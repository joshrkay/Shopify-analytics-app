"""
Cohort Analysis API — customer retention heatmap data.

Provides:
  GET /api/analytics/cohort-analysis — cohort retention grid

Queries: analytics.fct_cohort_retention
Tenant isolation: WHERE tenant_id = :tenant_id on every query.
Entitlement gate: COHORT_ANALYSIS (growth+ tier).
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context
from src.api.dependencies.entitlements import check_cohort_analysis_entitlement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics/cohort-analysis", tags=["cohort_analysis"])


# Response models
class CohortPeriod(BaseModel):
    period: int
    retention_rate: float
    customers: int
    revenue: float


class CohortRow(BaseModel):
    cohort_month: str
    customers_total: int
    periods: List[CohortPeriod]


class CohortSummary(BaseModel):
    avg_retention_month_1: float
    best_cohort: str
    worst_cohort: str
    total_cohorts: int


class CohortAnalysisResponse(BaseModel):
    cohorts: List[CohortRow]
    summary: CohortSummary


@router.get("", response_model=CohortAnalysisResponse)
@check_billing_entitlement_decorator(BillingFeature.COHORT_ANALYSIS)
async def get_cohort_analysis(
    request: Request,
    timeframe: str = Query("12m", description="Lookback: 3m, 6m, 12m"),
    db=Depends(check_cohort_analysis_entitlement),
):
    """Return cohort retention grid for the heatmap."""
    tenant_ctx = get_tenant_context(request)

    # Map timeframe to months
    months_map = {"3m": 3, "6m": 6, "12m": 12}
    months_back = months_map.get(timeframe, 12)

    try:
        rows = db.execute(text("""
            SELECT cohort_month, period_number, customers_total,
                   customers_active, retention_rate, cohort_revenue, order_count
            FROM analytics.fct_cohort_retention
            WHERE tenant_id = :tenant_id
              AND cohort_month >= (current_date - make_interval(months => :months_back))::date
              AND period_number <= 12
            ORDER BY cohort_month, period_number
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "months_back": months_back,
        }).fetchall()

        # Group by cohort_month
        cohort_map: dict = {}
        for r in rows:
            key = r.cohort_month.isoformat() if hasattr(r.cohort_month, 'isoformat') else str(r.cohort_month)
            if key not in cohort_map:
                cohort_map[key] = {
                    "cohort_month": key,
                    "customers_total": int(r.customers_total),
                    "periods": [],
                }
            cohort_map[key]["periods"].append(CohortPeriod(
                period=int(r.period_number),
                retention_rate=float(r.retention_rate or 0),
                customers=int(r.customers_active),
                revenue=float(r.cohort_revenue or 0),
            ))

        cohorts = [CohortRow(**v) for v in cohort_map.values()]

        # Calculate summary
        month_1_rates = [
            p.retention_rate
            for c in cohorts
            for p in c.periods
            if p.period == 1
        ]
        avg_m1 = sum(month_1_rates) / len(month_1_rates) if month_1_rates else 0
        best = max(cohorts, key=lambda c: next((p.retention_rate for p in c.periods if p.period == 1), 0), default=None)
        worst = min(cohorts, key=lambda c: next((p.retention_rate for p in c.periods if p.period == 1), 0), default=None)

        summary = CohortSummary(
            avg_retention_month_1=round(avg_m1, 4),
            best_cohort=best.cohort_month if best else "",
            worst_cohort=worst.cohort_month if worst else "",
            total_cohorts=len(cohorts),
        )

        return CohortAnalysisResponse(cohorts=cohorts, summary=summary)

    except Exception as exc:
        logger.warning("Cohort analysis query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cohort data unavailable",
        )
