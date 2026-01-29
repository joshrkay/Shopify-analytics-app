"""
What Changed API routes for Story 9.8.

Read-only endpoints for the "What Changed?" debug panel.
Provides merchant-safe aggregated data about recent changes.

SECURITY:
- All endpoints are read-only (GET only)
- tenant_id from JWT only
- Never exposes raw logs, credentials, or sensitive data
- All data is aggregated into merchant-safe summaries

Story 9.8 - "What Changed?" Debug Panel
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, Query

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.data_change_aggregator import DataChangeAggregator
from src.api.schemas.what_changed import (
    DataChangeEventResponse,
    ChangeEventsListResponse,
    FreshnessStatusResponse,
    ConnectorFreshnessStatus,
    RecentSyncResponse,
    RecentSyncsListResponse,
    AIActionSummaryResponse,
    AIActionsListResponse,
    ConnectorStatusChangeResponse,
    ConnectorStatusChangesResponse,
    WhatChangedSummaryResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/what-changed", tags=["what-changed", "debug"])


# =============================================================================
# What Changed Debug Panel Routes (read-only)
# =============================================================================


@router.get(
    "",
    response_model=ChangeEventsListResponse,
)
async def list_change_events(
    request: Request,
    db_session=Depends(get_db_session),
    event_type: Optional[str] = Query(
        None,
        description="Filter by event type"
    ),
    connector_id: Optional[str] = Query(
        None,
        description="Filter by connector ID"
    ),
    metric: Optional[str] = Query(
        None,
        description="Filter by affected metric"
    ),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    limit: int = Query(50, le=100, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List aggregated data change events.

    Returns merchant-safe summaries of changes that may affect metrics.
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    events, total = aggregator.get_change_events(
        event_type=event_type,
        connector_id=connector_id,
        metric=metric,
        days=days,
        limit=limit,
        offset=offset,
    )

    has_more = offset + len(events) < total

    return ChangeEventsListResponse(
        events=[
            DataChangeEventResponse(
                id=event.id,
                event_type=event.event_type,
                title=event.title,
                description=event.description,
                affected_metrics=event.affected_metrics or [],
                affected_connector_name=event.affected_connector_name,
                impact_summary=event.impact_summary,
                affected_date_start=event.affected_date_start,
                affected_date_end=event.affected_date_end,
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
        total=total,
        has_more=has_more,
    )


@router.get(
    "/summary",
    response_model=WhatChangedSummaryResponse,
)
async def get_summary(
    request: Request,
    db_session=Depends(get_db_session),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
):
    """
    Get summary for the debug panel header.

    Returns at-a-glance overview of recent changes including:
    - Data freshness status
    - Recent sync count
    - Recent AI action count
    - Open incident count
    - Metric-affecting change count
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    summary = aggregator.get_summary(days=days)

    return WhatChangedSummaryResponse(
        data_freshness=FreshnessStatusResponse(
            overall_status=summary["data_freshness"]["overall_status"],
            last_sync_at=summary["data_freshness"]["last_sync_at"],
            hours_since_sync=summary["data_freshness"]["hours_since_sync"],
            connectors=[
                ConnectorFreshnessStatus(
                    connector_id=c["connector_id"],
                    connector_name=c["connector_name"],
                    status=c["status"],
                    last_sync_at=c["last_sync_at"],
                    minutes_since_sync=c["minutes_since_sync"],
                    source_type=c["source_type"],
                )
                for c in summary["data_freshness"]["connectors"]
            ],
        ),
        recent_syncs_count=summary["recent_syncs_count"],
        recent_ai_actions_count=summary["recent_ai_actions_count"],
        open_incidents_count=summary["open_incidents_count"],
        metric_changes_count=summary["metric_changes_count"],
        last_updated=summary["last_updated"],
    )


@router.get(
    "/freshness",
    response_model=FreshnessStatusResponse,
)
async def get_freshness_status(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get data freshness status.

    Returns overall freshness status and per-connector breakdown.
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    freshness = aggregator.get_freshness_status()

    return FreshnessStatusResponse(
        overall_status=freshness["overall_status"],
        last_sync_at=freshness["last_sync_at"],
        hours_since_sync=freshness["hours_since_sync"],
        connectors=[
            ConnectorFreshnessStatus(
                connector_id=c["connector_id"],
                connector_name=c["connector_name"],
                status=c["status"],
                last_sync_at=c["last_sync_at"],
                minutes_since_sync=c["minutes_since_sync"],
                source_type=c["source_type"],
            )
            for c in freshness["connectors"]
        ],
    )


@router.get(
    "/recent-syncs",
    response_model=RecentSyncsListResponse,
)
async def get_recent_syncs(
    request: Request,
    db_session=Depends(get_db_session),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    limit: int = Query(20, le=50, description="Maximum syncs to return"),
):
    """
    Get recent sync activity.

    Returns sync completions and failures with sanitized error messages.
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    syncs = aggregator.get_recent_syncs(days=days, limit=limit)

    return RecentSyncsListResponse(
        syncs=[
            RecentSyncResponse(
                sync_id=s["sync_id"],
                connector_id=s["connector_id"],
                connector_name=s["connector_name"],
                source_type=s["source_type"],
                status=s["status"],
                started_at=s["started_at"],
                completed_at=s["completed_at"],
                rows_synced=s["rows_synced"],
                duration_seconds=s["duration_seconds"],
                error_message=s["error_message"],
            )
            for s in syncs
        ],
        total=len(syncs),
    )


@router.get(
    "/ai-actions",
    response_model=AIActionsListResponse,
)
async def get_ai_actions(
    request: Request,
    db_session=Depends(get_db_session),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    limit: int = Query(20, le=50, description="Maximum actions to return"),
):
    """
    Get recent AI action activity.

    Returns AI actions that were approved, rejected, or executed.
    User identities are anonymized (e.g., "Admin user").
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    actions = aggregator.get_ai_actions_summary(days=days, limit=limit)

    return AIActionsListResponse(
        actions=[
            AIActionSummaryResponse(
                action_id=a["action_id"],
                action_type=a["action_type"],
                status=a["status"],
                target_name=a["target_name"],
                target_platform=a["target_platform"],
                performed_at=a["performed_at"],
                performed_by=a["performed_by"],
            )
            for a in actions
        ],
        total=len(actions),
    )


@router.get(
    "/connector-status",
    response_model=ConnectorStatusChangesResponse,
)
async def get_connector_status_changes(
    request: Request,
    db_session=Depends(get_db_session),
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
):
    """
    Get recent connector status changes.

    Returns status transitions (e.g., active -> failed) with sanitized reasons.
    """
    tenant_ctx = get_tenant_context(request)

    aggregator = DataChangeAggregator(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
    )

    changes = aggregator.get_connector_status_changes(days=days)

    return ConnectorStatusChangesResponse(
        changes=[
            ConnectorStatusChangeResponse(
                connector_id=c["connector_id"],
                connector_name=c["connector_name"],
                previous_status=c["previous_status"],
                new_status=c["new_status"],
                changed_at=c["changed_at"],
                reason=c["reason"],
            )
            for c in changes
        ],
        total=len(changes),
    )
