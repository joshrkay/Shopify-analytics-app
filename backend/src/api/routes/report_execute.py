"""
Report Execute API route.

Provides the endpoint for executing a saved report's query with optional
parameters (date range, filters, row limit). This is used by the frontend
to load live data for saved dashboard widgets.

The preview endpoint (POST /api/datasets/preview) handles unsaved/wizard
reports. This endpoint handles saved reports by loading their config from
the database and executing via ChartQueryService.

SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, status
from pydantic import BaseModel, Field

from src.platform.tenant_context import get_tenant_context
from src.api.dependencies.entitlements import check_custom_reports_entitlement
from src.services.chart_query_service import ChartConfig, ChartQueryService, validate_viz_type
from src.models.custom_report import CustomReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["report-execute"])


# =============================================================================
# Request / Response Models
# =============================================================================


class ReportExecuteRequest(BaseModel):
    """Request body for executing a saved report."""

    date_range: str = Field("30", description="Date range: 7, 30, 90, or custom")
    filters: list[dict[str, Any]] = Field(default_factory=list, description="Additional filters")
    limit: int = Field(1000, ge=1, le=10000, description="Row limit (max 10000)")


class ReportExecuteResponse(BaseModel):
    """Response from executing a saved report."""

    data: list[dict[str, Any]] = Field(default_factory=list, description="Query result rows")
    columns: list[str] = Field(default_factory=list, description="Column names")
    row_count: int = Field(0, description="Number of rows returned")
    truncated: bool = Field(False, description="Whether results were truncated")
    query_duration_ms: Optional[float] = Field(None, description="Query execution time in ms")


# =============================================================================
# Helpers
# =============================================================================

_chart_query_service: Optional[ChartQueryService] = None


def _get_chart_query_service() -> ChartQueryService:
    """Lazy singleton for the chart query service."""
    global _chart_query_service
    if _chart_query_service is None:
        _chart_query_service = ChartQueryService()
    return _chart_query_service


# Map frontend date_range strings to Superset time range expressions
DATE_RANGE_MAP: dict[str, str] = {
    "7": "Last 7 days",
    "30": "Last 30 days",
    "90": "Last 90 days",
    "365": "Last 365 days",
}


# =============================================================================
# Route
# =============================================================================


@router.post(
    "/{report_id}/execute",
    response_model=ReportExecuteResponse,
)
async def execute_report(
    request: Request,
    report_id: str,
    body: ReportExecuteRequest,
    db_session=Depends(check_custom_reports_entitlement),
):
    """
    Execute a saved report's query with optional parameters.

    Loads the report's chart config from the database, merges with
    request parameters (date range, filters, limit), and executes
    via ChartQueryService.

    SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
    Report must belong to the requesting tenant (RLS enforced).
    """
    tenant_ctx = get_tenant_context(request)

    # Load the saved report (tenant-scoped)
    report = db_session.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.tenant_id == tenant_ctx.tenant_id,
    ).first()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    # Build ChartConfig from saved report config + request overrides
    config_json = report.config_json or {}

    time_range = DATE_RANGE_MAP.get(body.date_range, f"Last {body.date_range} days")

    # Merge saved filters with request filters (request filters take precedence)
    saved_filters = config_json.get("filters", [])
    merged_filters = saved_filters + body.filters

    # Resolve viz type from saved config
    viz_type = config_json.get("viz_type", report.chart_type or "line")
    try:
        resolved_viz = validate_viz_type(viz_type)
    except ValueError:
        resolved_viz = "echarts_timeseries_line"

    config = ChartConfig(
        dataset_name=report.dataset_name,
        metrics=config_json.get("metrics", []),
        dimensions=config_json.get("dimensions", []),
        filters=merged_filters,
        time_range=time_range,
        time_column=config_json.get("time_column"),
        time_grain=config_json.get("time_grain", "P1D"),
        viz_type=resolved_viz,
        row_limit=min(body.limit, 10000),
    )

    logger.info(
        "Report execute requested",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "report_id": report_id,
            "dataset_name": report.dataset_name,
            "date_range": body.date_range,
        },
    )

    service = _get_chart_query_service()

    try:
        result = service.execute_preview(config, tenant_ctx.tenant_id)
    except Exception as exc:
        logger.error(
            "Report execution failed",
            extra={"report_id": report_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report query failed — analytics engine unavailable",
        )

    return ReportExecuteResponse(
        data=result.data,
        columns=result.columns,
        row_count=result.row_count,
        truncated=result.truncated,
        query_duration_ms=result.query_duration_ms,
    )
