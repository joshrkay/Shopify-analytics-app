"""
Attribution API — UTM last-click attribution data.

Provides:
  GET /api/attribution/summary  — aggregate KPIs + top campaigns + channel ROAS
  GET /api/attribution/orders   — paginated attributed orders with UTM fields

No entitlement gate — available on all plans.
Queries: attribution.last_click + marts.mart_marketing_metrics
Tenant isolation: WHERE tenant_id = :tenant_id on every query.
"""

import logging
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/attribution", tags=["attribution"])

TIMEFRAME_DAYS: dict[str, int] = {
    "7days": 7,
    "thisWeek": 7,
    "30days": 30,
    "thisMonth": 30,
    "90days": 90,
    "thisQuarter": 90,
}

TIMEFRAME_TO_PERIOD: dict[str, str] = {
    "7days": "last_7_days",
    "thisWeek": "weekly",
    "30days": "last_30_days",
    "thisMonth": "monthly",
    "90days": "last_90_days",
    "thisQuarter": "quarterly",
}


def _get_db(request: Request):
    """DB dependency — validates JWT/tenant then yields a session."""
    get_tenant_context(request)  # raises 401/403 if invalid
    from src.database.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TopCampaign(BaseModel):
    campaign_name: str
    platform: Optional[str] = None
    revenue: float
    orders: int
    spend: float
    roas: Optional[float] = None  # None when spend == 0


class ChannelRoas(BaseModel):
    platform: str
    gross_roas: float
    revenue: float
    spend: float


class AttributionSummaryResponse(BaseModel):
    attributed_orders: int
    unattributed_orders: int
    attribution_rate: float          # percentage 0–100
    total_attributed_revenue: float
    top_campaigns: List[TopCampaign]
    channel_roas: List[ChannelRoas]


class AttributedOrder(BaseModel):
    order_id: str
    order_name: Optional[str] = None
    order_number: Optional[str] = None
    revenue: float
    currency: str
    created_at: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    platform: Optional[str] = None
    attribution_status: str


class AttributedOrdersResponse(BaseModel):
    orders: List[AttributedOrder]
    total: int
    has_more: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=AttributionSummaryResponse)
async def get_attribution_summary(
    request: Request,
    timeframe: str = Query("30days", description="7days|30days|90days|thisMonth|thisQuarter"),
    db=Depends(_get_db),
):
    """
    Aggregated attribution KPIs for the Attribution dashboard.
    No custom_reports entitlement required.
    """
    tenant_ctx = get_tenant_context(request)
    days = TIMEFRAME_DAYS.get(timeframe, 30)
    start_date = date.today() - timedelta(days=days)
    period_type = TIMEFRAME_TO_PERIOD.get(timeframe, "last_30_days")

    try:
        # Attribution counts + attributed revenue
        counts = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE attribution_status = 'attributed')
                    AS attributed,
                COUNT(*) FILTER (WHERE attribution_status <> 'attributed')
                    AS unattributed,
                COALESCE(
                    SUM(revenue) FILTER (WHERE attribution_status = 'attributed'),
                    0
                ) AS attributed_revenue
            FROM attribution.last_click
            WHERE tenant_id = :tenant_id
              AND order_created_at >= :start_date
        """), {"tenant_id": tenant_ctx.tenant_id, "start_date": start_date}).fetchone()

        attributed = int(counts.attributed) if counts else 0
        unattributed = int(counts.unattributed) if counts else 0
        total_orders = attributed + unattributed
        attribution_rate = round(attributed / total_orders * 100, 1) if total_orders > 0 else 0.0
        attributed_revenue = float(counts.attributed_revenue) if counts else 0.0

        # Top campaigns by attributed revenue
        campaign_rows = db.execute(text("""
            SELECT
                COALESCE(campaign_name, 'Unknown Campaign') AS campaign_name,
                platform,
                COALESCE(SUM(revenue), 0)        AS revenue,
                COUNT(*)                          AS orders,
                COALESCE(SUM(campaign_spend), 0)  AS spend
            FROM attribution.last_click
            WHERE tenant_id = :tenant_id
              AND attribution_status = 'attributed'
              AND order_created_at >= :start_date
            GROUP BY campaign_name, platform
            ORDER BY revenue DESC
            LIMIT 10
        """), {"tenant_id": tenant_ctx.tenant_id, "start_date": start_date}).fetchall()

        top_campaigns = [
            TopCampaign(
                campaign_name=r.campaign_name,
                platform=r.platform,
                revenue=float(r.revenue),
                orders=int(r.orders),
                spend=float(r.spend),
                roas=round(float(r.revenue) / float(r.spend), 2) if float(r.spend) > 0 else None,
            )
            for r in campaign_rows
        ]

        # Channel ROAS from mart (pre-aggregated with prior period)
        roas_rows = db.execute(text("""
            SELECT
                COALESCE(platform, 'organic') AS platform,
                COALESCE(AVG(gross_roas), 0)   AS gross_roas,
                COALESCE(SUM(gross_revenue), 0) AS revenue,
                COALESCE(SUM(spend), 0)         AS spend
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
              AND period_end = (
                  SELECT MAX(period_end)
                  FROM marts.mart_marketing_metrics
                  WHERE tenant_id = :tenant_id
                    AND period_type = :period_type
                    AND period_end <= current_date::date
              )
            GROUP BY platform
            ORDER BY gross_roas DESC
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type}).fetchall()

        channel_roas = [
            ChannelRoas(
                platform=r.platform,
                gross_roas=float(r.gross_roas),
                revenue=float(r.revenue),
                spend=float(r.spend),
            )
            for r in roas_rows
        ]

        return AttributionSummaryResponse(
            attributed_orders=attributed,
            unattributed_orders=unattributed,
            attribution_rate=attribution_rate,
            total_attributed_revenue=attributed_revenue,
            top_campaigns=top_campaigns,
            channel_roas=channel_roas,
        )

    except Exception as exc:
        logger.warning("Attribution summary query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attribution data unavailable",
        )


