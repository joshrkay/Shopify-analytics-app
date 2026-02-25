"""
Datasets API routes.

Provides endpoints for dataset discovery and chart preview:
- List available datasets with column metadata
- Get columns for a specific dataset
- Validate report config columns against current schema
- Execute chart preview queries with caching

SECURITY: All routes require valid tenant context from JWT.
Requires CUSTOM_REPORTS entitlement.

Phase 2A - Dataset Discovery API
Phase 2B - Chart Preview Backend
"""

import logging
from decimal import Decimal
from typing import Any, Optional, List

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context
from src.api.dependencies.entitlements import check_custom_reports_entitlement
from src.services.dataset_discovery_service import (
    DatasetDiscoveryService,
    ColumnMetadata,
    DatasetInfo,
)
from src.services.chart_query_service import (
    ChartConfig,
    ChartQueryService,
    ChartPreviewResult,
    validate_viz_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


# =============================================================================
# Response Models
# =============================================================================


class ColumnMetadataResponse(BaseModel):
    """Column metadata for chart builder filtering."""

    column_name: str = Field(..., description="Column name in the dataset")
    data_type: str = Field(..., description="SQL data type")
    description: str = Field("", description="Human-readable column description")
    is_metric: bool = Field(..., description="True if column can be used as a metric (SUM/AVG/etc)")
    is_dimension: bool = Field(..., description="True if column can be used as a dimension (GROUP BY)")
    is_temporal: bool = Field(..., description="True if column is a date/time type for time axes")


class DatasetResponse(BaseModel):
    """Response model for a single dataset."""

    dataset_name: str = Field(..., description="Table name in the warehouse")
    dataset_id: int = Field(..., description="Superset dataset ID")
    schema_name: str = Field(..., description="Database schema", alias="schema")
    description: str = Field("", description="Dataset description")
    columns: list[ColumnMetadataResponse] = Field(
        default_factory=list, description="Column metadata"
    )

    class Config:
        populate_by_name = True


class DatasetListResponse(BaseModel):
    """Response model for dataset list."""

    datasets: list[DatasetResponse] = Field(..., description="Available datasets")
    total: int = Field(..., description="Total dataset count")
    stale: bool = Field(False, description="True if data is from stale cache")
    cached_at: Optional[str] = Field(None, description="ISO timestamp when data was cached")


class ConfigWarningResponse(BaseModel):
    """Warning for a column referenced in config that no longer exists."""

    column_name: str = Field(..., description="Missing column name")
    dataset_name: str = Field(..., description="Dataset the column was expected in")
    message: str = Field(..., description="Human-readable warning message")


class ValidateConfigRequest(BaseModel):
    """Request to validate report config columns."""

    dataset_name: str = Field(..., description="Dataset name to validate against")
    referenced_columns: list[str] = Field(
        ..., description="Column names referenced in the report config"
    )


class ValidateConfigResponse(BaseModel):
    """Response with validation warnings."""

    valid: bool = Field(..., description="True if all columns exist")
    warnings: list[ConfigWarningResponse] = Field(
        default_factory=list, description="Warnings for missing columns"
    )


class ChartPreviewRequest(BaseModel):
    """Request to execute a chart preview query."""

    dataset_name: str = Field(..., description="Dataset to query")
    metrics: list[dict[str, Any]] = Field(..., description="Metrics to compute")
    dimensions: list[str] = Field(default_factory=list, description="GROUP BY dimensions")
    filters: list[dict[str, Any]] = Field(default_factory=list, description="Adhoc filters")
    time_range: str = Field("Last 30 days", description="Time range expression")
    time_column: Optional[str] = Field(None, description="Temporal column for time axis")
    time_grain: str = Field("P1D", description="Time grain (P1D, P1W, P1M, etc.)")
    viz_type: str = Field("line", description="Abstract chart type: line, bar, pie, table, etc.")


class ChartPreviewResponse(BaseModel):
    """Response from chart preview query."""

    data: list[dict[str, Any]] = Field(default_factory=list, description="Query result rows")
    columns: list[str] = Field(default_factory=list, description="Column names in result")
    row_count: int = Field(0, description="Number of rows returned")
    truncated: bool = Field(False, description="True if GROUP BY was truncated to max cardinality")
    message: Optional[str] = Field(None, description="Info or error message")
    query_duration_ms: Optional[float] = Field(None, description="Query execution time in ms")
    viz_type: str = Field("", description="Resolved Superset viz_type")


# =============================================================================
# Helpers
# =============================================================================

_discovery_service: Optional[DatasetDiscoveryService] = None
_chart_query_service: Optional[ChartQueryService] = None


def _get_discovery_service() -> DatasetDiscoveryService:
    """Lazy singleton for the discovery service."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = DatasetDiscoveryService()
    return _discovery_service


def _get_chart_query_service() -> ChartQueryService:
    """Lazy singleton for the chart query service."""
    global _chart_query_service
    if _chart_query_service is None:
        _chart_query_service = ChartQueryService()
    return _chart_query_service


def _column_to_response(col: ColumnMetadata) -> ColumnMetadataResponse:
    return ColumnMetadataResponse(
        column_name=col.column_name,
        data_type=col.data_type,
        description=col.description,
        is_metric=col.is_metric,
        is_dimension=col.is_dimension,
        is_temporal=col.is_temporal,
    )


def _dataset_to_response(ds: DatasetInfo) -> DatasetResponse:
    return DatasetResponse(
        dataset_name=ds.dataset_name,
        dataset_id=ds.dataset_id,
        schema=ds.schema,
        description=ds.description,
        columns=[_column_to_response(c) for c in ds.columns],
    )


# =============================================================================
# Routes
# =============================================================================


@router.get(
    "",
    response_model=DatasetListResponse,
)
async def list_datasets(
    request: Request,
    db_session=Depends(check_custom_reports_entitlement),
):
    """
    List available datasets with column metadata.

    Returns all datasets discoverable from Superset, with column-level
    type information (is_metric, is_dimension, is_temporal) for the
    chart builder to filter options per chart type.

    If Superset is unavailable, returns cached data with stale=True.

    SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
    """
    tenant_ctx = get_tenant_context(request)
    logger.info(
        "Dataset list requested",
        extra={"tenant_id": tenant_ctx.tenant_id},
    )

    service = _get_discovery_service()
    result = service.discover_datasets()

    return DatasetListResponse(
        datasets=[_dataset_to_response(ds) for ds in result.datasets],
        total=len(result.datasets),
        stale=result.stale,
        cached_at=result.cached_at,
    )


@router.get(
    "/{dataset_id}/columns",
    response_model=list[ColumnMetadataResponse],
)
async def get_dataset_columns(
    request: Request,
    dataset_id: int,
    db_session=Depends(check_custom_reports_entitlement),
):
    """
    Get column metadata for a specific dataset.

    Returns typed column information for the chart builder.
    Numeric columns can be metrics. String columns are dimensions only.
    DateTime columns can be time axes.

    SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
    """
    tenant_ctx = get_tenant_context(request)
    logger.info(
        "Dataset columns requested",
        extra={"tenant_id": tenant_ctx.tenant_id, "dataset_id": dataset_id},
    )

    service = _get_discovery_service()
    columns = service.get_dataset_columns(dataset_id)

    if not columns:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found or has no columns",
        )

    return [_column_to_response(c) for c in columns]


@router.post(
    "/validate-config",
    response_model=ValidateConfigResponse,
)
async def validate_config(
    request: Request,
    body: ValidateConfigRequest,
    db_session=Depends(check_custom_reports_entitlement),
):
    """
    Validate that columns referenced in a report config still exist.

    Returns warnings for missing columns rather than errors, so the
    frontend can show warning badges on affected report widgets.

    SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
    """
    tenant_ctx = get_tenant_context(request)
    logger.info(
        "Config validation requested",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "dataset_name": body.dataset_name,
            "column_count": len(body.referenced_columns),
        },
    )

    service = _get_discovery_service()
    result = service.discover_datasets()

    # Find the dataset
    target_ds = None
    for ds in result.datasets:
        if ds.dataset_name == body.dataset_name:
            target_ds = ds
            break

    if target_ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{body.dataset_name}' not found",
        )

    warnings = service.validate_config_columns(
        body.dataset_name,
        body.referenced_columns,
        target_ds.columns,
    )

    return ValidateConfigResponse(
        valid=len(warnings) == 0,
        warnings=[
            ConfigWarningResponse(
                column_name=w.column_name,
                dataset_name=w.dataset_name,
                message=w.message,
            )
            for w in warnings
        ],
    )


# =============================================================================
# Chart Preview Routes (Phase 2B)
# =============================================================================


@router.post(
    "/preview",
    response_model=ChartPreviewResponse,
)
async def chart_preview(
    request: Request,
    body: ChartPreviewRequest,
    db_session=Depends(check_custom_reports_entitlement),
):
    """
    Execute a chart preview query.

    Accepts a chart config, translates it to a Superset dataset query,
    and returns formatted data for frontend rendering.

    Constraints:
    - 100-row limit enforced
    - 10-second query timeout
    - Results cached for 60s keyed by (dataset_name, config_hash, tenant_id)
    - High-cardinality GROUP BY truncated to 100 unique values

    All column names are parameterized via Superset column references.
    No raw SQL interpolation.

    SECURITY: Requires valid tenant context and CUSTOM_REPORTS entitlement.
    """
    tenant_ctx = get_tenant_context(request)

    if not body.metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one metric is required",
        )

    try:
        resolved_viz = validate_viz_type(body.viz_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    logger.info(
        "Chart preview requested",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "dataset_name": body.dataset_name,
            "viz_type": body.viz_type,
            "metric_count": len(body.metrics),
            "dimension_count": len(body.dimensions),
        },
    )

    config = ChartConfig(
        dataset_name=body.dataset_name,
        metrics=body.metrics,
        dimensions=body.dimensions,
        filters=body.filters,
        time_range=body.time_range,
        time_column=body.time_column,
        time_grain=body.time_grain,
        viz_type=resolved_viz,
    )

    service = _get_chart_query_service()
    result = service.execute_preview(config, tenant_ctx.tenant_id)

    return ChartPreviewResponse(
        data=result.data,
        columns=result.columns,
        row_count=result.row_count,
        truncated=result.truncated,
        message=result.message,
        query_duration_ms=result.query_duration_ms,
        viz_type=result.viz_type,
    )


# =============================================================================
# KPI Summary — Overview Dashboard (no custom_reports entitlement required)
# =============================================================================

TIMEFRAME_TO_PERIOD: dict[str, str] = {
    "7days": "last_7_days",
    "thisWeek": "weekly",
    "30days": "last_30_days",
    "thisMonth": "monthly",
    "90days": "last_90_days",
    "thisQuarter": "quarterly",
}


class KpiMetric(BaseModel):
    value: float
    change_pct: Optional[float] = None


class ChannelBar(BaseModel):
    channel: str
    revenue: float
    spend: float


class KpiSummaryResponse(BaseModel):
    total_revenue: KpiMetric
    total_ad_spend: KpiMetric
    average_roas: KpiMetric
    total_conversions: KpiMetric
    total_clicks: KpiMetric
    avg_ctr: KpiMetric
    avg_conversion_rate: KpiMetric
    revenue_by_channel: List[ChannelBar]
    active_channels: int


@router.get(
    "/kpi-summary",
    response_model=KpiSummaryResponse,
)
async def get_kpi_summary(
    request: Request,
    timeframe: str = Query("30days", description="Timeframe: 7days, 30days, 90days, thisMonth, thisQuarter"),
    db_session=Depends(_get_db_for_kpi),
):
    """
    Aggregated KPI metrics for the Overview dashboard.

    No custom_reports entitlement required — available on all plans.
    Queries mart_marketing_metrics and mart_revenue_metrics directly.
    """
    tenant_ctx = get_tenant_context(request)
    period_type = TIMEFRAME_TO_PERIOD.get(timeframe, "last_30_days")

    try:
        # Marketing metrics (spend, ROAS, clicks, CTR, conversions, conv_rate)
        mkt_row = db_session.execute(text("""
            SELECT
                COALESCE(SUM(total_spend), 0)           AS total_spend,
                COALESCE(SUM(order_count), 0)            AS total_conversions,
                COALESCE(SUM(total_clicks), 0)           AS total_clicks,
                COALESCE(AVG(ctr), 0)                    AS avg_ctr,
                COALESCE(AVG(conversion_rate), 0)        AS avg_conversion_rate,
                COALESCE(AVG(gross_roas), 0)             AS avg_roas,
                COALESCE(SUM(total_spend_prior), 0)      AS prior_spend,
                COALESCE(SUM(order_count_prior), 0)      AS prior_conversions,
                COALESCE(SUM(total_clicks_prior), 0)     AS prior_clicks,
                COALESCE(AVG(ctr_prior), 0)              AS prior_ctr,
                COALESCE(AVG(conversion_rate_prior), 0)  AS prior_conv_rate,
                COALESCE(AVG(gross_roas_prior), 0)       AS prior_roas
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type}).fetchone()

        # Revenue metrics
        rev_row = db_session.execute(text("""
            SELECT
                COALESCE(SUM(total_gross_revenue), 0)       AS total_revenue,
                COALESCE(SUM(total_gross_revenue_prior), 0) AS prior_revenue
            FROM marts.mart_revenue_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type}).fetchone()

        # Per-channel revenue + spend for grouped bar chart
        channel_rows = db_session.execute(text("""
            SELECT
                COALESCE(platform, 'organic')         AS channel,
                COALESCE(SUM(total_gross_revenue), 0) AS revenue,
                COALESCE(SUM(total_spend), 0)          AS spend
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
            GROUP BY platform
            ORDER BY revenue DESC
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type}).fetchall()

        def _pct(current: float, prior: float) -> Optional[float]:
            if prior and prior != 0:
                return round((current - prior) / abs(prior) * 100, 1)
            return None

        rev = float(rev_row.total_revenue) if rev_row else 0.0
        prior_rev = float(rev_row.prior_revenue) if rev_row else 0.0
        spend = float(mkt_row.total_spend) if mkt_row else 0.0
        prior_spend = float(mkt_row.prior_spend) if mkt_row else 0.0
        roas = float(mkt_row.avg_roas) if mkt_row else 0.0
        prior_roas = float(mkt_row.prior_roas) if mkt_row else 0.0
        convs = float(mkt_row.total_conversions) if mkt_row else 0.0
        prior_convs = float(mkt_row.prior_conversions) if mkt_row else 0.0
        clicks = float(mkt_row.total_clicks) if mkt_row else 0.0
        prior_clicks = float(mkt_row.prior_clicks) if mkt_row else 0.0
        ctr = float(mkt_row.avg_ctr) if mkt_row else 0.0
        prior_ctr = float(mkt_row.prior_ctr) if mkt_row else 0.0
        conv_rate = float(mkt_row.avg_conversion_rate) if mkt_row else 0.0
        prior_conv_rate = float(mkt_row.prior_conv_rate) if mkt_row else 0.0

        channels = [
            ChannelBar(channel=r.channel, revenue=float(r.revenue), spend=float(r.spend))
            for r in channel_rows
        ]
        active_channels = len(set(r.channel for r in channel_rows if float(r.revenue) > 0 or float(r.spend) > 0))

        return KpiSummaryResponse(
            total_revenue=KpiMetric(value=rev, change_pct=_pct(rev, prior_rev)),
            total_ad_spend=KpiMetric(value=spend, change_pct=_pct(spend, prior_spend)),
            average_roas=KpiMetric(value=roas, change_pct=_pct(roas, prior_roas)),
            total_conversions=KpiMetric(value=convs, change_pct=_pct(convs, prior_convs)),
            total_clicks=KpiMetric(value=clicks, change_pct=_pct(clicks, prior_clicks)),
            avg_ctr=KpiMetric(value=ctr, change_pct=_pct(ctr, prior_ctr)),
            avg_conversion_rate=KpiMetric(value=conv_rate, change_pct=_pct(conv_rate, prior_conv_rate)),
            revenue_by_channel=channels,
            active_channels=active_channels,
        )

    except Exception as exc:
        logger.warning("KPI summary query failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Analytics data unavailable")


