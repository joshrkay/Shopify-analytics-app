"""
Audit API routes for Story 8.7.

Provides endpoints for:
- Querying audit logs with filters
- Getting audit log summaries
- Querying safety events
- Getting current safety status

SECURITY:
- All routes require valid tenant context from JWT
- Logs are tenant-scoped - users only see their own
- Requires appropriate audit viewing permissions

Story 8.7 - Audit, Rollback & Accountability
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from sqlalchemy import func

from src.platform.tenant_context import get_tenant_context
from src.platform.audit import AuditLog
from src.services.audit_access_control import get_audit_access_control
from src.platform.audit_events import get_event_severity, EVENT_CATEGORIES
from src.platform.feature_flags import is_kill_switch_active, FeatureFlag
from src.database.session import get_db_session
from src.services.action_safety_service import AISafetyEvent, ActionSafetyService
from src.services.billing_entitlements import BillingEntitlementsService
from src.api.schemas.audit import (
    AuditLogEntry,
    AuditLogsResponse,
    AuditSummaryResponse,
    SafetyEventEntry,
    SafetyEventsResponse,
    SafetyStatusResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


# =============================================================================
# Audit Log Routes
# =============================================================================


@router.get(
    "/logs",
    response_model=AuditLogsResponse,
)
async def list_audit_logs(
    request: Request,
    db_session=Depends(get_db_session),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant (super admin/agency only)"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by event category"),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation ID"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    limit: int = Query(50, le=500, description="Maximum logs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Query audit logs with filters.

    Returns paginated audit log entries for accessible tenants.

    SECURITY:
    - Merchants see only their own tenant
    - Agency users see their allowed_tenants
    - Super admins see all tenants
    """
    access_control = get_audit_access_control(request)

    logger.info(
        "Audit logs query",
        extra={
            "tenant_id": access_control.context.tenant_id,
            "requested_tenant_id": tenant_id,
            "action": action,
            "resource_type": resource_type,
        },
    )

    # Build query with RBAC-based tenant filtering
    query = db_session.query(AuditLog)

    if tenant_id:
        # Explicit tenant requested - validate access
        access_control.validate_access(tenant_id, db_session=db_session)
        query = query.filter(AuditLog.tenant_id == tenant_id)
    else:
        # Auto-filter based on user's accessible tenants
        query = access_control.filter_query(query, AuditLog.tenant_id)

    # Apply filters
    if action:
        query = query.filter(AuditLog.action == action)

    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    if resource_id:
        query = query.filter(AuditLog.resource_id == resource_id)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    if correlation_id:
        query = query.filter(AuditLog.correlation_id == correlation_id)

    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)

    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    # Filter by category (expand to all actions in category)
    if category and category in EVENT_CATEGORIES:
        category_actions = EVENT_CATEGORIES[category]
        query = query.filter(AuditLog.action.in_(category_actions))

    # Filter by severity (need to look up which actions have this severity)
    if severity:
        # Get all actions with this severity from EVENT_SEVERITY
        from src.platform.audit_events import EVENT_SEVERITY
        severity_actions = [
            action_type for action_type, sev in EVENT_SEVERITY.items()
            if sev == severity
        ]
        if severity_actions:
            query = query.filter(AuditLog.action.in_(severity_actions))

    # Get total count
    total = query.count()

    # Get paginated results
    logs = (
        query
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )

    has_more = len(logs) > limit
    logs = logs[:limit]

    return AuditLogsResponse(
        logs=[
            AuditLogEntry(
                id=log.id,
                tenant_id=log.tenant_id,
                user_id=log.user_id,
                action=log.action,
                timestamp=log.timestamp,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                event_metadata=log.event_metadata or {},
                correlation_id=log.correlation_id,
            )
            for log in logs
        ],
        total=total,
        has_more=has_more,
    )


