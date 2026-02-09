"""Audit log API endpoints (tenant-scoped)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.database.session import get_db_session
from src.constants.permissions import Role
from src.platform.tenant_context import get_tenant_context
from src.services.audit_access_control import get_audit_access_control
from src.services.audit_query_service import AuditQueryService

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit-logs"])


def _is_audit_admin(roles: list[str]) -> bool:
    return any(role == Role.MERCHANT_ADMIN.value for role in roles) or any(
        role == Role.SUPER_ADMIN.value for role in roles
    )


@router.get("")
async def list_audit_logs(
    request: Request,
    db_session=Depends(get_db_session),
    tenant_id: Optional[str] = Query(None, description="Tenant filter (super admin only)"),
    event_type: Optional[str] = Query(None, description="Audit event type"),
    dashboard_id: Optional[str] = Query(None, description="Dashboard ID"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    tenant_ctx = get_tenant_context(request)

    if not _is_audit_admin(tenant_ctx.roles):
        raise HTTPException(status_code=403, detail="Audit log access denied")

    access_control = get_audit_access_control(request)
    service = AuditQueryService(db_session)

    logs, total, has_more = service.list_logs(
        access_control,
        tenant_id=tenant_id,
        event_type=event_type,
        dashboard_id=dashboard_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return {
        "logs": [
            {
                "id": log.id,
                "event_type": log.event_type or log.action,
                "user_id": log.user_id,
                "tenant_id": log.tenant_id,
                "dashboard_id": log.dashboard_id,
                "access_surface": log.access_surface,
                "success": log.success,
                "metadata": log.event_metadata or {},
                "correlation_id": log.correlation_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "has_more": has_more,
    }
