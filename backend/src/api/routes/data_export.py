"""
General Data Export API routes.

Provides CSV/JSON export of analytics data from dbt models:
- Orders (canonical.orders)
- Marketing metrics (marts.mart_marketing_metrics)
- Marketing spend (analytics.marketing_spend)
- Attribution (attribution.last_click)

Supports:
- On-demand export with format selection
- Row limits based on billing tier
- Rate limiting per tenant
- Google Sheets export (Pro+ tiers)

Entitlement: DATA_EXPORT (Growth+), SHEETS_EXPORT (Growth+), SCHEDULED_EXPORTS (Pro+)
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.billing_entitlements import (
    BillingEntitlementsService,
    BillingFeature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exports", tags=["data-export"])


# =============================================================================
# Request/Response Models
# =============================================================================

class DataExportRequest(BaseModel):
    """Request body for triggering a data export."""

    dataset: str
    """Dataset to export: 'orders', 'marketing_metrics', 'marketing_spend', 'attribution'."""

    format: str = "csv"
    """Export format: 'csv' or 'json'."""

    date_from: Optional[str] = None
    """Start date filter (ISO format)."""

    date_to: Optional[str] = None
    """End date filter (ISO format)."""

    limit: Optional[int] = None
    """Max rows to export. Capped by billing tier."""


class DataExportResponse(BaseModel):
    """Response from a data export request."""

    export_id: str
    success: bool
    record_count: int
    format: str
    error: Optional[str] = None


class ExportDatasetInfo(BaseModel):
    """Information about an available export dataset."""

    id: str
    name: str
    description: str
    columns: List[str]


class AvailableDatasetsResponse(BaseModel):
    """Response listing available datasets for export."""

    datasets: List[ExportDatasetInfo]


class SheetsExportRequest(BaseModel):
    """Request body for Google Sheets export."""

    dataset: str
    """Dataset to export."""

    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: Optional[int] = 10000
    spreadsheet_name: Optional[str] = None
    """Name for the new Google Sheet. Auto-generated if not provided."""


class SheetsExportResponse(BaseModel):
    """Response from Google Sheets export."""

    success: bool
    spreadsheet_url: Optional[str] = None
    spreadsheet_id: Optional[str] = None
    record_count: int = 0
    error: Optional[str] = None


# =============================================================================
# Available datasets
# =============================================================================

AVAILABLE_DATASETS = {
    "orders": ExportDatasetInfo(
        id="orders",
        name="Orders",
        description="Order data with revenue, status, and attribution",
        columns=[
            "order_id", "order_name", "order_number", "order_created_at",
            "financial_status", "revenue_gross", "tenant_id",
        ],
    ),
    "marketing_metrics": ExportDatasetInfo(
        id="marketing_metrics",
        name="Marketing Metrics",
        description="Pre-aggregated marketing KPIs by platform and period",
        columns=[
            "platform", "period_type", "period_start", "period_end",
            "spend", "orders", "gross_revenue", "gross_roas",
        ],
    ),
    "marketing_spend": ExportDatasetInfo(
        id="marketing_spend",
        name="Marketing Spend",
        description="Daily ad spend by platform with performance metrics",
        columns=[
            "source_platform", "date", "clicks", "impressions",
            "ctr", "conversions", "spend",
        ],
    ),
    "attribution": ExportDatasetInfo(
        id="attribution",
        name="Attribution",
        description="Last-click attribution data with UTM fields",
        columns=[
            "order_id", "order_created_at", "attribution_status",
            "revenue", "platform", "utm_source", "utm_medium", "utm_campaign",
        ],
    ),
}

# Maps dataset ID to the actual table in the dbt schema
DATASET_TO_TABLE = {
    "orders": "canonical.orders",
    "marketing_metrics": "marts.mart_marketing_metrics",
    "marketing_spend": "analytics.marketing_spend",
    "attribution": "attribution.last_click",
}

# Rate limit: exports per tenant per 24h
EXPORT_RATE_LIMIT = 10

# In-memory rate limit tracking (production should use Redis)
_export_counts: dict[str, list[datetime]] = {}


def _check_rate_limit(tenant_id: str) -> bool:
    """Check if tenant has exceeded export rate limit."""
    now = datetime.now(timezone.utc)
    key = tenant_id
    if key not in _export_counts:
        _export_counts[key] = []

    # Remove entries older than 24h
    _export_counts[key] = [
        t for t in _export_counts[key]
        if (now - t).total_seconds() < 86400
    ]

    if len(_export_counts[key]) >= EXPORT_RATE_LIMIT:
        return False

    _export_counts[key].append(now)
    return True


def _get_row_limit(billing_tier: str, requested_limit: Optional[int]) -> int:
    """Get the effective row limit based on billing tier."""
    tier_limits = {
        "free": 100,
        "growth": 10_000,
        "pro": 100_000,
        "enterprise": 1_000_000,
    }
    max_rows = tier_limits.get(billing_tier, 100)
    if requested_limit and requested_limit > 0:
        return min(requested_limit, max_rows)
    return max_rows


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "/datasets",
    response_model=AvailableDatasetsResponse,
)
async def list_export_datasets(request: Request):
    """List available datasets for export."""
    get_tenant_context(request)
    return AvailableDatasetsResponse(
        datasets=list(AVAILABLE_DATASETS.values())
    )


@router.post(
    "/data",
    response_model=DataExportResponse,
)
async def export_data(
    request: Request,
    body: DataExportRequest,
    db_session=Depends(get_db_session),
):
    """
    Export analytics data as CSV or JSON.

    Requires DATA_EXPORT entitlement (Growth+ tiers).
    Row count is capped by billing tier.
    Rate limited to 10 exports per tenant per 24 hours.
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    # Check entitlement
    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.DATA_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Data export requires a {result.required_tier} plan",
        )

    # Validate dataset
    if body.dataset not in AVAILABLE_DATASETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown dataset: {body.dataset}. Available: {list(AVAILABLE_DATASETS.keys())}",
        )

    if body.format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be 'csv' or 'json'",
        )

    # Rate limit
    if not _check_rate_limit(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Export rate limit exceeded. Maximum 10 exports per 24 hours.",
        )

    # Get row limit
    billing_tier = entitlements.get_billing_tier()
    row_limit = _get_row_limit(billing_tier, body.limit)

    # Build query
    table = DATASET_TO_TABLE[body.dataset]
    dataset_info = AVAILABLE_DATASETS[body.dataset]
    columns = ", ".join(dataset_info.columns)

    export_id = str(uuid.uuid4())

    try:
        from sqlalchemy import text

        query = f"SELECT {columns} FROM {table} WHERE tenant_id = :tenant_id"
        params = {"tenant_id": tenant_id}

        if body.date_from:
            query += " AND created_at >= :date_from"
            params["date_from"] = body.date_from

        if body.date_to:
            query += " AND created_at <= :date_to"
            params["date_to"] = body.date_to

        query += f" LIMIT :row_limit"
        params["row_limit"] = row_limit

        result = db_session.execute(text(query), params)
        rows = result.fetchall()
        column_names = list(result.keys())

        logger.info(
            "Data export completed",
            extra={
                "tenant_id": tenant_id,
                "dataset": body.dataset,
                "format": body.format,
                "row_count": len(rows),
                "export_id": export_id,
            },
        )

        if body.format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(column_names)
            for row in rows:
                writer.writerow([str(v) if v is not None else "" for v in row])
            return PlainTextResponse(
                content=output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{body.dataset}_{export_id[:8]}.csv"',
                    "X-Export-Id": export_id,
                    "X-Record-Count": str(len(rows)),
                },
            )
        else:
            data = [dict(zip(column_names, [str(v) if v is not None else None for v in row])) for row in rows]
            return JSONResponse(
                content={
                    "export_id": export_id,
                    "dataset": body.dataset,
                    "record_count": len(data),
                    "data": data,
                },
                headers={
                    "X-Export-Id": export_id,
                    "X-Record-Count": str(len(data)),
                },
            )

    except Exception as exc:
        logger.error(
            "Data export failed",
            extra={
                "tenant_id": tenant_id,
                "dataset": body.dataset,
                "error": str(exc),
                "export_id": export_id,
            },
        )
        return DataExportResponse(
            export_id=export_id,
            success=False,
            record_count=0,
            format=body.format,
            error="Export failed. Please try again.",
        )


@router.post(
    "/sheets",
    response_model=SheetsExportResponse,
)
async def export_to_sheets(
    request: Request,
    body: SheetsExportRequest,
    db_session=Depends(get_db_session),
):
    """
    Export analytics data to a new Google Sheet.

    Requires SHEETS_EXPORT entitlement (Growth+ tiers).
    Requires the tenant to have connected Google via OAuth.
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    # Check entitlement
    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.SHEETS_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Google Sheets export requires a {result.required_tier} plan",
        )

    if body.dataset not in AVAILABLE_DATASETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown dataset: {body.dataset}",
        )

    # Google Sheets export is a future enhancement — return a clear message
    return SheetsExportResponse(
        success=False,
        record_count=0,
        error="Google Sheets export is coming soon. Please use CSV export for now.",
    )