@router.get(
    "/logs/{log_id}",
    response_model=AuditLogEntry,
)
async def get_audit_log(
    request: Request,
    log_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get a single audit log entry.

    SECURITY: Only returns log if user has access to the log's tenant.
    """
    access_control = get_audit_access_control(request)

    # First fetch the log without tenant filter
    log = db_session.query(AuditLog).filter(AuditLog.id == log_id).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )

    # Validate access to this log's tenant
    access_control.validate_access(log.tenant_id, db_session=db_session)

    return AuditLogEntry(
        id=log.id,
        tenant_id=log.tenant_id,
        user_id=log.user_id,
        action=log.action,
        timestamp=log.timestamp,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        event_metadata=log.event_metadata or {},
        correlation_id=log.correlation_id,
    )


@router.get(
    "/summary",
    response_model=AuditSummaryResponse,
)
async def get_audit_summary(
    request: Request,
    db_session=Depends(get_db_session),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant (super admin/agency only)"),
    start_date: Optional[datetime] = Query(
        None, description="Start of date range (defaults to 7 days ago)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="End of date range (defaults to now)"
    ),
):
    """
    Get summary statistics for audit logs.

    Returns counts grouped by action, severity, and resource type.
    """
    access_control = get_audit_access_control(request)

    # Default date range: last 7 days
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=7)

    # Base query with RBAC filtering
    base_query = db_session.query(AuditLog)

    if tenant_id:
        access_control.validate_access(tenant_id, db_session=db_session)
        base_query = base_query.filter(AuditLog.tenant_id == tenant_id)
    else:
        base_query = access_control.filter_query(base_query, AuditLog.tenant_id)

    base_query = base_query.filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date,
    )

    # Total events
    total_events = base_query.count()

    # Group by action
    action_counts = (
        base_query
        .with_entities(AuditLog.action, func.count(AuditLog.id))
        .group_by(AuditLog.action)
        .all()
    )
    by_action = {action: count for action, count in action_counts}

    # Group by resource type
    resource_counts = (
        base_query
        .filter(AuditLog.resource_type.isnot(None))
        .with_entities(AuditLog.resource_type, func.count(AuditLog.id))
        .group_by(AuditLog.resource_type)
        .all()
    )
    by_resource_type = {rt: count for rt, count in resource_counts}

    # Calculate severity counts from action counts
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for action, count in by_action.items():
        severity = get_event_severity(action)
        by_severity[severity] = by_severity.get(severity, 0) + count

    return AuditSummaryResponse(
        total_events=total_events,
        by_action=by_action,
        by_severity=by_severity,
        by_resource_type=by_resource_type,
    )


@router.get(
    "/correlation/{correlation_id}",
    response_model=AuditLogsResponse,
)
async def get_correlated_logs(
    request: Request,
    correlation_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get all audit logs sharing a correlation ID.

    Useful for tracing request chains across services.

    SECURITY: Only returns logs for accessible tenants.
    """
    access_control = get_audit_access_control(request)

    # Build query with RBAC filtering
    query = db_session.query(AuditLog).filter(
        AuditLog.correlation_id == correlation_id,
    )
    query = access_control.filter_query(query, AuditLog.tenant_id)

    logs = query.order_by(AuditLog.timestamp.asc()).all()

    return AuditLogsResponse(
        logs=[
            AuditLogEntry(
                id=log.id,
                tenant_id=log.tenant_id,
                user_id=log.user_id,
                action=log.action,
                timestamp=log.timestamp,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                event_metadata=log.event_metadata or {},
                correlation_id=log.correlation_id,
            )
            for log in logs
        ],
        total=len(logs),
        has_more=False,
    )


# =============================================================================
# Safety Event Routes
# =============================================================================


@router.get(
    "/safety/events",
    response_model=SafetyEventsResponse,
)
async def list_safety_events(
    request: Request,
    db_session=Depends(get_db_session),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    limit: int = Query(50, le=500, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Query safety events (rate limits, cooldowns, blocked actions).

    Returns paginated safety events for the authenticated tenant.

    SECURITY: Only returns events belonging to the authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)

    query = db_session.query(AISafetyEvent).filter(
        AISafetyEvent.tenant_id == tenant_ctx.tenant_id
    )

    if event_type:
        query = query.filter(AISafetyEvent.event_type == event_type)

    if start_date:
        query = query.filter(AISafetyEvent.created_at >= start_date)

    if end_date:
        query = query.filter(AISafetyEvent.created_at <= end_date)

    total = query.count()

    events = (
        query
        .order_by(AISafetyEvent.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )

    has_more = len(events) > limit
    events = events[:limit]

    return SafetyEventsResponse(
        events=[
            SafetyEventEntry(
                id=str(event.id),
                tenant_id=event.tenant_id,
                event_type=event.event_type,
                operation_type=event.operation_type,
                entity_id=event.entity_id,
                action_id=event.action_id,
                reason=event.reason,
                metadata=event.event_metadata or {},
                correlation_id=event.correlation_id,
                created_at=event.created_at,
            )
            for event in events
        ],
        total=total,
        has_more=has_more,
    )


@router.get(
    "/safety/status",
    response_model=SafetyStatusResponse,
)
async def get_safety_status(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get current safety system status.

    Returns rate limit status, active cooldowns, and kill switch state.
    """
    tenant_ctx = get_tenant_context(request)

    # Get billing tier for rate limit lookup
    billing_service = BillingEntitlementsService(db_session, tenant_ctx.tenant_id)
    billing_tier = billing_service.get_billing_tier()

    # Create safety service to check status
    safety_service = ActionSafetyService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        billing_tier=billing_tier,
    )

    # Get rate limit status
    rate_limit_status = safety_service.get_rate_limit_status("action_execution")

    # Count active cooldowns
    from src.services.action_safety_service import AICooldown
    active_cooldowns = (
        db_session.query(func.count(AICooldown.id))
        .filter(
            AICooldown.tenant_id == tenant_ctx.tenant_id,
            AICooldown.cooldown_until > datetime.now(timezone.utc),
        )
        .scalar()
    ) or 0

    # Check kill switch
    kill_switch_active = await is_kill_switch_active(FeatureFlag.AI_WRITE_BACK)

    # Count recent blocked actions (last 24 hours)
    recent_blocked = (
        db_session.query(func.count(AISafetyEvent.id))
        .filter(
            AISafetyEvent.tenant_id == tenant_ctx.tenant_id,
            AISafetyEvent.event_type == "action_blocked",
            AISafetyEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
        )
        .scalar()
    ) or 0

    return SafetyStatusResponse(
        rate_limit_status={
            "count": rate_limit_status.count,
            "limit": rate_limit_status.limit,
            "remaining": rate_limit_status.remaining,
            "reset_at": rate_limit_status.reset_at.isoformat(),
            "is_limited": rate_limit_status.is_limited,
        },
        active_cooldowns=active_cooldowns,
        kill_switch_active=kill_switch_active,
        recent_blocked_count=recent_blocked,
    )
