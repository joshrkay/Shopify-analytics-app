"""
Orders API — Shopify order list with UTM attribution overlay.

Provides:
  GET /api/orders — paginated order list with UTM fields from last-click attribution

No entitlement gate — available on all plans.
Queries: canonical.orders LEFT JOIN attribution.last_click
Tenant isolation: WHERE fo.tenant_id = :tenant_id on every query.
"""

import logging
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orders", tags=["orders"])

TIMEFRAME_DAYS: dict[str, int] = {
    "7days": 7,
    "thisWeek": 7,
    "30days": 30,
    "thisMonth": 30,
    "90days": 90,
    "thisQuarter": 90,
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

class Order(BaseModel):
    order_id: str
    order_number: Optional[str] = None
    order_name: Optional[str] = None
    revenue: float
    currency: str
    financial_status: Optional[str] = None
    created_at: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    platform: Optional[str] = None


class OrdersListResponse(BaseModel):
    orders: List[Order]
    total: int
    has_more: bool


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("", response_model=OrdersListResponse)
async def get_orders(
    request: Request,
    timeframe: str = Query("30days", description="7days|30days|90days|thisMonth|thisQuarter"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(_get_db),
):
    """
    Paginated Shopify order list with UTM attribution overlay.
    No custom_reports entitlement required.
    """
    tenant_ctx = get_tenant_context(request)
    days = TIMEFRAME_DAYS.get(timeframe, 30)
    start_date = date.today() - timedelta(days=days)

    try:
        rows = db.execute(text("""
            SELECT
                fo.order_id,
                fo.order_number,
                fo.order_name,
                COALESCE(fo.revenue_gross, 0)      AS revenue,
                COALESCE(fo.currency, 'USD')        AS currency,
                fo.financial_status,
                fo.order_created_at                 AS created_at,
                lc.utm_source,
                lc.utm_medium,
                lc.utm_campaign,
                lc.platform
            FROM canonical.orders fo
            LEFT JOIN attribution.last_click lc
                   ON lc.order_id = fo.order_id
                  AND lc.tenant_id = fo.tenant_id
            WHERE fo.tenant_id = :tenant_id
              AND fo.order_created_at >= :start_date
            ORDER BY fo.order_created_at DESC
            LIMIT :limit OFFSET :offset
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "start_date": start_date,
            "limit": limit,
            "offset": offset,
        }).fetchall()

        total_row = db.execute(text("""
            SELECT COUNT(*) AS total
            FROM canonical.orders fo
            WHERE fo.tenant_id = :tenant_id
              AND fo.order_created_at >= :start_date
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "start_date": start_date,
        }).fetchone()

        total = int(total_row.total) if total_row else 0

        orders = [
            Order(
                order_id=str(r.order_id),
                order_number=str(r.order_number) if r.order_number is not None else None,
                order_name=r.order_name,
                revenue=float(r.revenue),
                currency=r.currency,
                financial_status=r.financial_status,
                created_at=r.created_at.isoformat() if r.created_at else "",
                utm_source=r.utm_source,
                utm_medium=r.utm_medium,
                utm_campaign=r.utm_campaign,
                platform=r.platform,
            )
            for r in rows
        ]

        return OrdersListResponse(
            orders=orders,
            total=total,
            has_more=(offset + limit) < total,
        )

    except Exception as exc:
        logger.warning("Orders query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orders data unavailable",
        )
