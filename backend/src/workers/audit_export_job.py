"""Background job for audit log exports."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.database.session import get_db_session_sync
from src.platform.audit import AuditExportFormat
from src.services.audit_access_control import AuditAccessContext, AuditAccessControl
from src.services.audit_exporter import AuditExporter, ExportFilters

logger = logging.getLogger(__name__)


@dataclass
class AuditExportJobPayload:
    tenant_id: Optional[str]
    format: AuditExportFormat
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    event_type: Optional[str]
    dashboard_id: Optional[str]


def run_audit_export_job(
    payload,
    requesting_user_id: Optional[str],
    ip_address: Optional[str],
) -> None:
    """Execute audit export asynchronously."""
    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        job_payload = _normalize_payload(payload)
        access_context = AuditAccessContext(
            user_id=requesting_user_id or "system",
            role="system",
            tenant_id=job_payload.tenant_id or "system",
            allowed_tenants=set(),
            is_super_admin=True,
        )
        access_control = AuditAccessControl(access_context)
        exporter = AuditExporter(db, access_control)
        import asyncio

        asyncio.run(
            exporter.export_logs(
                tenant_id=job_payload.tenant_id,
                export_format=job_payload.format,
                filters=ExportFilters(
                    start_date=job_payload.start_date,
                    end_date=job_payload.end_date,
                    event_type=job_payload.event_type,
                    dashboard_id=job_payload.dashboard_id,
                ),
                request_user_id=requesting_user_id,
                ip_address=ip_address,
            )
        )
    except Exception:
        logger.error("Audit export job failed", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _normalize_payload(payload) -> AuditExportJobPayload:
    if isinstance(payload, AuditExportJobPayload):
        return payload

    data = payload.dict() if hasattr(payload, "dict") else payload
    return AuditExportJobPayload(
        tenant_id=data.get("tenant_id"),
        format=AuditExportFormat(data.get("format")),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        event_type=data.get("event_type"),
        dashboard_id=data.get("dashboard_id"),
    )
