"""
GA Audit Log Retention Job.

Enforces 90-day hard-delete retention for ga_audit_logs.

REQUIREMENTS:
- Hard-delete logs older than 90 days
- Daily scheduled job
- No legal hold support (GA scope)
- Batch deletion to avoid long transactions
- Temporarily disables immutability trigger during deletion

SAFETY:
- Dry-run mode is ON by default (set AUDIT_RETENTION_DRY_RUN=false to enable)
- Batch size is configurable (default 1000)
- Transaction per batch to avoid holding locks
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.audit_log import GAAuditLog

logger = logging.getLogger(__name__)

# Configuration
RETENTION_DAYS = 90
BATCH_SIZE = int(os.getenv("GA_AUDIT_RETENTION_BATCH_SIZE", "1000"))
DRY_RUN = os.getenv("GA_AUDIT_RETENTION_DRY_RUN", "true").lower() == "true"


class GAAuditRetentionJob:
    """
    Deletes GA audit log records older than 90 days.

    Runs as a daily scheduled job. Deletes in batches to avoid long
    transactions and lock contention.

    The immutability trigger on ga_audit_logs prevents DELETE operations.
    This job temporarily disables the trigger, performs the batch delete,
    then re-enables it.
    """

    def __init__(self, db: Session):
        self.db = db
        self.retention_days = RETENTION_DAYS
        self.batch_size = BATCH_SIZE
        self.dry_run = DRY_RUN

    def execute(self) -> dict:
        """
        Run the retention job.

        Returns:
            Dict with execution summary including total_deleted, batches, duration.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        start_time = time.monotonic()
        total_deleted = 0
        batch_count = 0

        logger.info(
            "ga_audit_retention_started",
            extra={
                "cutoff": cutoff.isoformat(),
                "retention_days": self.retention_days,
                "batch_size": self.batch_size,
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            # Count what would be deleted
            count = (
                self.db.query(GAAuditLog)
                .filter(GAAuditLog.created_at < cutoff)
                .count()
            )
            elapsed = time.monotonic() - start_time
            logger.info(
                "ga_audit_retention_dry_run",
                extra={
                    "would_delete": count,
                    "cutoff": cutoff.isoformat(),
                    "elapsed_seconds": round(elapsed, 2),
                },
            )
            return {
                "dry_run": True,
                "would_delete": count,
                "cutoff": cutoff.isoformat(),
                "elapsed_seconds": round(elapsed, 2),
            }

        try:
            # Disable immutability trigger for deletion
            self._disable_immutability_trigger()

            while True:
                deleted = self._delete_batch(cutoff)
                if deleted == 0:
                    break
                total_deleted += deleted
                batch_count += 1

                logger.info(
                    "ga_audit_retention_batch",
                    extra={
                        "batch": batch_count,
                        "deleted": deleted,
                        "total_deleted": total_deleted,
                    },
                )

        finally:
            # Always re-enable the trigger
            self._enable_immutability_trigger()

        elapsed = time.monotonic() - start_time

        logger.info(
            "ga_audit_retention_completed",
            extra={
                "total_deleted": total_deleted,
                "batches": batch_count,
                "cutoff": cutoff.isoformat(),
                "elapsed_seconds": round(elapsed, 2),
            },
        )

        return {
            "dry_run": False,
            "total_deleted": total_deleted,
            "batches": batch_count,
            "cutoff": cutoff.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
        }

    def _delete_batch(self, cutoff: datetime) -> int:
        """
        Delete a single batch of expired records.

        Uses a subquery to identify IDs first (avoids locking entire table),
        then deletes by ID.
        """
        # Find IDs to delete
        ids_to_delete = (
            self.db.query(GAAuditLog.id)
            .filter(GAAuditLog.created_at < cutoff)
            .limit(self.batch_size)
            .all()
        )

        if not ids_to_delete:
            return 0

        id_list = [row[0] for row in ids_to_delete]

        deleted = (
            self.db.query(GAAuditLog)
            .filter(GAAuditLog.id.in_(id_list))
            .delete(synchronize_session=False)
        )

        self.db.commit()
        return deleted

    def _disable_immutability_trigger(self) -> None:
        """Temporarily disable the immutability trigger on ga_audit_logs."""
        try:
            self.db.execute(
                text(
                    "ALTER TABLE ga_audit_logs "
                    "DISABLE TRIGGER ga_audit_log_immutable"
                )
            )
            self.db.commit()
            logger.info("ga_audit_retention_trigger_disabled")
        except Exception:
            # SQLite (test) doesn't support triggers
            logger.debug(
                "ga_audit_retention_trigger_disable_skipped",
                exc_info=True,
            )

    def _enable_immutability_trigger(self) -> None:
        """Re-enable the immutability trigger on ga_audit_logs."""
        try:
            self.db.execute(
                text(
                    "ALTER TABLE ga_audit_logs "
                    "ENABLE TRIGGER ga_audit_log_immutable"
                )
            )
            self.db.commit()
            logger.info("ga_audit_retention_trigger_enabled")
        except Exception:
            logger.debug(
                "ga_audit_retention_trigger_enable_skipped",
                exc_info=True,
            )
