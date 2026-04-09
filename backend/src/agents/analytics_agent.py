"""
Analytics Agent — tool-calling loop for AI chat.

Extends the single LLM call in ai_chat.py into an agentic loop that
lets the model request more specific data when the pre-fetched 30-day
snapshot isn't enough to answer a question.

Example questions that benefit from tool calls:
  "What's my TikTok ROAS for the last 7 days?"
  "Show me my top 5 campaigns by spend"
  "Which channel drives the most new customers?"

The agent never calls more than MAX_ITERATIONS times, so worst-case
latency is bounded. When the model doesn't invoke any tools (the common
case for simple questions), it returns after a single LLM call.

SECURITY:
  - tenant_id scopes every SQL query
  - Tools are read-only (SELECT only)
  - Max 3 tool iterations prevents runaway loops

Tables queried (verified against dbt model final SELECTs per CLAUDE.md):
  - marts.fct_marketing_metrics  → channel/campaign hierarchy, roas, cac, ctr
  - marts.mart_revenue_metrics   → gross_revenue, net_revenue, order_count, aov
  - attribution.last_click       → platform, revenue, attribution_status
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.integrations.openrouter.client import OpenRouterClient
from src.integrations.openrouter.models import (
    ChatMessage,
    ToolCall,
    ToolDefinition,
)
from src.models.llm_routing import LLMModelRegistry, LLMResponseStatus, LLMUsageLog

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

# ---------------------------------------------------------------------------
# Tool definitions exposed to the model
# ---------------------------------------------------------------------------

TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="query_marketing_metrics",
        description=(
            "Get marketing metrics (ROAS, spend, CAC, clicks, impressions, CTR) "
            "for a specific channel or time period. Use this when the user asks "
            "about a specific platform, campaign, or time range not covered by "
            "the 30-day summary."
        ),
        parameters={
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": (
                        "Filter by channel name, e.g. 'meta_ads', 'google_ads', "
                        "'tiktok_ads', 'snapchat_ads', 'pinterest_ads'. "
                        "Omit to get all channels."
                    ),
                },
                "period_type": {
                    "type": "string",
                    "enum": ["last_7_days", "last_30_days", "last_90_days", "monthly"],
                    "description": "Time period. Defaults to last_30_days.",
                },
                "hierarchy_level": {
                    "type": "string",
                    "enum": ["channel", "campaign", "adset"],
                    "description": (
                        "Level of detail. 'channel' for platform totals, "
                        "'campaign' for campaign breakdown. Defaults to 'channel'."
                    ),
                },
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="get_revenue_breakdown",
        description=(
            "Get revenue metrics (gross/net revenue, AOV, order count, "
            "refunds) for a specific time period."
        ),
        parameters={
            "type": "object",
            "properties": {
                "period_type": {
                    "type": "string",
                    "enum": ["last_7_days", "last_30_days", "last_90_days"],
                    "description": "Time period. Defaults to last_30_days.",
                },
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="get_attribution_by_channel",
        description=(
            "Get attribution data showing which channels are credited for "
            "orders, based on last-click UTM attribution. Shows attributed "
            "vs unattributed order split per platform."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _execute_tool(
    call: ToolCall,
    tenant_id: str,
    db: Session,
) -> str:
    """
    Execute a tool call and return the result as a JSON string.
    Returns an error message string on failure (never raises).
    """
    try:
        args: dict = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        args = {}

    try:
        if call.name == "query_marketing_metrics":
            return _tool_marketing_metrics(tenant_id, db, args)
        if call.name == "get_revenue_breakdown":
            return _tool_revenue_breakdown(tenant_id, db, args)
        if call.name == "get_attribution_by_channel":
            return _tool_attribution_by_channel(tenant_id, db)
        return json.dumps({"error": f"Unknown tool: {call.name}"})
    except Exception as exc:
        logger.warning(
            "Tool execution failed",
            extra={"tool": call.name, "tenant_id": tenant_id, "error": str(exc)},
        )
        return json.dumps({"error": f"Tool failed: {exc}"})


def _tool_marketing_metrics(tenant_id: str, db: Session, args: dict) -> str:
    platform = args.get("platform")
    period_type = args.get("period_type", "last_30_days")
    hierarchy_level = args.get("hierarchy_level", "channel")

    filters = "WHERE tenant_id = :tenant_id AND period_type = :period_type"
    params: dict = {"tenant_id": tenant_id, "period_type": period_type}

    if hierarchy_level in ("channel", "campaign", "adset"):
        filters += " AND hierarchy_level = :level"
        params["level"] = hierarchy_level

    if platform:
        filters += " AND channel = :platform"
        params["platform"] = platform

    rows = db.execute(
        text(f"""
            SELECT
                channel,
                hierarchy_level,
                period_type,
                total_spend,
                total_revenue,
                order_count,
                new_customers,
                total_impressions,
                total_clicks,
                roas,
                cac,
                ctr,
                aov,
                currency
            FROM marts.fct_marketing_metrics
            {filters}
            ORDER BY total_spend DESC NULLS LAST
            LIMIT 10
        """),
        params,
    ).fetchall()

    if not rows:
        return json.dumps({"result": "No data found for the requested filters."})

    return json.dumps({
        "result": [
            {
                "channel": r.channel,
                "hierarchy_level": r.hierarchy_level,
                "period_type": r.period_type,
                "total_spend": float(r.total_spend or 0),
                "total_revenue": float(r.total_revenue or 0),
                "order_count": int(r.order_count or 0),
                "new_customers": int(r.new_customers or 0),
                "roas": round(float(r.roas or 0), 2),
                "cac": round(float(r.cac or 0), 2),
                "ctr": round(float(r.ctr or 0), 2),
                "aov": round(float(r.aov or 0), 2),
                "currency": r.currency,
            }
            for r in rows
        ]
    })


def _tool_revenue_breakdown(tenant_id: str, db: Session, args: dict) -> str:
    period_type = args.get("period_type", "last_30_days")

    row = db.execute(
        text("""
            SELECT
                gross_revenue,
                net_revenue,
                order_count,
                aov,
                refund_amount,
                gross_revenue_change_pct,
                net_revenue_change_pct,
                order_count_change_pct,
                aov_change_pct,
                currency,
                period_start,
                period_end
            FROM marts.mart_revenue_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
            LIMIT 1
        """),
        {"tenant_id": tenant_id, "period_type": period_type},
    ).fetchone()

    if not row:
        return json.dumps({"result": "No revenue data available for this period."})

    return json.dumps({
        "result": {
            "gross_revenue": float(row.gross_revenue or 0),
            "net_revenue": float(row.net_revenue or 0),
            "order_count": int(row.order_count or 0),
            "aov": round(float(row.aov or 0), 2),
            "refund_amount": float(row.refund_amount or 0),
            "gross_revenue_change_pct": float(row.gross_revenue_change_pct or 0),
            "order_count_change_pct": float(row.order_count_change_pct or 0),
            "aov_change_pct": float(row.aov_change_pct or 0),
            "currency": row.currency,
            "period_start": str(row.period_start) if row.period_start else None,
            "period_end": str(row.period_end) if row.period_end else None,
        }
    })


def _tool_attribution_by_channel(tenant_id: str, db: Session) -> str:
    rows = db.execute(
        text("""
            SELECT
                platform,
                COUNT(*) AS order_count,
                SUM(revenue) AS total_revenue,
                attribution_status
            FROM attribution.last_click
            WHERE tenant_id = :tenant_id
            GROUP BY platform, attribution_status
            ORDER BY total_revenue DESC NULLS LAST
            LIMIT 20
        """),
        {"tenant_id": tenant_id},
    ).fetchall()

    if not rows:
        return json.dumps({"result": "No attribution data available."})

    return json.dumps({
        "result": [
            {
                "platform": r.platform,
                "order_count": int(r.order_count or 0),
                "total_revenue": round(float(r.total_revenue or 0), 2),
                "attribution_status": r.attribution_status,
            }
            for r in rows
        ]
    })


# ---------------------------------------------------------------------------
# Agent result
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Result returned from AnalyticsAgent.run()."""
    content: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    cost_usd: Decimal
    was_fallback: bool
    tool_calls_made: int
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AnalyticsAgent:
    """
    Tool-calling analytics agent.

    Wraps the OpenRouter client to support a multi-turn tool loop.
    Falls through to a single LLM call (no extra latency) when the
    model doesn't invoke any tools.
    """

    def __init__(
        self,
        client: OpenRouterClient,
        primary_model: LLMModelRegistry,
        fallback_model: LLMModelRegistry | None,
        db: Session,
        tenant_id: str,
    ) -> None:
        self._client = client
        self._primary = primary_model
        self._fallback = fallback_model
        self._db = db
        self._tenant_id = tenant_id

    async def run(
        self,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AgentResult:
        """
        Run the agent loop.

        Sends messages to the LLM with tool definitions. If the model
        requests tool calls, executes them and loops (up to MAX_ITERATIONS).
        Returns when the model produces a final text response.
        """
        start = time.time()
        total_input = 0
        total_output = 0
        tool_calls_made = 0
        model = self._primary
        was_fallback = False
        fallback_reason = None

        conversation = list(messages)

        for iteration in range(MAX_ITERATIONS + 1):
            try:
                response = await self._client.chat_completion(
                    messages=conversation,
                    model=model.model_id,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=TOOLS if iteration < MAX_ITERATIONS else None,
                )
            except Exception as exc:
                if not was_fallback and self._fallback:
                    logger.warning(
                        "Analytics agent primary model failed, trying fallback",
                        extra={"error": str(exc), "tenant_id": self._tenant_id},
                    )
                    model = self._fallback
                    was_fallback = True
                    fallback_reason = type(exc).__name__
                    response = await self._client.chat_completion(
                        messages=conversation,
                        model=model.model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        tools=TOOLS if iteration < MAX_ITERATIONS else None,
                    )
                else:
                    raise

            total_input += response.input_tokens
            total_output += response.output_tokens

            # No tool calls — return the text response
            if not response.tool_calls:
                latency_ms = int((time.time() - start) * 1000)
                cost = model.calculate_cost(total_input, total_output)
                return AgentResult(
                    content=response.content,
                    model_id=model.model_id,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_tokens=total_input + total_output,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    was_fallback=was_fallback,
                    tool_calls_made=tool_calls_made,
                    fallback_reason=fallback_reason,
                )

            # Append assistant message (with tool_calls) to conversation
            # OpenRouter expects the raw tool_calls list in the assistant message
            assistant_msg = ChatMessage(
                role="assistant",
                content=response.content or "",
            )
            conversation.append(assistant_msg)

            # Execute each tool and append results
            for tc in response.tool_calls:
                tool_calls_made += 1
                result_str = _execute_tool(tc, self._tenant_id, self._db)
                conversation.append(
                    ChatMessage(
                        role="tool",
                        content=result_str,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )

        # Exhausted iterations — return whatever the last response said
        latency_ms = int((time.time() - start) * 1000)
        cost = model.calculate_cost(total_input, total_output)
        return AgentResult(
            content=response.content or "",
            model_id=model.model_id,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            latency_ms=latency_ms,
            cost_usd=cost,
            was_fallback=was_fallback,
            tool_calls_made=tool_calls_made,
            fallback_reason=fallback_reason,
        )
