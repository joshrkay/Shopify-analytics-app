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
# System Prompt
# =============================================================================

_SYSTEM_PROMPT = (
    "You are an analytics assistant for a Shopify merchant. "
    "Answer questions about their marketing metrics, ad performance, "
    "and revenue data. Be concise and data-driven."
)


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
    """
    tenant_ctx = get_tenant_context(request)

    service = LLMRoutingService(db_session, tenant_ctx.tenant_id)

    messages = [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(role="user", content=body.question),
    ]

    try:
        result = await service.complete(
            messages=messages,
            template_key="ai_chat",
        )
    except LLMRoutingError as exc:
        logger.error(
            "AI chat LLM routing failed",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is temporarily unavailable. Please try again.",
        )

    return AIChatResponse(
        message=result.content,
        model_id=result.model_id,
    )
