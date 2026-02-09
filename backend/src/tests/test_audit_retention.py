"""Tests for audit retention enforcement."""

from datetime import datetime, timedelta, timezone

from src.platform.audit import AuditLog
from src.workers.audit_retention_job import run_retention_cycle


def test_retention_deletes_old_logs(db_session):
    old_time = datetime.now(timezone.utc) - timedelta(days=120)
    recent_time = datetime.now(timezone.utc) - timedelta(days=1)

    old_log = AuditLog(
        id="old-log",
        tenant_id="tenant-1",
        user_id="user-1",
        action="auth.login_success",
        event_type="auth.login_success",
        timestamp=old_time,
        created_at=old_time,
        event_metadata={},
        correlation_id="corr-old",
        source="api",
        outcome="success",
    )
    recent_log = AuditLog(
        id="recent-log",
        tenant_id="tenant-1",
        user_id="user-1",
        action="auth.login_success",
        event_type="auth.login_success",
        timestamp=recent_time,
        created_at=recent_time,
        event_metadata={},
        correlation_id="corr-new",
        source="api",
        outcome="success",
    )

    db_session.add_all([old_log, recent_log])
    db_session.commit()

    deleted = run_retention_cycle(retention_days=90, db_session=db_session)

    assert deleted == 1
    remaining_ids = {log.id for log in db_session.query(AuditLog).all()}
    assert "old-log" not in remaining_ids
    assert "recent-log" in remaining_ids
