"""Tests for audit log access control via query service."""

from datetime import datetime, timezone

from src.platform.audit import AuditLog
from src.services.audit_access_control import AuditAccessContext, AuditAccessControl
from src.services.audit_query_service import AuditQueryService


def _create_log(db_session, tenant_id: str, event_type: str) -> None:
    log = AuditLog(
        id=f"log-{tenant_id}",
        tenant_id=tenant_id,
        user_id="user-1",
        action=event_type,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        event_metadata={},
        correlation_id=f"corr-{tenant_id}",
        source="api",
        outcome="success",
    )
    db_session.add(log)
    db_session.commit()


def test_tenant_scoped_logs(db_session):
    _create_log(db_session, "tenant-a", "auth.login_success")
    _create_log(db_session, "tenant-b", "auth.login_success")

    access_context = AuditAccessContext(
        user_id="user-1",
        role="merchant_admin",
        tenant_id="tenant-a",
        allowed_tenants=set(),
        is_super_admin=False,
    )
    access_control = AuditAccessControl(access_context)
    service = AuditQueryService(db_session)

    logs, total, has_more = service.list_logs(
        access_control,
        tenant_id=None,
        event_type=None,
        dashboard_id=None,
        start_date=None,
        end_date=None,
        limit=10,
        offset=0,
    )

    assert total == 1
    assert has_more is False
    assert logs[0].tenant_id == "tenant-a"