def _get_db_for_kpi(request: Request):
    """DB dependency without entitlement check — KPI is available on all plans."""
    from src.database.session import get_db_session as _get
    from src.platform.tenant_context import get_tenant_context as _ctx
    _ctx(request)  # validates JWT + tenant
    from src.database.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Channel Breakdown — Level 1 (all channels) + Level 2 (channel drill-down)
# =============================================================================

class ChannelBreakdownRow(BaseModel):
    rank: int
    channel: str
    display_name: str
    value: float
    pct_of_total: float


class ChannelBreakdownSummary(BaseModel):
    total: float
    active_channels: int
    bar_chart: List[ChannelBar]
    pie_chart: List[ChannelBreakdownRow]
    table: List[ChannelBreakdownRow]


class ProductRow(BaseModel):
    rank: int
    product_name: str
    revenue: float
    units_sold: int
    avg_price: float
    pct_of_channel: float


class DailyTrendPoint(BaseModel):
    date: str
    revenue: float


class ChannelDrilldownResponse(BaseModel):
    channel: str
    display_name: str
    total_revenue: float
    unique_products: int
    daily_trend: List[DailyTrendPoint]
    products: List[ProductRow]


CHANNEL_DISPLAY_NAMES: dict[str, str] = {
    "meta_ads": "Facebook Ads",
    "google_ads": "Google Ads",
    "tiktok_ads": "TikTok Ads",
    "snapchat_ads": "Snapchat Ads",
    "pinterest_ads": "Pinterest Ads",
    "twitter_ads": "Twitter Ads",
    "instagram_ads": "Instagram Ads",
    "organic": "Organic",
}


