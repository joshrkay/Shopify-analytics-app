"""Audit log export service wrapper with access control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from src.platform.audit import (
    AuditAction,
    AuditExportFormat,
    AuditExportRequest,
    AuditExportResult,
    AuditExportService,
    AuditLog,
    AuditOutcome,
    log_system_audit_event_sync,
)
from src.services.audit_access_control import AuditAccessControl


@dataclass
class ExportFilters:
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    event_type: Optional[str] = None
    dashboard_id: Optional[str] = None


class AuditExporter:
    """Coordinates audit log exports with tenant scoping."""

    def __init__(self, db: Session, access_control: AuditAccessControl) -> None:
        self.db = db
        self.access_control = access_control
        self.export_service = AuditExportService(db)

    async def export_logs(
        self,
        *,
        tenant_id: Optional[str],
        export_format: AuditExportFormat,
        filters: ExportFilters,
        request_user_id: Optional[str],
        ip_address: Optional[str],
    ) -> AuditExportResult:
        scoped_tenant_id = self._resolve_tenant_scope(tenant_id)

        if scoped_tenant_id is not None:
            request = AuditExportRequest(
                tenant_id=scoped_tenant_id,
                format=export_format,
                start_date=filters.start_date,
                end_date=filters.end_date,
            )
            return await self.export_service.export_audit_logs(
                request=request,
                requesting_user_id=request_user_id,
                ip_address=ip_address,
            )

        return await self._export_all_tenants(
            export_format=export_format,
            filters=filters,
            request_user_id=request_user_id,
            ip_address=ip_address,
        )

    def _resolve_tenant_scope(self, tenant_id: Optional[str]) -> Optional[str]:
        if tenant_id:
            self.access_control.validate_access(tenant_id, db_session=self.db)
            return tenant_id

        if self.access_control.context.is_super_admin:
            return None

        return self.access_control.context.tenant_id

    async def _export_all_tenants(
        self,
        *,
        export_format: AuditExportFormat,
        filters: ExportFilters,
        request_user_id: Optional[str],
        ip_address: Optional[str],
    ) -> AuditExportResult:
        export_id = datetime.utcnow().strftime("global-%Y%m%d%H%M%S")
        tenant_key = "all"
        is_allowed, _ = self.export_service.check_rate_limit(tenant_key)
        if not is_allowed:
            log_system_audit_event_sync(
                db=self.db,
                tenant_id=tenant_key,
                action=AuditAction.EXPORT_FAILED,
                metadata={
                    "export_type": "audit_logs",
                    "error": "Rate limit exceeded",
                    "format": export_format.value,
                },
                outcome=AuditOutcome.DENIED,
                error_code="RATE_LIMIT_EXCEEDED",
            )
            return AuditExportResult(
                success=False,
                record_count=0,
                format=export_format,
                error="Rate limit exceeded. Maximum exports per day.",
                export_id=export_id,
            )

        query = self.db.query(AuditLog)
        if filters.start_date:
            query = query.filter(AuditLog.created_at >= filters.start_date)
        if filters.end_date:
            query = query.filter(AuditLog.created_at <= filters.end_date)
        if filters.event_type:
            query = query.filter(
                or_(AuditLog.event_type == filters.event_type, AuditLog.action == filters.event_type)
            )
        if filters.dashboard_id:
            query = query.filter(
                or_(AuditLog.dashboard_id == filters.dashboard_id, AuditLog.resource_id == filters.dashboard_id)
            )

        total_count = query.with_entities(func.count(AuditLog.id)).scalar() or 0

        if total_count > self.export_service.ASYNC_THRESHOLD_ROWS:
            log_system_audit_event_sync(
                db=self.db,
                tenant_id=tenant_key,
                action=AuditAction.EXPORT_REQUESTED,
                metadata={
                    "export_type": "audit_logs",
                    "format": export_format.value,
                    "record_count": total_count,
                    "export_id": export_id,
                    "async": True,
                },
                outcome=AuditOutcome.SUCCESS,
            )
            return AuditExportResult(
                success=True,
                record_count=total_count,
                format=export_format,
                export_id=export_id,
                is_async=True,
                error=f"Export queued for async processing ({total_count} records)",
            )

        log_system_audit_event_sync(
            db=self.db,
            tenant_id=tenant_key,
            action=AuditAction.EXPORT_REQUESTED,
            metadata={
                "export_type": "audit_logs",
                "format": export_format.value,
                "export_id": export_id,
            },
            outcome=AuditOutcome.SUCCESS,
        )

        logs = query.order_by(AuditLog.created_at.desc()).all()
        if export_format == AuditExportFormat.CSV:
            content = self.export_service.format_csv(logs)
        else:
            content = self.export_service.format_json(logs)

        log_system_audit_event_sync(
            db=self.db,
            tenant_id=tenant_key,
            action=AuditAction.EXPORT_COMPLETED,
            metadata={
                "export_type": "audit_logs",
                "format": export_format.value,
                "record_count": total_count,
                "export_id": export_id,
                "requested_by": request_user_id,
                "ip_address": ip_address,
            },
            outcome=AuditOutcome.SUCCESS,
        )

        self.export_service.record_export(tenant_key)

        return AuditExportResult(
            success=True,
            record_count=total_count,
            format=export_format,
            content=content,
            export_id=export_id,
        )
