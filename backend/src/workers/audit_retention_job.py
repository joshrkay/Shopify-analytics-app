"""Audit log retention enforcement job."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.database.session import get_db_session_sync
from src.platform.audit import AuditAction, AuditLog, AuditOutcome, log_system_audit_event_sync

logger = logging.getLogger(__name__)


def run_retention_cycle(retention_days: int = 90, db_session=None) -> int:
    """Delete audit logs older than retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    db = db_session
    db_gen = None
    if db is None:
        db_gen = get_db_session_sync()
        db = next(db_gen)
    try:
        log_system_audit_event_sync(
            db=db,
            tenant_id="system",
            action=AuditAction.AUDIT_RETENTION_STARTED,
            metadata={"retention_days": retention_days, "cutoff": cutoff.isoformat()},
            outcome=AuditOutcome.SUCCESS,
        )
        deleted = (
            db.query(AuditLog)
            .filter(AuditLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        log_system_audit_event_sync(
            db=db,
            tenant_id="system",
            action=AuditAction.AUDIT_RETENTION_COMPLETED,
            metadata={"retention_days": retention_days, "deleted": deleted},
            outcome=AuditOutcome.SUCCESS,
        )
        db.commit()
        return deleted
    except Exception:
        db.rollback()
        logger.error("Audit retention job failed", exc_info=True)
        log_system_audit_event_sync(
            db=db,
            tenant_id="system",
            action=AuditAction.AUDIT_RETENTION_FAILED,
            metadata={"retention_days": retention_days},
            outcome=AuditOutcome.FAILURE,
        )
        db.commit()
        return 0
    finally:
        if db_gen is not None:
            db.close()
