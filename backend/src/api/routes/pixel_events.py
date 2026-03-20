"""
Pixel Events API — ingestion endpoint for Shopify Web Pixel events.

POST /api/pixel/events — Receives batched customer journey events from the
  web pixel running in the customer's browser. No JWT auth required.
GET  /api/pixel/status — Check pixel status for a store (authenticated).

Events are stored in the pixel_events table for dbt processing into
customer sessions and enhanced attribution.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pixel", tags=["pixel"])

# Rate limit: max events per single request
MAX_EVENTS_PER_REQUEST = 100


class PixelEventPayload(BaseModel):
    """Single pixel event from the browser."""

    event_type: str = Field(..., max_length=100)
    event_data: Optional[dict] = None
    page_url: Optional[str] = Field(None, max_length=2048)
    referrer: Optional[str] = Field(None, max_length=2048)
    utm_source: Optional[str] = Field(None, max_length=255)
    utm_medium: Optional[str] = Field(None, max_length=255)
    utm_campaign: Optional[str] = Field(None, max_length=500)
    utm_term: Optional[str] = Field(None, max_length=500)
    utm_content: Optional[str] = Field(None, max_length=500)
    event_timestamp: str  # ISO 8601 timestamp from browser


class PixelEventBatch(BaseModel):
    """Batch of pixel events from a single session."""

    shop_domain: str = Field(..., max_length=255)
    session_id: str = Field(..., max_length=255)
    events: List[PixelEventPayload] = Field(..., max_length=MAX_EVENTS_PER_REQUEST)


class PixelStatusResponse(BaseModel):
    """Pixel status for a store."""

    pixel_active: bool
    events_last_24h: int = 0
    sessions_last_24h: int = 0


@router.post("/events", status_code=204)
async def ingest_pixel_events(
    batch: PixelEventBatch,
    session: Session = Depends(get_db_session),
):
    """
    Receive batched pixel events from the Shopify Web Pixel.

    No JWT auth — pixel runs in the customer's browser.
    Validated by checking that shop_domain exists in shopify_stores.
    """
    if len(batch.events) > MAX_EVENTS_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {MAX_EVENTS_PER_REQUEST} events per request",
        )

    if not batch.events:
        return

    try:
        from src.models.store import ShopifyStore

        # Validate shop_domain — must exist in our system
        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == batch.shop_domain
        ).first()

        if not store:
            logger.warning("Pixel event from unknown shop", extra={
                "shop_domain": batch.shop_domain,
            })
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown shop domain",
            )

        from src.models.pixel_event import PixelEvent

        for event_payload in batch.events:
            # Parse event timestamp
            try:
                event_ts = datetime.fromisoformat(
                    event_payload.event_timestamp.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                event_ts = datetime.now(timezone.utc)

            pixel_event = PixelEvent(
                tenant_id=store.tenant_id,
                shop_domain=batch.shop_domain,
                session_id=batch.session_id,
                event_type=event_payload.event_type,
                event_data=event_payload.event_data,
                page_url=event_payload.page_url,
                referrer=event_payload.referrer,
                utm_source=event_payload.utm_source,
                utm_medium=event_payload.utm_medium,
                utm_campaign=event_payload.utm_campaign,
                utm_term=event_payload.utm_term,
                utm_content=event_payload.utm_content,
                event_timestamp=event_ts,
            )
            session.add(pixel_event)

        session.commit()

        logger.info("Pixel events ingested", extra={
            "shop_domain": batch.shop_domain,
            "session_id": batch.session_id,
            "event_count": len(batch.events),
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error ingesting pixel events", extra={
            "shop_domain": batch.shop_domain,
            "error": str(e),
        })
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store pixel events",
        )


@router.get("/status", response_model=PixelStatusResponse)
async def get_pixel_status(
    request: Request,
    session: Session = Depends(get_db_session),
):
    """
    Check Web Pixel status for the authenticated merchant's store.

    Returns whether the pixel is active and recent event counts.
    """
    from sqlalchemy import func, text

    # Get tenant_id from request state (set by TenantContextMiddleware)
    tenant_id = getattr(request.state, "active_tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        from src.models.pixel_event import PixelEvent

        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Count events in last 24h
        events_count = session.query(func.count(PixelEvent.id)).filter(
            PixelEvent.tenant_id == tenant_id,
            PixelEvent.event_timestamp >= cutoff,
        ).scalar() or 0

        # Count unique sessions in last 24h
        sessions_count = session.query(
            func.count(func.distinct(PixelEvent.session_id))
        ).filter(
            PixelEvent.tenant_id == tenant_id,
            PixelEvent.event_timestamp >= cutoff,
        ).scalar() or 0

        return PixelStatusResponse(
            pixel_active=events_count > 0,
            events_last_24h=events_count,
            sessions_last_24h=sessions_count,
        )

    except Exception as e:
        logger.error("Error checking pixel status", extra={
            "tenant_id": tenant_id,
            "error": str(e),
        })
        return PixelStatusResponse(pixel_active=False)
