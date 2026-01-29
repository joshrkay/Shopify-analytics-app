"""
Audit Log Retention Enforcement Job.

Runs daily to hard-delete audit logs past their retention window.
Retention periods are configurable per billing plan.

Run as a daily cron job:
    python -m src.jobs.audit_retention_job

Configuration:
- AUDIT_DELETION_BATCH_SIZE: Records to delete per batch (default: 1000)
- AUDIT_RETENTION_DRY_RUN: Set to "false" to enable actual deletion (default: "true")

Story 10.4 - Retention Enforcement
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.session import get_db_session_sync
from src.config.retention import (
    get_retention_days,
    DELETION_BATCH_SIZE,
    RETENTION_DRY_RUN,
    DEFAULT_RETENTION_DAYS,
)
from src.platform.audit import (
    AuditLog,
    AuditAction,
    AuditOutcome,
    log_system_audit_event_sync,
)
from src.monitoring.audit_metrics import get_audit_metrics
from src.monitoring.audit_alerts import get_audit_alert_manager
from src.models.subscription import Subscription, SubscriptionStatus
from src.models.plan import Plan

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AuditRetentionJob:
    """
    Enforces audit log retention policy.

    Process:
    1. Query distinct tenant_ids from audit_logs
    2. For each tenant, get their plan's retention period
    3. Calculate cutoff date (now - retention_days)
    4. Delete logs older than cutoff in batches
    5. Log deletion stats as audit event
    """

    def __init__(self, db_session: Session, dry_run: bool = RETENTION_DRY_RUN):
        """
        Initialize retention job.

        Args:
            db_session: Database session
            dry_run: If True, only count records without deleting
        """
        self.db = db_session
        self.dry_run = dry_run
        self.metrics = get_audit_metrics()
        self.stats: Dict = {
            "tenants_processed": 0,
            "total_deleted": 0,
            "dry_run": dry_run,
            "errors": [],
        }

    def get_distinct_tenants(self) -> list:
        """Get list of distinct tenant IDs from audit logs."""
        result = self.db.execute(
            text("SELECT DISTINCT tenant_id FROM audit_logs WHERE tenant_id != 'system'")
        )
        return [row[0] for row in result]

    def get_tenant_plan(self, tenant_id: str) -> str:
        """
        Get billing plan name for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            Plan name (e.g., 'free', 'professional', 'enterprise')
        """
        subscription = (
            self.db.query(Subscription)
            .filter(
                Subscription.tenant_id == tenant_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .first()
        )

        if not subscription:
            return "professional"  # Default for tenants without subscription

        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if not plan:
            return "professional"

        return plan.name

    def count_expired_logs(self, tenant_id: str, cutoff_date: datetime) -> int:
        """Count logs that would be deleted."""
        result = self.db.execute(
            text("""
                SELECT COUNT(*) FROM audit_logs
                WHERE tenant_id = :tenant_id
                AND timestamp < :cutoff_date
            """),
            {"tenant_id": tenant_id, "cutoff_date": cutoff_date}
        )
        return result.scalar() or 0

    def delete_expired_logs(self, tenant_id: str, cutoff_date: datetime) -> int:
        """
        Delete audit logs older than cutoff_date for tenant.

        Uses batched deletion with trigger disable/enable to bypass
        the immutability trigger for retention purposes.

        Args:
            tenant_id: The tenant to process
            cutoff_date: Delete logs older than this date

        Returns:
            Number of records deleted
        """
        if self.dry_run:
            count = self.count_expired_logs(tenant_id, cutoff_date)
            logger.info(
                f"[DRY RUN] Would delete {count} logs for tenant {tenant_id}"
            )
            return count

        total_deleted = 0

        try:
            # Disable the immutability trigger for this operation
            self.db.execute(
                text("ALTER TABLE audit_logs DISABLE TRIGGER audit_log_immutable")
            )

            # Delete in batches to avoid long-running transactions
            while True:
                result = self.db.execute(
                    text("""
                        DELETE FROM audit_logs
                        WHERE id IN (
                            SELECT id FROM audit_logs
                            WHERE tenant_id = :tenant_id
                            AND timestamp < :cutoff_date
                            LIMIT :batch_size
                        )
                    """),
                    {
                        "tenant_id": tenant_id,
                        "cutoff_date": cutoff_date,
                        "batch_size": DELETION_BATCH_SIZE,
                    }
                )

                batch_deleted = result.rowcount
                self.db.commit()
                total_deleted += batch_deleted

                logger.info(
                    f"Deleted {batch_deleted} audit logs (batch)",
                    extra={
                        "tenant_id": tenant_id,
                        "batch_size": batch_deleted,
                        "total_deleted": total_deleted,
                    },
                )

                if batch_deleted < DELETION_BATCH_SIZE:
                    break

        finally:
            # Always re-enable the trigger
            self.db.execute(
                text("ALTER TABLE audit_logs ENABLE TRIGGER audit_log_immutable")
            )
            self.db.commit()

        # Record metric
        if total_deleted > 0:
            self.metrics.record_retention_deletion(total_deleted, tenant_id)

        return total_deleted

    def process_tenant(self, tenant_id: str) -> int:
        """
        Process retention for a single tenant.

        Args:
            tenant_id: The tenant to process

        Returns:
            Number of records deleted
        """
        try:
            plan = self.get_tenant_plan(tenant_id)
            retention_days = get_retention_days(plan)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            deleted = self.delete_expired_logs(tenant_id, cutoff_date)

            logger.info(
                f"Processed tenant {tenant_id}: plan={plan}, "
                f"retention={retention_days}d, deleted={deleted}"
            )

            return deleted

        except Exception as e:
            error_msg = f"Error processing tenant {tenant_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"].append(error_msg)
            return 0

    def run(self) -> Dict:
        """
        Execute retention enforcement for all tenants.

        Returns:
            Statistics dictionary with processing results
        """
        start_time = datetime.now(timezone.utc)
        logger.info(
            "Starting audit retention job",
            extra={"dry_run": self.dry_run}
        )

        # Log job start
        log_system_audit_event_sync(
            db=self.db,
            tenant_id="system",
            action=AuditAction.AUDIT_RETENTION_STARTED,
            metadata={"dry_run": self.dry_run},
            source="worker",
        )

        try:
            tenants = self.get_distinct_tenants()
            logger.info(f"Found {len(tenants)} tenants to process")

            for tenant_id in tenants:
                deleted = self.process_tenant(tenant_id)
                self.stats["total_deleted"] += deleted
                self.stats["tenants_processed"] += 1

            end_time = datetime.now(timezone.utc)
            self.stats["duration_seconds"] = (end_time - start_time).total_seconds()
            self.stats["completed_at"] = end_time.isoformat()

            # Log job completion
            log_system_audit_event_sync(
                db=self.db,
                tenant_id="system",
                action=AuditAction.AUDIT_RETENTION_COMPLETED,
                metadata=self.stats,
                source="worker",
            )

            logger.info("Audit retention job completed", extra=self.stats)
            return self.stats

        except Exception as e:
            self.stats["error"] = str(e)
            logger.error(
                "Audit retention job failed",
                extra={"error": str(e)},
                exc_info=True
            )

            # Log job failure
            log_system_audit_event_sync(
                db=self.db,
                tenant_id="system",
                action=AuditAction.AUDIT_RETENTION_FAILED,
                metadata=self.stats,
                source="worker",
                outcome=AuditOutcome.FAILURE,
            )

            # Send alert
            get_audit_alert_manager().alert_retention_job_failed(
                error=str(e),
                tenants_processed=self.stats["tenants_processed"],
                total_deleted=self.stats["total_deleted"],
            )

            raise


def main():
    """Main entry point for audit retention job."""
    logger.info("Audit Retention Job starting")

    try:
        for session in get_db_session_sync():
            job = AuditRetentionJob(session)
            stats = job.run()
            logger.info("Audit Retention Job stats", extra=stats)
    except Exception as e:
        logger.error(
            "Audit Retention Job failed",
            extra={"error": str(e)},
            exc_info=True
        )
        sys.exit(1)

    logger.info("Audit Retention Job finished")


if __name__ == "__main__":
    main()