@router.get("/orders", response_model=AttributedOrdersResponse)
async def get_attributed_orders(
    request: Request,
    timeframe: str = Query("30days"),
    platform: Optional[str] = Query(None, description="Filter by ad platform, e.g. meta_ads"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(_get_db),
):
    """
    Paginated order list with UTM attribution fields.
    No custom_reports entitlement required.
    """
    tenant_ctx = get_tenant_context(request)
    days = TIMEFRAME_DAYS.get(timeframe, 30)
    start_date = date.today() - timedelta(days=days)

    # Parameterized platform filter avoids SQL injection
    # NULL means "all platforms"; a non-NULL value filters to that platform.
    try:
        rows = db.execute(text("""
            SELECT
                order_id, order_name, order_number,
                COALESCE(revenue, 0)        AS revenue,
                COALESCE(currency, 'USD')   AS currency,
                order_created_at            AS created_at,
                utm_source, utm_medium, utm_campaign,
                platform, attribution_status
            FROM attribution.last_click
            WHERE tenant_id = :tenant_id
              AND order_created_at >= :start_date
              AND (:platform IS NULL OR platform = :platform)
            ORDER BY order_created_at DESC
            LIMIT :limit OFFSET :offset
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "start_date": start_date,
            "platform": platform,
            "limit": limit,
            "offset": offset,
        }).fetchall()

        total_row = db.execute(text("""
            SELECT COUNT(*) AS total
            FROM attribution.last_click
            WHERE tenant_id = :tenant_id
              AND order_created_at >= :start_date
              AND (:platform IS NULL OR platform = :platform)
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "start_date": start_date,
            "platform": platform,
        }).fetchone()

        total = int(total_row.total) if total_row else 0

        orders = [
            AttributedOrder(
                order_id=str(r.order_id),
                order_name=r.order_name,
                order_number=str(r.order_number) if r.order_number is not None else None,
                revenue=float(r.revenue),
                currency=r.currency,
                created_at=r.created_at.isoformat() if r.created_at else "",
                utm_source=r.utm_source,
                utm_medium=r.utm_medium,
                utm_campaign=r.utm_campaign,
                platform=r.platform,
                attribution_status=r.attribution_status or "unattributed_no_utm",
            )
            for r in rows
        ]

        return AttributedOrdersResponse(
            orders=orders,
            total=total,
            has_more=(offset + limit) < total,
        )

    except Exception as exc:
        logger.warning("Attribution orders query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attribution data unavailable",
        )
