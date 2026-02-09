"""
GA Audit Query Service — tenant-scoped audit log queries with filtering + pagination.

Access rules:
- Tenant Admin  → view logs for their tenant only
- Super Admin   → view all tenants
- Other users   → no access (403)

Supports filters: date range, event_type, dashboard_id
Pagination required on all list queries.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.audit_log import GAAuditLog, AuditEventType

logger = logging.getLogger(__name__)


class AuditQueryResult:
    """Paginated audit query result."""

    __slots__ = ("items", "total", "limit", "offset", "has_more")

    def __init__(
        self,
        items: list[GAAuditLog],
        total: int,
        limit: int,
        offset: int,
    ):
        self.items = items
        self.total = total
        self.limit = limit
        self.offset = offset
        self.has_more = (offset + limit) < total


class AuditQueryService:
    """
    Query GA audit logs with strict tenant scoping.

    All queries are filtered by tenant_id (or unrestricted for super admins).
    Pagination is mandatory — no unbounded result sets.
    """

    MAX_PAGE_SIZE = 500

    def __init__(self, db: Session):
        self.db = db

    def query_logs(
        self,
        *,
        tenant_id: Optional[str] = None,
        accessible_tenants: Optional[set[str]] = None,
        is_super_admin: bool = False,
        event_type: Optional[str] = None,
        dashboard_id: Optional[str] = None,
        user_id: Optional[str] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditQueryResult:
        """
        Query audit logs with filters and pagination.

        Args:
            tenant_id: Specific tenant to query (required unless super admin)
            accessible_tenants: Set of tenant IDs user can access (for agency)
            is_super_admin: If True, no tenant restriction applied
            event_type: Filter by event type
            dashboard_id: Filter by dashboard ID
            user_id: Filter by user ID
            success: Filter by success/failure
            start_date: Start of date range filter
            end_date: End of date range filter
            correlation_id: Filter by correlation ID
            limit: Page size (max 500)
            offset: Pagination offset

        Returns:
            AuditQueryResult with items, total count, pagination info
        """
        limit = min(limit, self.MAX_PAGE_SIZE)

        query = self.db.query(GAAuditLog)

        # Apply tenant scoping
        if not is_super_admin:
            if tenant_id:
                query = query.filter(GAAuditLog.tenant_id == tenant_id)
            elif accessible_tenants:
                if len(accessible_tenants) == 1:
                    query = query.filter(
                        GAAuditLog.tenant_id == list(accessible_tenants)[0]
                    )
                else:
                    query = query.filter(
                        GAAuditLog.tenant_id.in_(accessible_tenants)
                    )
            else:
                # No tenant access = empty result
                return AuditQueryResult(items=[], total=0, limit=limit, offset=offset)
        elif tenant_id:
            # Super admin with explicit tenant filter
            query = query.filter(GAAuditLog.tenant_id == tenant_id)

        # Apply filters
        if event_type:
            query = query.filter(GAAuditLog.event_type == event_type)
        if dashboard_id:
            query = query.filter(GAAuditLog.dashboard_id == dashboard_id)
        if user_id:
            query = query.filter(GAAuditLog.user_id == user_id)
        if success is not None:
            query = query.filter(GAAuditLog.success == success)
        if start_date:
            query = query.filter(GAAuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(GAAuditLog.created_at <= end_date)
        if correlation_id:
            query = query.filter(GAAuditLog.correlation_id == correlation_id)

        # Count total
        total = query.count()

        # Paginated results ordered by most recent first
        items = (
            query
            .order_by(GAAuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return AuditQueryResult(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def count_by_event_type(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, int]:
        """
        Count audit events grouped by event_type for a tenant.

        Returns dict of {event_type: count}.
        """
        query = (
            self.db.query(
                GAAuditLog.event_type,
                func.count(GAAuditLog.id),
            )
            .filter(GAAuditLog.tenant_id == tenant_id)
        )

        if start_date:
            query = query.filter(GAAuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(GAAuditLog.created_at <= end_date)

        results = query.group_by(GAAuditLog.event_type).all()
        return {event_type: count for event_type, count in results}

    def get_by_correlation_id(
        self,
        correlation_id: str,
        tenant_id: Optional[str] = None,
        is_super_admin: bool = False,
    ) -> list[GAAuditLog]:
        """
        Get all audit events sharing a correlation ID.

        Useful for tracing all events in a single request.
        """
        query = self.db.query(GAAuditLog).filter(
            GAAuditLog.correlation_id == correlation_id,
        )

        if not is_super_admin and tenant_id:
            query = query.filter(GAAuditLog.tenant_id == tenant_id)

        return query.order_by(GAAuditLog.created_at.asc()).all()
