"""
GA Audit Logs API — expose audit logs via REST with strict access control.

LOCKED RULES:
- Tenant Admin → view logs for their tenant only
- Super Admin  → view all tenants
- Other users  → no access (403)

ENDPOINTS:
- GET /api/v1/audit-logs          — list with filters + pagination
- GET /api/v1/audit-logs/{log_id} — single log entry

Supports filters: date range, event_type, dashboard_id
Pagination required on all list queries.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.platform.tenant_context import get_tenant_context
from src.constants.permissions import Role
from src.database.session import get_db_session
from src.models.audit_log import GAAuditLog
from src.services.audit_query_service import AuditQueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit-logs"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class AuditLogEntryResponse(BaseModel):
    """Single audit log entry."""
    id: str
    event_type: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    dashboard_id: Optional[str] = None
    access_surface: str
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    created_at: datetime


class AuditLogsListResponse(BaseModel):
    """Paginated list of audit log entries."""
    logs: list[AuditLogEntryResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


# ---------------------------------------------------------------------------
# Access control helpers
# ---------------------------------------------------------------------------

def _check_audit_access(request: Request) -> tuple[bool, str, set[str]]:
    """
    Validate caller has audit log access.

    Returns (is_super_admin, tenant_id, accessible_tenants).
    Raises 403 if user has no audit access.
    """
    tenant_ctx = get_tenant_context(request)

    # Check if super admin
    is_super_admin = any(
        role.lower() == Role.SUPER_ADMIN.value
        for role in tenant_ctx.roles
    )

    # Check if tenant admin
    is_tenant_admin = any(
        role.lower() in (
            Role.SUPER_ADMIN.value,
            "merchant_admin",
            "agency_admin",
            "admin",
            "owner",
            "org:admin",
        )
        for role in tenant_ctx.roles
    )

    if not is_tenant_admin and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit log access requires admin role",
        )

    accessible_tenants = set(tenant_ctx.allowed_tenants or [tenant_ctx.tenant_id])
    return is_super_admin, tenant_ctx.tenant_id, accessible_tenants


def _log_entry_from_row(row: GAAuditLog) -> AuditLogEntryResponse:
    """Convert a GAAuditLog row to API response model."""
    return AuditLogEntryResponse(
        id=row.id,
        event_type=row.event_type,
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        dashboard_id=row.dashboard_id,
        access_surface=row.access_surface,
        success=row.success,
        metadata=row.metadata or {},
        correlation_id=row.correlation_id,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=AuditLogsListResponse)
async def list_audit_logs(
    request: Request,
    db_session=Depends(get_db_session),
    tenant_id: Optional[str] = Query(
        None, description="Filter by tenant (super admin only)"
    ),
    event_type: Optional[str] = Query(
        None, description="Filter by event type (e.g. auth.login_success)"
    ),
    dashboard_id: Optional[str] = Query(
        None, description="Filter by dashboard ID"
    ),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    success: Optional[bool] = Query(None, description="Filter by success/failure"),
    start_date: Optional[datetime] = Query(
        None, description="Start of date range"
    ),
    end_date: Optional[datetime] = Query(
        None, description="End of date range"
    ),
    correlation_id: Optional[str] = Query(
        None, description="Filter by correlation ID"
    ),
    limit: int = Query(50, le=500, ge=1, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Query GA audit logs with filters and pagination.

    Access control:
    - Tenant Admin: sees own tenant's logs only
    - Super Admin: can filter across all tenants
    - Others: 403
    """
    is_super_admin, caller_tenant_id, accessible_tenants = _check_audit_access(request)

    # Non-super-admin requesting another tenant's logs → 403
    if tenant_id and not is_super_admin and tenant_id not in accessible_tenants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to tenant {tenant_id}",
        )

    # Default to caller's tenant for non-super-admins
    effective_tenant = tenant_id if is_super_admin else caller_tenant_id

    service = AuditQueryService(db_session)
    result = service.query_logs(
        tenant_id=effective_tenant if not is_super_admin or tenant_id else tenant_id,
        accessible_tenants=accessible_tenants if not is_super_admin else None,
        is_super_admin=is_super_admin,
        event_type=event_type,
        dashboard_id=dashboard_id,
        user_id=user_id,
        success=success,
        start_date=start_date,
        end_date=end_date,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset,
    )

    return AuditLogsListResponse(
        logs=[_log_entry_from_row(row) for row in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.get("/{log_id}", response_model=AuditLogEntryResponse)
async def get_audit_log(
    request: Request,
    log_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get a single audit log entry by ID.

    Access control: only returns log if caller can access the log's tenant.
    """
    is_super_admin, caller_tenant_id, accessible_tenants = _check_audit_access(request)

    row = db_session.query(GAAuditLog).filter(GAAuditLog.id == log_id).first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )

    # Validate tenant access
    if not is_super_admin and row.tenant_id not in accessible_tenants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this audit log",
        )

    return _log_entry_from_row(row)
