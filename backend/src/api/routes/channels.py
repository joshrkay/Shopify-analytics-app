"""
Per-channel analytics routes.

Provides a single endpoint:
  GET /api/channels/{platform}/metrics?timeframe=

Returns aggregated metrics for one ad platform (revenue, spend, ROAS, clicks,
impressions, CTR, conversion_rate) plus a daily revenue trend series.

SECURITY:
- Requires valid tenant context from JWT (no entitlement gate — available
  on all plans, same as /api/datasets/kpi-summary).
- All queries are scoped to tenant_id from the JWT context.

Queries:
  1. mart_marketing_metrics   — revenue, spend, gross_roas
  2. analytics.fct_marketing_spend — clicks, impressions, ctr, conversions
  3. mart_marketing_metrics daily — daily revenue trend
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context
from src.database.session import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])

# ---------------------------------------------------------------------------
# Timeframe → period_type mapping (mirrors datasets.py)
# ---------------------------------------------------------------------------

TIMEFRAME_TO_PERIOD: dict[str, str] = {
    "7days":       "last_7_days",
    "thisWeek":    "this_week",
    "30days":      "last_30_days",
    "thisMonth":   "this_month",
    "90days":      "last_90_days",
    "thisQuarter": "this_quarter",
}

CHANNEL_DISPLAY_NAMES: dict[str, str] = {
    "meta_ads":      "Facebook Ads",
    "facebook_ads":  "Facebook Ads",
    "google_ads":    "Google Ads",
    "instagram_ads": "Instagram Ads",
    "tiktok_ads":    "TikTok Ads",
    "snapchat_ads":  "Snapchat Ads",
    "pinterest_ads": "Pinterest Ads",
    "twitter_ads":   "Twitter/X Ads",
    "organic":       "Organic",
}

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ChannelTrendPoint(BaseModel):
    date: str
    revenue: float


class ChannelMetricsResponse(BaseModel):
    platform: str = Field(..., description="Platform key, e.g. 'google_ads'")
    display_name: str = Field(..., description="Human-readable platform name")

    # Aggregated totals for the selected period
    revenue: float = Field(..., description="Total gross revenue")
    spend: float = Field(..., description="Total ad spend")
    roas: float = Field(..., description="Gross ROAS (revenue / spend)")
    orders: int = Field(..., description="Total orders / conversions")

    # Click-level metrics from fct_marketing_spend
    clicks: int = Field(..., description="Total clicks")
    impressions: int = Field(..., description="Total impressions")
    ctr: float = Field(..., description="Average click-through rate (0–1)")
    conversion_rate: float = Field(..., description="Conversions / clicks (0–1)")

    # Daily revenue trend for line chart
    daily_trend: List[ChannelTrendPoint] = Field(
        ..., description="Daily revenue for the trailing window"
    )


# ---------------------------------------------------------------------------
# DB dependency — no entitlement gate (all plans)
# ---------------------------------------------------------------------------


def _get_db_for_channels(request: Request):
    """Open a DB session after validating tenant context."""
    get_tenant_context(request)  # raises 401/403 if invalid
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/{platform}/metrics",
    response_model=ChannelMetricsResponse,
)
async def get_channel_metrics(
    platform: str,
    request: Request,
    timeframe: str = Query("30days", description="7days|thisWeek|30days|thisMonth|90days|thisQuarter"),
    db_session=Depends(_get_db_for_channels),
):
    """
    Aggregated metrics for a single ad platform.

    Available on all plans — no CUSTOM_REPORTS entitlement required.
    Queries mart_marketing_metrics (revenue/spend/ROAS) and
    analytics.fct_marketing_spend (clicks/impressions/CTR).
    """
    tenant_ctx = get_tenant_context(request)
    period_type = TIMEFRAME_TO_PERIOD.get(timeframe, "last_30_days")
    display_name = CHANNEL_DISPLAY_NAMES.get(platform, platform.replace("_", " ").title())

    try:
        # ── Aggregated marketing metrics for this platform ─────────────────
        mkt = db_session.execute(text("""
            SELECT
                COALESCE(SUM(gross_revenue), 0)  AS revenue,
                COALESCE(SUM(spend), 0)          AS spend,
                COALESCE(AVG(gross_roas), 0)     AS roas,
                COALESCE(SUM(orders), 0)         AS orders
            FROM marts.mart_marketing_metrics
            WHERE tenant_id   = :tenant_id
              AND period_type = :period_type
              AND (
                platform = :platform
                OR (:platform = 'organic' AND platform IS NULL)
              )
              AND period_end = (
                  SELECT MAX(period_end)
                  FROM marts.mart_marketing_metrics
                  WHERE tenant_id   = :tenant_id
                    AND period_type = :period_type
                    AND period_end  <= current_date::date
              )
        """), {
            "tenant_id":   tenant_ctx.tenant_id,
            "period_type": period_type,
            "platform":    platform,
        }).fetchone()

        # ── Click-level metrics from canonical fact table ──────────────────
        # analytics.marketing_spend has daily rows; sum over the matching date range.
        days_map = {
            "last_7_days":   7,
            "this_week":     7,
            "last_30_days":  30,
            "this_month":    30,
            "last_90_days":  90,
            "this_quarter":  90,
        }
        lookback_days = days_map.get(period_type, 30)

        clicks_row = db_session.execute(text("""
            SELECT
                COALESCE(SUM(clicks), 0)       AS clicks,
                COALESCE(SUM(impressions), 0)  AS impressions,
                COALESCE(AVG(ctr), 0)          AS ctr,
                COALESCE(SUM(conversions), 0)  AS conversions
            FROM analytics.marketing_spend
            WHERE tenant_id       = :tenant_id
              AND source_platform = :platform
              AND date >= current_date - (:lookback_days * INTERVAL '1 day')
              AND date <= current_date
        """), {
            "tenant_id":     tenant_ctx.tenant_id,
            "platform":      platform,
            "lookback_days": lookback_days,
        }).fetchone()

        # ── Daily revenue trend (trailing 90 days, daily granularity) ──────
        trend_rows = db_session.execute(text("""
            SELECT
                period_start::date              AS day,
                COALESCE(SUM(gross_revenue), 0) AS revenue
            FROM marts.mart_marketing_metrics
            WHERE tenant_id   = :tenant_id
              AND period_type = 'daily'
              AND (
                platform = :platform
                OR (:platform = 'organic' AND platform IS NULL)
              )
              AND period_start >= current_date - INTERVAL '89 days'
              AND period_start <= current_date
            GROUP BY period_start::date
            ORDER BY day ASC
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "platform":  platform,
        }).fetchall()

        # ── Build response ─────────────────────────────────────────────────
        revenue  = float(mkt.revenue)  if mkt else 0.0
        spend    = float(mkt.spend)    if mkt else 0.0
        roas     = float(mkt.roas)     if mkt else 0.0
        orders   = int(mkt.orders)     if mkt else 0

        clicks      = int(clicks_row.clicks)         if clicks_row else 0
        impressions = int(clicks_row.impressions)    if clicks_row else 0
        ctr = clicks / impressions if impressions > 0 else 0.0
        conversions = int(clicks_row.conversions)    if clicks_row else 0

        conv_rate = conversions / clicks if clicks > 0 else 0.0

        trend = [
            ChannelTrendPoint(date=str(r.day), revenue=float(r.revenue))
            for r in trend_rows
        ]

        return ChannelMetricsResponse(
            platform=platform,
            display_name=display_name,
            revenue=revenue,
            spend=spend,
            roas=roas,
            orders=orders,
            clicks=clicks,
            impressions=impressions,
            ctr=ctr,
            conversion_rate=conv_rate,
            daily_trend=trend,
        )

    except Exception as exc:
        logger.warning("Channel metrics query failed for %s: %s", platform, exc)
        raise HTTPException(status_code=503, detail="Analytics data unavailable")