@router.get(
    "/channel-breakdown",
    response_model=ChannelBreakdownSummary,
)
async def get_channel_breakdown(
    request: Request,
    metric: str = Query("revenue", description="Metric: revenue, spend, roas, conversions"),
    timeframe: str = Query("30days"),
    db_session=Depends(_get_db_for_kpi),
):
    """
    Level-1 channel breakdown for KPI breakdown modals.
    Returns bar chart, pie chart, and ranked table for a given metric across all channels.
    No custom_reports entitlement required.
    """
    tenant_ctx = get_tenant_context(request)
    period_type = TIMEFRAME_TO_PERIOD.get(timeframe, "last_30_days")

    metric_col_map = {
        "revenue": "SUM(total_gross_revenue)",
        "spend": "SUM(total_spend)",
        "roas": "AVG(gross_roas)",
        "conversions": "SUM(order_count)",
    }
    if metric not in metric_col_map:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")

    agg_expr = metric_col_map[metric]

    try:
        rows = db_session.execute(text(f"""
            SELECT
                COALESCE(platform, 'organic') AS channel,
                COALESCE({agg_expr}, 0)        AS metric_value
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
            GROUP BY platform
            ORDER BY metric_value DESC
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type}).fetchall()

        total = sum(float(r.metric_value) for r in rows) if rows else 0.0
        active = len([r for r in rows if float(r.metric_value) > 0])

        table = []
        for i, r in enumerate(rows):
            val = float(r.metric_value)
            pct = round(val / total * 100, 1) if total else 0.0
            ch = r.channel
            table.append(ChannelBreakdownRow(
                rank=i + 1,
                channel=ch,
                display_name=CHANNEL_DISPLAY_NAMES.get(ch, ch.replace("_", " ").title()),
                value=val,
                pct_of_total=pct,
            ))

        bar = [ChannelBar(channel=r.channel, revenue=r.value, spend=0.0) for r in table]

        return ChannelBreakdownSummary(
            total=total,
            active_channels=active,
            bar_chart=bar,
            pie_chart=table,
            table=table,
        )

    except Exception as exc:
        logger.warning("Channel breakdown query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Analytics data unavailable")


@router.get(
    "/channel-breakdown/{channel}",
    response_model=ChannelDrilldownResponse,
)
async def get_channel_drilldown(
    channel: str,
    request: Request,
    timeframe: str = Query("30days"),
    db_session=Depends(_get_db_for_kpi),
):
    """
    Level-2 channel drill-down: daily revenue trend + top products for one channel.
    No custom_reports entitlement required.
    """
    tenant_ctx = get_tenant_context(request)
    period_type = TIMEFRAME_TO_PERIOD.get(timeframe, "last_30_days")
    display_name = CHANNEL_DISPLAY_NAMES.get(channel, channel.replace("_", " ").title())

    try:
        # Aggregate totals for this channel
        totals = db_session.execute(text("""
            SELECT
                COALESCE(SUM(total_gross_revenue), 0) AS total_revenue,
                COALESCE(SUM(order_count), 0)          AS total_orders
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = :period_type
              AND (platform = :channel OR (:channel = 'organic' AND platform IS NULL))
        """), {"tenant_id": tenant_ctx.tenant_id, "period_type": period_type, "channel": channel}).fetchone()

        # Daily trend from mart_revenue_metrics (or marketing metrics daily)
        trend_rows = db_session.execute(text("""
            SELECT
                DATE(period_start)                    AS day,
                COALESCE(SUM(total_gross_revenue), 0) AS revenue
            FROM marts.mart_marketing_metrics
            WHERE tenant_id = :tenant_id
              AND period_type = 'daily'
              AND (platform = :channel OR (:channel = 'organic' AND platform IS NULL))
            GROUP BY DATE(period_start)
            ORDER BY day ASC
            LIMIT 90
        """), {"tenant_id": tenant_ctx.tenant_id, "channel": channel}).fetchall()

        # Top products via attribution join (canonical orders + last_click)
        product_rows = db_session.execute(text("""
            SELECT
                COALESCE(o.title, 'Unknown Product')  AS product_name,
                COALESCE(SUM(o.price * li.quantity), 0) AS revenue,
                COALESCE(SUM(li.quantity), 0)          AS units_sold,
                COALESCE(AVG(o.price), 0)              AS avg_price
            FROM canonical.fact_orders_v1 fo
            JOIN canonical.order_line_items li ON li.order_id = fo.order_id
            JOIN canonical.products o ON o.product_id = li.product_id
            JOIN analytics.last_click lc ON lc.order_id = fo.order_id
            WHERE fo.tenant_id = :tenant_id
              AND (lc.platform = :channel OR (:channel = 'organic' AND lc.platform IS NULL))
            GROUP BY o.title
            ORDER BY revenue DESC
            LIMIT 10
        """), {"tenant_id": tenant_ctx.tenant_id, "channel": channel}).fetchall()

        total_rev = float(totals.total_revenue) if totals else 0.0
        unique_products = len(product_rows)

        trend = [
            DailyTrendPoint(date=str(r.day), revenue=float(r.revenue))
            for r in trend_rows
        ]

        products = []
        for i, r in enumerate(product_rows):
            rev = float(r.revenue)
            pct = round(rev / total_rev * 100, 1) if total_rev else 0.0
            products.append(ProductRow(
                rank=i + 1,
                product_name=r.product_name,
                revenue=rev,
                units_sold=int(r.units_sold),
                avg_price=float(r.avg_price),
                pct_of_channel=pct,
            ))

        return ChannelDrilldownResponse(
            channel=channel,
            display_name=display_name,
            total_revenue=total_rev,
            unique_products=unique_products,
            daily_trend=trend,
            products=products,
        )

    except Exception as exc:
        logger.warning("Channel drilldown query failed for %s: %s", channel, exc)
        raise HTTPException(status_code=503, detail="Analytics data unavailable")
