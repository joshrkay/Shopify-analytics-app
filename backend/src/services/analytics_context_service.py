"""
Analytics Context Service.

Fetches a snapshot of tenant analytics data from dbt marts for injection
into LLM prompts. This is what makes the AI chat feature data-aware —
grounding LLM responses in real merchant metrics rather than generic advice.

SECURITY:
- tenant_id comes from JWT only (never from client input)
- Queries only aggregated marts (no raw PII)
- Returns None on any failure (graceful degradation — chat still works)

Tables queried (verified against dbt model final SELECTs per CLAUDE.md):
- marts.mart_revenue_metrics   → period_type, gross_revenue, net_revenue,
                                  order_count, aov, *_change_pct columns
- marts.mart_marketing_metrics → period_type, platform, spend, orders,
                                  gross_roas, cac, new_customers, *_change_pct
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_analytics_snapshot(tenant_id: str, db: Session) -> Optional[dict]:
    """
    Return a last-30-day analytics snapshot from the dbt mart layer.

    Returns a structured dict for LLM prompt injection, or None when
    data is unavailable (new tenant, no synced sources, mart query error).
    Never raises — degrades gracefully so chat still works without data.
    """
    try:
        revenue = _fetch_revenue_metrics(tenant_id, db)
        channels = _fetch_channel_metrics(tenant_id, db)

        if not revenue and not channels:
            return None

        return {
            "revenue": revenue,
            "channels": channels,
        }
    except Exception:
        logger.warning(
            "Failed to fetch analytics snapshot for AI chat — falling back to generic prompt",
            extra={"tenant_id": tenant_id},
            exc_info=True,
        )
        return None


def _fetch_revenue_metrics(tenant_id: str, db: Session) -> Optional[dict]:
    row = db.execute(
        text("""
            SELECT
                gross_revenue,
                net_revenue,
                order_count,
                aov,
                gross_revenue_change_pct,
                order_count_change_pct,
                aov_change_pct,
                currency,
                period_start,
                period_end
            FROM marts.mart_revenue_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = 'last_30_days'
            LIMIT 1
        """),
        {"tenant_id": tenant_id},
    ).fetchone()

    if not row:
        return None

    return {
        "gross_revenue": _fmt_money(row.gross_revenue, row.currency),
        "net_revenue": _fmt_money(row.net_revenue, row.currency),
        "order_count": int(row.order_count or 0),
        "aov": _fmt_money(row.aov, row.currency),
        "revenue_change_pct": _fmt_pct(row.gross_revenue_change_pct),
        "order_count_change_pct": _fmt_pct(row.order_count_change_pct),
        "aov_change_pct": _fmt_pct(row.aov_change_pct),
        "currency": row.currency or "USD",
    }


def _fetch_channel_metrics(tenant_id: str, db: Session) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT
                platform,
                spend,
                orders,
                gross_roas,
                cac,
                new_customers,
                gross_roas_change_pct,
                spend_change_pct,
                currency
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = 'last_30_days'
            ORDER BY spend DESC NULLS LAST
            LIMIT 8
        """),
        {"tenant_id": tenant_id},
    ).fetchall()

    channels = []
    for row in rows:
        channels.append({
            "platform": row.platform or "unknown",
            "spend": _fmt_money(row.spend, row.currency),
            "orders": int(row.orders or 0),
            "roas": _fmt_decimal(row.gross_roas),
            "cac": _fmt_money(row.cac, row.currency),
            "new_customers": int(row.new_customers or 0),
            "roas_change_pct": _fmt_pct(row.gross_roas_change_pct),
            "spend_change_pct": _fmt_pct(row.spend_change_pct),
        })

    return channels


def build_analytics_system_prompt(context: Optional[dict]) -> str:
    """
    Build the AI chat system prompt, injecting real metrics when available.

    With context:  Tells the LLM the merchant's actual ROAS, revenue, channel
                   breakdown so it can answer specific questions with real data.
    Without context: Generic analytics assistant prompt (new merchant / no data).
    """
    base = (
        "You are an analytics assistant for a Shopify merchant. "
        "Answer questions about their marketing metrics, ad performance, "
        "and revenue data. Be concise and data-driven."
    )

    if not context:
        return base

    lines = [base, "", "Current merchant analytics (last 30 days):"]

    rev = context.get("revenue")
    if rev:
        rev_change = rev["revenue_change_pct"] or "no prior data"
        ord_change = rev["order_count_change_pct"] or "no prior data"
        aov_change = rev["aov_change_pct"] or "no prior data"
        lines.append(
            f"- Revenue: {rev['gross_revenue']} gross "
            f"({rev_change} vs prior period)"
        )
        lines.append(
            f"- Orders: {rev['order_count']:,} ({ord_change}), "
            f"AOV: {rev['aov']} ({aov_change})"
        )

    channels = context.get("channels", [])
    if channels:
        lines.append("- Ad channel performance:")
        for ch in channels:
            roas_str = f"ROAS {ch['roas']}x" if ch["roas"] else "no ROAS"
            roas_change = f" ({ch['roas_change_pct']})" if ch["roas_change_pct"] else ""
            spend_str = f"spend {ch['spend']}"
            lines.append(
                f"  \u2022 {ch['platform']}: {roas_str}{roas_change}, {spend_str}"
            )

    lines.extend([
        "",
        "Answer using the data above. If asked about something not in this "
        "snapshot (e.g., individual campaigns or dates outside 30 days), say "
        "you can see summary-level data but not that level of detail here.",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_money(value, currency: Optional[str] = None) -> str:
    if value is None:
        return "N/A"
    symbol = "$" if not currency or currency.upper() == "USD" else f"{currency} "
    try:
        return f"{symbol}{float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value) -> Optional[str]:
    if value is None:
        return None
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"
    except (TypeError, ValueError):
        return None


def _fmt_decimal(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None
