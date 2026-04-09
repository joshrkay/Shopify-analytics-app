"""
AI Chat API route for conversational analytics assistant.

Provides a POST endpoint that accepts a user question and returns
an LLM-generated response using the tenant's configured model.

SECURITY:
- Requires valid tenant context from JWT
- Requires LLM_ROUTING entitlement (Growth+ tiers)
- Input length limited to 2000 characters
"""

import logging

from fastapi import APIRouter, Request, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.platform.tenant_context import get_tenant_context
from src.api.dependencies.entitlements import check_llm_routing_entitlement
from src.services.llm_routing_service import LLMRoutingService, LLMRoutingError
from src.integrations.openrouter.models import ChatMessage
from src.integrations.openrouter.client import get_openrouter_client
from src.services.analytics_context_service import (
    get_analytics_snapshot,
    build_analytics_system_prompt,
)
from src.agents.analytics_agent import AnalyticsAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai-chat"])


# =============================================================================
# Request / Response Models
# =============================================================================


class AIChatRequest(BaseModel):
    """Request model for AI chat."""

    question: str = Field(..., min_length=1, max_length=2000)


class AIChatResponse(BaseModel):
    """Response model for AI chat."""

    message: str
    model_id: str | None = None


# =============================================================================
# Route
# =============================================================================


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    request: Request,
    body: AIChatRequest,
    db_session=Depends(check_llm_routing_entitlement),
):
    """
    Send a question to the AI analytics assistant.

    Requires LLM_ROUTING entitlement (Growth+ plan).

    Fetches a 30-day analytics snapshot from the mart layer and injects it
    into the system prompt so the LLM can answer questions about real data.
    Falls back to a generic prompt when no mart data is available yet.
    """
    tenant_ctx = get_tenant_context(request)

    context = get_analytics_snapshot(tenant_ctx.tenant_id, db_session)
    system_prompt = build_analytics_system_prompt(context)

    service = LLMRoutingService(db_session, tenant_ctx.tenant_id)

    try:
        primary_model = service.get_primary_model()
        fallback_model = service.get_fallback_model()
    except LLMRoutingError as exc:
        logger.error(
            "AI chat model resolution failed",
            extra={"tenant_id": tenant_ctx.tenant_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is temporarily unavailable. Please try again.",
        )

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=body.question),
    ]

    agent = AnalyticsAgent(
        client=get_openrouter_client(),
        primary_model=primary_model,
        fallback_model=fallback_model,
        db=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    try:
        result = await agent.run(messages=messages)
    except Exception as exc:
        logger.error(
            "AI chat agent failed",
            extra={"tenant_id": tenant_ctx.tenant_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is temporarily unavailable. Please try again.",
        )

    return AIChatResponse(
        message=result.content,
        model_id=result.model_id,
    )
