"""Audit log query service with tenant scoping."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.platform.audit import AuditLog
from src.services.audit_access_control import AuditAccessControl


class AuditQueryService:
    """Query audit logs with access control and filters."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_logs(
        self,
        access_control: AuditAccessControl,
        *,
        tenant_id: Optional[str],
        event_type: Optional[str],
        dashboard_id: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int, bool]:
        query = self.db.query(AuditLog)

        if tenant_id:
            access_control.validate_access(tenant_id, db_session=self.db)
            query = query.filter(AuditLog.tenant_id == tenant_id)
        else:
            query = access_control.filter_query(query, AuditLog.tenant_id)

        if event_type:
            query = query.filter(
                or_(AuditLog.event_type == event_type, AuditLog.action == event_type)
            )

        if dashboard_id:
            query = query.filter(
                or_(AuditLog.dashboard_id == dashboard_id, AuditLog.resource_id == dashboard_id)
            )

        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)

        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)

        total = query.count()
        logs = (
            query.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
            .all()
        )

        has_more = len(logs) > limit
        logs = logs[:limit]
        return logs, total, has_more
