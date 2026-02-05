"""
Sync retry manager for ingestion job failure handling.

Orchestrates the retry lifecycle for failed ingestion syncs:
- Evaluates failures using error-aware retry policy
- Applies exponential backoff with jitter (up to 5 retries)
- Marks syncs as permanently failed after retry exhaustion
- Notifies Merchant Admin + Agency Admin on terminal failures
- Emits immutable audit events for every state transition

Integrates with existing infrastructure:
- ingestion/jobs/retry.py for retry decisions and backoff calculation
- ingestion/jobs/models.py for IngestionJob state transitions
- services/notification_service.py for admin notifications
- platform/audit.py for immutable audit trail

SECURITY:
- tenant_id from JWT only, never from client input
- Error messages are truncated to prevent log injection
- No PII in audit metadata

Usage:
    manager = SyncRetryManager(db_session=db, tenant_id=tenant_id)

    # Handle a job failure (called by sync executor)
    result = manager.handle_failure(job, error_category, error_message)

    # Get failure summary for UI display
    summary = manager.get_failure_summary(connector_id)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy.orm import Session

from src.ingestion.jobs.models import IngestionJob, JobStatus
from src.ingestion.jobs.retry import (
    ErrorCategory,
    RetryDecision,
    RetryPolicy,
    calculate_backoff,
    categorize_error,
    log_retry_decision,
    should_retry,
)

logger = logging.getLogger(__name__)

MAX_ERROR_MESSAGE_LENGTH = 500


class FailureAction(str, Enum):
    """Action taken after a failure evaluation."""
    RETRY_SCHEDULED = "retry_scheduled"
    MOVED_TO_DLQ = "moved_to_dlq"
    MARKED_FAILED_TERMINAL = "marked_failed_terminal"


@dataclass
class FailureResult:
    """Outcome of handling a job failure."""
    job_id: str
    action: FailureAction
    retry_count: int
    error_category: str
    error_message: str
    next_retry_at: Optional[datetime] = None
    delay_seconds: float = 0
    notified_admins: bool = False

    def to_dict(self) -> dict:
        result = {
            "job_id": self.job_id,
            "action": self.action.value,
            "retry_count": self.retry_count,
            "error_category": self.error_category,
            "error_message": self.error_message[:200],
            "delay_seconds": self.delay_seconds,
            "notified_admins": self.notified_admins,
        }
        if self.next_retry_at:
            result["next_retry_at"] = self.next_retry_at.isoformat()
        return result


@dataclass
class FailureSummary:
    """Failure summary for UI display."""
    connector_id: str
    total_failures: int
    active_retries: int
    dead_letter_count: int
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    last_error_category: Optional[str] = None
    next_retry_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "connector_id": self.connector_id,
            "total_failures": self.total_failures,
            "active_retries": self.active_retries,
            "dead_letter_count": self.dead_letter_count,
            "last_error": self.last_error,
            "last_error_at": (
                self.last_error_at.isoformat() if self.last_error_at else None
            ),
            "last_error_category": self.last_error_category,
            "next_retry_at": (
                self.next_retry_at.isoformat() if self.next_retry_at else None
            ),
        }


class SyncRetryManager:
    """
    Manages retry lifecycle and failure handling for ingestion syncs.

    Coordinates between the retry policy engine, notification service,
    and audit system to provide a complete failure handling pipeline.
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.db = db_session
        self.tenant_id = tenant_id
        self.retry_policy = retry_policy or RetryPolicy()

    # =========================================================================
    # Core Failure Handling
    # =========================================================================

    def handle_failure(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        error_message: str,
        status_code: Optional[int] = None,
        retry_after: Optional[int] = None,
    ) -> FailureResult:
        """
        Handle an ingestion job failure with retry evaluation.

        This is the main entry point called by the sync executor when a
        job fails. It evaluates the error, decides whether to retry or
        give up, updates the job state, and triggers notifications and
        audit events as needed.

        Args:
            job: The failed IngestionJob
            error_category: Classified error type
            error_message: Human-readable error description
            status_code: HTTP status code if applicable
            retry_after: Server-specified retry delay in seconds

        Returns:
            FailureResult describing what action was taken
        """
        error_message = error_message[:MAX_ERROR_MESSAGE_LENGTH]

        decision = should_retry(
            error_category=error_category,
            retry_count=job.retry_count,
            policy=self.retry_policy,
            retry_after=retry_after,
        )

        log_retry_decision(
            job_id=job.job_id,
            tenant_id=self.tenant_id,
            error_category=error_category,
            decision=decision,
        )

        if decision.move_to_dlq:
            return self._move_to_dlq(job, error_category, error_message, decision)
        elif decision.should_retry:
            return self._schedule_retry(job, error_category, error_message, decision)
        else:
            return self._mark_terminal_failure(
                job, error_category, error_message, decision
            )

    def handle_failure_from_status_code(
        self,
        job: IngestionJob,
        status_code: int,
        error_message: str,
        retry_after: Optional[int] = None,
    ) -> FailureResult:
        """
        Handle a failure using an HTTP status code for error classification.

        Convenience method that auto-categorizes the error from the
        status code before delegating to handle_failure().

        Args:
            job: The failed IngestionJob
            status_code: HTTP status code
            error_message: Human-readable error description
            retry_after: Server-specified retry delay in seconds

        Returns:
            FailureResult describing what action was taken
        """
        error_category = categorize_error(status_code=status_code)
        return self.handle_failure(
            job=job,
            error_category=error_category,
            error_message=error_message,
            status_code=status_code,
            retry_after=retry_after,
        )

    # =========================================================================
    # UI Surface: Failure Summaries
    # =========================================================================

    def get_failure_summary(self, connector_id: str) -> FailureSummary:
        """
        Get failure summary for a connector, suitable for UI display.

        Aggregates failure state across all jobs for the connector
        within the current tenant.

        Args:
            connector_id: Internal connector ID

        Returns:
            FailureSummary with counts and latest error info
        """
        failed_jobs = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.tenant_id == self.tenant_id,
                IngestionJob.connector_id == connector_id,
                IngestionJob.status.in_([JobStatus.FAILED, JobStatus.DEAD_LETTER]),
            )
            .order_by(IngestionJob.created_at.desc())
            .limit(100)
            .all()
        )

        active_retries = sum(
            1 for j in failed_jobs
            if j.status == JobStatus.FAILED and j.can_retry
        )
        dead_letter_count = sum(
            1 for j in failed_jobs if j.status == JobStatus.DEAD_LETTER
        )

        last_error = None
        last_error_at = None
        last_error_category = None
        next_retry_at = None

        if failed_jobs:
            latest = failed_jobs[0]
            last_error = latest.error_message
            last_error_at = latest.completed_at or latest.created_at
            last_error_category = latest.error_code

            # Find the earliest pending retry
            for j in failed_jobs:
                if j.status == JobStatus.FAILED and j.next_retry_at:
                    if next_retry_at is None or j.next_retry_at < next_retry_at:
                        next_retry_at = j.next_retry_at

        return FailureSummary(
            connector_id=connector_id,
            total_failures=len(failed_jobs),
            active_retries=active_retries,
            dead_letter_count=dead_letter_count,
            last_error=last_error,
            last_error_at=last_error_at,
            last_error_category=last_error_category,
            next_retry_at=next_retry_at,
        )

    def get_all_failure_summaries(self) -> List[FailureSummary]:
        """
        Get failure summaries for all connectors with failures.

        Returns:
            List of FailureSummary for connectors with failed/DLQ jobs
        """
        connector_ids = (
            self.db.query(IngestionJob.connector_id)
            .filter(
                IngestionJob.tenant_id == self.tenant_id,
                IngestionJob.status.in_([JobStatus.FAILED, JobStatus.DEAD_LETTER]),
            )
            .distinct()
            .all()
        )

        return [
            self.get_failure_summary(row[0])
            for row in connector_ids
        ]

    # =========================================================================
    # Internal: State Transitions
    # =========================================================================

    def _schedule_retry(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        error_message: str,
        decision: RetryDecision,
    ) -> FailureResult:
        """Schedule a job for retry with backoff."""
        job.mark_failed(
            error_message=error_message,
            error_code=error_category.value,
            next_retry_at=decision.next_retry_at,
        )
        self.db.flush()

        self._log_audit_retry(job, error_category, decision)

        logger.info(
            "Sync retry scheduled",
            extra={
                "tenant_id": self.tenant_id,
                "job_id": job.job_id,
                "connector_id": job.connector_id,
                "retry_count": job.retry_count,
                "error_category": error_category.value,
                "delay_seconds": decision.delay_seconds,
                "next_retry_at": (
                    decision.next_retry_at.isoformat()
                    if decision.next_retry_at
                    else None
                ),
            },
        )

        return FailureResult(
            job_id=job.job_id,
            action=FailureAction.RETRY_SCHEDULED,
            retry_count=job.retry_count,
            error_category=error_category.value,
            error_message=error_message,
            next_retry_at=decision.next_retry_at,
            delay_seconds=decision.delay_seconds,
        )

    def _move_to_dlq(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        error_message: str,
        decision: RetryDecision,
    ) -> FailureResult:
        """Move a job to the dead letter queue and notify admins."""
        job.mark_dead_letter(error_message)
        self.db.flush()

        self._log_audit_dlq(job, error_category, decision)

        notified = self._notify_admins_of_failure(job, error_category, error_message)

        logger.error(
            "Sync moved to dead letter queue",
            extra={
                "tenant_id": self.tenant_id,
                "job_id": job.job_id,
                "connector_id": job.connector_id,
                "retry_count": job.retry_count,
                "error_category": error_category.value,
                "reason": decision.reason,
                "notified_admins": notified,
            },
        )

        return FailureResult(
            job_id=job.job_id,
            action=FailureAction.MOVED_TO_DLQ,
            retry_count=job.retry_count,
            error_category=error_category.value,
            error_message=error_message,
            notified_admins=notified,
        )

    def _mark_terminal_failure(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        error_message: str,
        decision: RetryDecision,
    ) -> FailureResult:
        """Mark a job as terminally failed (no retry, no DLQ)."""
        job.mark_failed(
            error_message=error_message,
            error_code=error_category.value,
        )
        job.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        self._log_audit_terminal_failure(job, error_category)

        notified = self._notify_admins_of_failure(job, error_category, error_message)

        logger.error(
            "Sync marked as terminal failure",
            extra={
                "tenant_id": self.tenant_id,
                "job_id": job.job_id,
                "connector_id": job.connector_id,
                "error_category": error_category.value,
                "reason": decision.reason,
                "notified_admins": notified,
            },
        )

        return FailureResult(
            job_id=job.job_id,
            action=FailureAction.MARKED_FAILED_TERMINAL,
            retry_count=job.retry_count,
            error_category=error_category.value,
            error_message=error_message,
            notified_admins=notified,
        )

    # =========================================================================
    # Internal: Admin Notifications
    # =========================================================================

    def _notify_admins_of_failure(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        error_message: str,
    ) -> bool:
        """
        Notify Merchant Admin and Agency Admin of a terminal sync failure.

        Uses the existing NotificationService and TenantMembersService
        to find admin users and send notifications.

        Returns:
            True if notifications were sent, False on error
        """
        try:
            admin_user_ids = self._get_admin_user_ids()

            if not admin_user_ids:
                logger.warning(
                    "No admin users found for failure notification",
                    extra={
                        "tenant_id": self.tenant_id,
                        "job_id": job.job_id,
                    },
                )
                return False

            from src.services.notification_service import NotificationService

            notification_service = NotificationService(
                db_session=self.db, tenant_id=self.tenant_id
            )
            connector_name = (job.job_metadata or {}).get(
                "connector_name", job.connector_id
            )

            notifications = notification_service.notify_connector_failed(
                connector_id=job.connector_id,
                connector_name=connector_name,
                error_message=error_message[:200],
                user_ids=admin_user_ids,
            )

            logger.info(
                "Admin failure notifications sent",
                extra={
                    "tenant_id": self.tenant_id,
                    "job_id": job.job_id,
                    "notification_count": len(notifications),
                    "admin_count": len(admin_user_ids),
                },
            )

            return len(notifications) > 0

        except Exception:
            logger.warning(
                "Failed to send admin failure notifications",
                extra={
                    "tenant_id": self.tenant_id,
                    "job_id": job.job_id,
                },
                exc_info=True,
            )
            return False

    def _get_admin_user_ids(self) -> List[str]:
        """
        Get clerk_user_ids for Merchant Admin and Agency Admin roles.

        Uses TenantMembersService to look up admin users.
        Returns clerk_user_id values for notification targeting.
        """
        try:
            from src.services.tenant_members_service import TenantMembersService

            members_service = TenantMembersService(self.db)
            members = members_service.list_members(self.tenant_id)

            admin_roles = {"MERCHANT_ADMIN", "AGENCY_ADMIN", "ADMIN", "OWNER"}
            return [
                m["clerk_user_id"]
                for m in members
                if m.get("role") in admin_roles and m.get("is_active", True)
            ]
        except Exception:
            logger.warning(
                "Failed to look up admin users",
                extra={"tenant_id": self.tenant_id},
                exc_info=True,
            )
            return []

    # =========================================================================
    # Internal: Audit Logging
    # =========================================================================

    def _log_audit_retry(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        decision: RetryDecision,
    ) -> None:
        """Log a sync retry event to the immutable audit trail."""
        try:
            from src.platform.audit import (
                AuditAction,
                AuditOutcome,
                log_system_audit_event_sync,
            )

            log_system_audit_event_sync(
                db=self.db,
                tenant_id=self.tenant_id,
                action=AuditAction.STORE_SYNC_FAILED,
                resource_type="ingestion_job",
                resource_id=job.job_id,
                metadata={
                    "connector_id": job.connector_id,
                    "error_category": error_category.value,
                    "retry_count": job.retry_count,
                    "delay_seconds": decision.delay_seconds,
                    "next_retry_at": (
                        decision.next_retry_at.isoformat()
                        if decision.next_retry_at
                        else None
                    ),
                    "decision": "retry",
                },
                source="worker",
                outcome=AuditOutcome.FAILURE,
            )
        except Exception:
            logger.warning(
                "Failed to write retry audit event",
                extra={"tenant_id": self.tenant_id, "job_id": job.job_id},
                exc_info=True,
            )

    def _log_audit_dlq(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
        decision: RetryDecision,
    ) -> None:
        """Log a dead-letter-queue event to the immutable audit trail."""
        try:
            from src.platform.audit import (
                AuditAction,
                AuditOutcome,
                log_system_audit_event_sync,
            )

            log_system_audit_event_sync(
                db=self.db,
                tenant_id=self.tenant_id,
                action=AuditAction.STORE_SYNC_FAILED,
                resource_type="ingestion_job",
                resource_id=job.job_id,
                metadata={
                    "connector_id": job.connector_id,
                    "error_category": error_category.value,
                    "retry_count": job.retry_count,
                    "reason": decision.reason,
                    "decision": "dead_letter",
                },
                source="worker",
                outcome=AuditOutcome.FAILURE,
            )
        except Exception:
            logger.warning(
                "Failed to write DLQ audit event",
                extra={"tenant_id": self.tenant_id, "job_id": job.job_id},
                exc_info=True,
            )

    def _log_audit_terminal_failure(
        self,
        job: IngestionJob,
        error_category: ErrorCategory,
    ) -> None:
        """Log a terminal failure event to the immutable audit trail."""
        try:
            from src.platform.audit import (
                AuditAction,
                AuditOutcome,
                log_system_audit_event_sync,
            )

            log_system_audit_event_sync(
                db=self.db,
                tenant_id=self.tenant_id,
                action=AuditAction.STORE_SYNC_FAILED,
                resource_type="ingestion_job",
                resource_id=job.job_id,
                metadata={
                    "connector_id": job.connector_id,
                    "error_category": error_category.value,
                    "retry_count": job.retry_count,
                    "decision": "terminal_failure",
                },
                source="worker",
                outcome=AuditOutcome.FAILURE,
            )
        except Exception:
            logger.warning(
                "Failed to write terminal failure audit event",
                extra={"tenant_id": self.tenant_id, "job_id": job.job_id},
                exc_info=True,
            )
