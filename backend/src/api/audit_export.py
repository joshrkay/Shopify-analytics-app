"""Audit log export endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.constants.permissions import Role
from src.database.session import get_db_session
from src.platform.audit import AuditExportFormat
from src.platform.tenant_context import get_tenant_context
from src.services.audit_access_control import get_audit_access_control
from src.services.audit_exporter import AuditExporter, ExportFilters
from src.workers.audit_export_job import run_audit_export_job

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit-logs"])


class AuditExportRequestModel(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID for export")
    format: AuditExportFormat = Field(default=AuditExportFormat.CSV)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    event_type: Optional[str] = None
    dashboard_id: Optional[str] = None


def _is_audit_admin(roles: list[str]) -> bool:
    return any(role == Role.MERCHANT_ADMIN.value for role in roles) or any(
        role == Role.SUPER_ADMIN.value for role in roles
    )


@router.post("/export")
async def export_audit_logs(
    request: Request,
    payload: AuditExportRequestModel,
    background_tasks: BackgroundTasks,
    db_session=Depends(get_db_session),
):
    tenant_ctx = get_tenant_context(request)

    if not _is_audit_admin(tenant_ctx.roles):
        raise HTTPException(status_code=403, detail="Audit export denied")

    access_control = get_audit_access_control(request)
    exporter = AuditExporter(db_session, access_control)

    result = await exporter.export_logs(
        tenant_id=payload.tenant_id,
        export_format=payload.format,
        filters=ExportFilters(
            start_date=payload.start_date,
            end_date=payload.end_date,
            event_type=payload.event_type,
            dashboard_id=payload.dashboard_id,
        ),
        request_user_id=tenant_ctx.user_id,
        ip_address=request.client.host if request.client else None,
    )

    if result.is_async:
        background_tasks.add_task(
            run_audit_export_job,
            payload,
            tenant_ctx.user_id,
            request.client.host if request.client else None,
        )
        return {
            "export_id": result.export_id,
            "queued": True,
            "record_count": result.record_count,
            "message": result.error,
        }

    return {
        "export_id": result.export_id,
        "queued": False,
        "record_count": result.record_count,
        "format": result.format.value,
        "content": result.content,
    }
