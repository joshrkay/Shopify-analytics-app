"""
Credential cleanup job — Render cron job for hard-deleting expired credentials.

Runs daily to permanently wipe credentials past their 20-day hard-delete
deadline. Delegates actual purge to CredentialVault.purge_expired().

Lifecycle:
- Day 0: Source disconnected → credentials soft-deleted (status=REVOKED)
- Day 0–5: Restorable via CredentialVault.restore()
- Day 5–20: No longer restorable, but payload still encrypted in DB
- Day 20+: This job wipes encrypted_payload and deletes the row

CONSTRAINTS:
- Operates cross-tenant (no tenant_id scoping)
- Respects CREDENTIAL_CLEANUP_DRY_RUN for safe rollout
- All deletions are audit-logged
- Ingestion logs are retained per retention policy (not deleted here)

Run as a daily cron job:
    python -m src.workers.credential_cleanup_job

Deployed as a Render cron job in render.yaml.
"""

import os
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configurable via environment variables
CREDENTIAL_CLEANUP_DRY_RUN = (
    os.getenv("CREDENTIAL_CLEANUP_DRY_RUN", "true").lower() == "true"
)


@dataclass
class CleanupStats:
    """Statistics from a credential cleanup run."""

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    credentials_eligible: int = 0
    credentials_purged: int = 0
    dry_run: bool = CREDENTIAL_CLEANUP_DRY_RUN
    errors: list = field(default_factory=list)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        duration = None
        if self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "credentials_eligible": self.credentials_eligible,
            "credentials_purged": self.credentials_purged,
            "dry_run": self.dry_run,
            "error_count": len(self.errors),
            "duration_seconds": duration,
        }


def _get_database_session() -> Session:
    """Create database session for cleanup job."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    return session_factory()


def count_eligible_credentials(db_session: Session) -> int:
    """
    Count credentials eligible for hard deletion.

    Returns the number of soft-deleted credentials past their
    hard_delete_after deadline.
    """
    from src.models.connector_credential import ConnectorCredential

    now = datetime.now(timezone.utc)
    stmt = (
        select(func.count())
        .select_from(ConnectorCredential)
        .where(ConnectorCredential.hard_delete_after.isnot(None))
        .where(ConnectorCredential.hard_delete_after <= now)
        .where(ConnectorCredential.soft_deleted_at.isnot(None))
    )
    return db_session.execute(stmt).scalar() or 0


def run_cleanup(db_session: Session, dry_run: bool = CREDENTIAL_CLEANUP_DRY_RUN) -> CleanupStats:
    """
    Execute credential cleanup.

    Finds and permanently deletes credentials past their hard_delete_after
    deadline. Logs audit events for compliance.

    Args:
        db_session: Database session (not tenant-scoped)
        dry_run: If True, only count without deleting

    Returns:
        CleanupStats with results
    """
    stats = CleanupStats(dry_run=dry_run)

    # Log job start
    _log_cleanup_audit(db_session, "started", stats)

    try:
        # Count eligible credentials
        stats.credentials_eligible = count_eligible_credentials(db_session)

        if stats.credentials_eligible == 0:
            logger.info("No credentials eligible for cleanup")
            stats.completed_at = datetime.now(timezone.utc)
            _log_cleanup_audit(db_session, "completed", stats)
            return stats

        logger.info(
            "Credentials eligible for cleanup",
            extra={"count": stats.credentials_eligible, "dry_run": dry_run},
        )

        if dry_run:
            logger.info(
                "[DRY RUN] Would purge %d credentials",
                stats.credentials_eligible,
            )
            stats.credentials_purged = 0
            stats.completed_at = datetime.now(timezone.utc)
            _log_cleanup_audit(db_session, "completed", stats)
            return stats

        # Delegate actual purge to CredentialVault
        from src.services.credential_vault import CredentialVault

        purged = CredentialVault.purge_expired(db_session)
        stats.credentials_purged = purged

        logger.info(
            "Credential cleanup completed",
            extra={
                "eligible": stats.credentials_eligible,
                "purged": purged,
            },
        )

        stats.completed_at = datetime.now(timezone.utc)
        _log_cleanup_audit(db_session, "completed", stats)
        return stats

    except Exception as exc:
        error_msg = f"Credential cleanup failed: {exc}"
        stats.errors.append(error_msg)
        stats.completed_at = datetime.now(timezone.utc)
        logger.error(error_msg, exc_info=True)
        _log_cleanup_audit(db_session, "failed", stats)
        raise


def _log_cleanup_audit(
    db_session: Session,
    phase: str,
    stats: CleanupStats,
) -> None:
    """Log cleanup audit event. Failures are caught and logged."""
    try:
        from src.platform.audit import (
            AuditAction,
            AuditOutcome,
            log_system_audit_event_sync,
        )

        action_map = {
            "started": AuditAction.AUDIT_RETENTION_STARTED,
            "completed": AuditAction.AUDIT_RETENTION_COMPLETED,
            "failed": AuditAction.AUDIT_RETENTION_FAILED,
        }

        outcome_map = {
            "started": AuditOutcome.SUCCESS,
            "completed": AuditOutcome.SUCCESS,
            "failed": AuditOutcome.FAILURE,
        }

        log_system_audit_event_sync(
            db=db_session,
            tenant_id="system",
            action=action_map[phase],
            resource_type="credential_cleanup",
            metadata={
                "phase": phase,
                "job_type": "credential_cleanup",
                **stats.to_dict(),
            },
            source="worker",
            outcome=outcome_map[phase],
        )

    except Exception as exc:
        logger.error(
            "Failed to log cleanup audit event",
            extra={"phase": phase, "error": str(exc)},
        )


def main():
    """Entry point for credential cleanup job."""
    logger.info(
        "Credential Cleanup Job starting",
        extra={"dry_run": CREDENTIAL_CLEANUP_DRY_RUN},
    )

    session = _get_database_session()
    try:
        stats = run_cleanup(session, dry_run=CREDENTIAL_CLEANUP_DRY_RUN)
        logger.info("Credential Cleanup Job stats", extra=stats.to_dict())
    except Exception as exc:
        logger.error(
            "Credential Cleanup Job failed",
            extra={"error": str(exc)},
            exc_info=True,
        )
        sys.exit(1)
    finally:
        session.close()

    logger.info("Credential Cleanup Job finished")


if __name__ == "__main__":
    main()
