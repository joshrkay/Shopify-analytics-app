"""
GA Audit Log Export API.

LOCKED RULES:
- Formats: CSV + JSON
- Rate-limited (3 exports per tenant per 24h)
- Tenant-scoped or global depending on role
- Async job for large exports (>10K rows)

Export attempts are themselves audited.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.platform.tenant_context import get_tenant_context
from src.constants.permissions import Role
from src.database.session import get_db_session
from src.services.audit_exporter import AuditExporterService, ExportFormat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit-logs/export", tags=["audit-export"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ExportResponse(BaseModel):
    """Export result."""
    export_id: str
    success: bool
    record_count: int
    format: str
    is_async: bool = False
    error: Optional[str] = None
    download_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def _check_export_access(request: Request) -> tuple[bool, str]:
    """
    Validate caller has export access (admin role required).

    Returns (is_super_admin, tenant_id).
    """
    tenant_ctx = get_tenant_context(request)

    is_super_admin = any(
        role.lower() == Role.SUPER_ADMIN.value
        for role in tenant_ctx.roles
    )

    is_admin = any(
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

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit export requires admin role",
        )

    return is_super_admin, tenant_ctx.tenant_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=ExportResponse)
async def export_audit_logs(
    request: Request,
    db_session=Depends(get_db_session),
    format: ExportFormat = Query(ExportFormat.CSV, description="Export format"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    dashboard_id: Optional[str] = Query(None, description="Filter by dashboard ID"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
):
    """
    Export GA audit logs to CSV or JSON.

    Rate-limited to 3 exports per tenant per 24 hours.
    Large exports (>10K rows) are queued for async processing.
    """
    is_super_admin, tenant_id = _check_export_access(request)

    service = AuditExporterService(db_session)
    result = service.export(
        tenant_id=tenant_id,
        fmt=format,
        is_super_admin=is_super_admin,
        event_type=event_type,
        dashboard_id=dashboard_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not result.success:
        if "rate limit" in (result.error or "").lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=result.error,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Export failed",
        )

    if result.is_async:
        return ExportResponse(
            export_id=result.export_id,
            success=True,
            record_count=result.record_count,
            format=result.format.value,
            is_async=True,
            download_url=f"/api/v1/audit-logs/export/{result.export_id}/download",
        )

    return ExportResponse(
        export_id=result.export_id,
        success=True,
        record_count=result.record_count,
        format=result.format.value,
        is_async=False,
    )


@router.post("/download", response_class=PlainTextResponse)
async def download_audit_export(
    request: Request,
    db_session=Depends(get_db_session),
    format: ExportFormat = Query(ExportFormat.CSV, description="Export format"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    dashboard_id: Optional[str] = Query(None, description="Filter by dashboard ID"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
):
    """
    Download audit logs directly as CSV or JSON content.

    Same rate limiting and access control as /export.
    Returns the file content directly.
    """
    is_super_admin, tenant_id = _check_export_access(request)

    service = AuditExporterService(db_session)
    result = service.export(
        tenant_id=tenant_id,
        fmt=format,
        is_super_admin=is_super_admin,
        event_type=event_type,
        dashboard_id=dashboard_id,
        start_date=start_date,
        end_date=end_date,
    )

    if not result.success:
        if "rate limit" in (result.error or "").lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=result.error,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Export failed",
        )

    if result.is_async:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="Export queued for async processing. Use /export endpoint.",
        )

    content_type = (
        "text/csv" if format == ExportFormat.CSV else "application/json"
    )
    return PlainTextResponse(
        content=result.content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=audit-logs.{format.value}"
            ),
        },
    )
