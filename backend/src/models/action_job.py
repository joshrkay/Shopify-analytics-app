"""
Action execution job model for scheduling.

Tracks AI action execution job processing with:
- Tenant isolation via TenantScopedMixin
- Status tracking (queued|running|succeeded|failed|partially_succeeded)
- Results tracking (attempted, succeeded, failed counts)
- Error summary for batch failures

Follows the same pattern as InsightJob but for action execution.

SECURITY: tenant_id is ONLY extracted from JWT, never from client input.

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Enum,
    DateTime,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


# Use JSONB for PostgreSQL, JSON for other databases (testing)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ActionJobStatus(str, enum.Enum):
    """
    Action job status enumeration.

    Unlike insight jobs, action jobs can partially succeed when
    processing multiple actions in a batch.
    """
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIALLY_SUCCEEDED = "partially_succeeded"  # Some actions succeeded, some failed


class ActionJob(Base, TimestampMixin, TenantScopedMixin):
    """
    Tracks action execution job processing.

    Jobs process batches of approved actions. A job can process
    multiple actions and tracks success/failure counts for each.

    SECURITY: tenant_id from TenantScopedMixin ensures isolation.
    tenant_id is ONLY extracted from JWT, never from client input.

    PARTIAL SUCCESS: Unlike insight jobs, action jobs can have
    partial success when processing multiple actions. The
    partially_succeeded status indicates some actions completed
    while others failed.
    """

    __tablename__ = "action_jobs"

    job_id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )

    # Status tracking
    status = Column(
        Enum(ActionJobStatus),
        default=ActionJobStatus.QUEUED,
        nullable=False,
        index=True,
        comment="Job status: queued, running, succeeded, failed, partially_succeeded"
    )

    # What actions are being processed (array of action IDs)
    action_ids = Column(
        JSONType,
        nullable=False,
        default=list,
        comment="Array of action IDs being processed in this job"
    )

    # Results tracking
    actions_attempted = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Total number of actions attempted"
    )

    actions_succeeded = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of actions that succeeded"
    )

    actions_failed = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of actions that failed"
    )

    # Timing
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When job started running"
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When job completed"
    )

    # Error summary for batch failures
    error_summary = Column(
        JSONType,
        nullable=True,
        comment="Summary of errors: {action_id: error_message, ...}"
    )

    # Job metadata
    job_metadata = Column(
        JSONType,
        nullable=True,
        default=dict,
        comment="Additional metadata (worker info, execution context)"
    )

    # Table constraints and indexes
    __table_args__ = (
        # Composite index for tenant-scoped status queries
        Index("ix_action_jobs_tenant_status", "tenant_id", "status"),
        # Index for finding recent jobs by tenant
        Index(
            "ix_action_jobs_tenant_created",
            "tenant_id",
            "created_at",
            postgresql_ops={"created_at": "DESC"}
        ),
        # Partial unique index: only ONE queued/running job per tenant
        Index(
            "ix_action_jobs_active_unique",
            "tenant_id",
            unique=True,
            postgresql_where=(status.in_([ActionJobStatus.QUEUED, ActionJobStatus.RUNNING]))
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ActionJob("
            f"job_id={self.job_id}, "
            f"tenant_id={self.tenant_id}, "
            f"status={self.status.value if self.status else None}, "
            f"attempted={self.actions_attempted}, "
            f"succeeded={self.actions_succeeded}, "
            f"failed={self.actions_failed}"
            f")>"
        )

    # ==========================================================================
    # Status checks
    # ==========================================================================

    @property
    def is_active(self) -> bool:
        """Check if job is currently active (queued or running)."""
        return self.status in (ActionJobStatus.QUEUED, ActionJobStatus.RUNNING)

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (
            ActionJobStatus.SUCCEEDED,
            ActionJobStatus.FAILED,
            ActionJobStatus.PARTIALLY_SUCCEEDED,
        )

    @property
    def has_failures(self) -> bool:
        """Check if any actions failed."""
        return self.actions_failed > 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.actions_attempted == 0:
            return 0.0
        return (self.actions_succeeded / self.actions_attempted) * 100

    # ==========================================================================
    # Status transitions
    # ==========================================================================

    def mark_running(self) -> None:
        """Mark job as running."""
        self.status = ActionJobStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_succeeded(
        self,
        actions_attempted: int,
        actions_succeeded: int,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Mark job as fully successful.

        Args:
            actions_attempted: Total actions processed
            actions_succeeded: Actions that succeeded (should equal attempted)
            metadata: Optional additional metadata
        """
        self.status = ActionJobStatus.SUCCEEDED
        self.completed_at = datetime.now(timezone.utc)
        self.actions_attempted = actions_attempted
        self.actions_succeeded = actions_succeeded
        self.actions_failed = 0
        if metadata:
            self.job_metadata = {**(self.job_metadata or {}), **metadata}

    def mark_failed(
        self,
        error_summary: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Mark job as completely failed (no actions succeeded).

        Args:
            error_summary: Mapping of action_id to error message
            metadata: Optional additional metadata
        """
        self.status = ActionJobStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        if error_summary:
            self.error_summary = error_summary
            self.actions_failed = len(error_summary)
            self.actions_attempted = len(error_summary)
        if metadata:
            self.job_metadata = {**(self.job_metadata or {}), **metadata}

    def mark_partially_succeeded(
        self,
        actions_attempted: int,
        actions_succeeded: int,
        actions_failed: int,
        error_summary: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Mark job as partially successful.

        Args:
            actions_attempted: Total actions processed
            actions_succeeded: Actions that succeeded
            actions_failed: Actions that failed
            error_summary: Mapping of failed action_id to error message
            metadata: Optional additional metadata
        """
        self.status = ActionJobStatus.PARTIALLY_SUCCEEDED
        self.completed_at = datetime.now(timezone.utc)
        self.actions_attempted = actions_attempted
        self.actions_succeeded = actions_succeeded
        self.actions_failed = actions_failed
        if error_summary:
            self.error_summary = error_summary
        if metadata:
            self.job_metadata = {**(self.job_metadata or {}), **metadata}

    def finalize(
        self,
        actions_succeeded: int,
        actions_failed: int,
        error_summary: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Finalize job with results, automatically determining status.

        Args:
            actions_succeeded: Number of successful actions
            actions_failed: Number of failed actions
            error_summary: Mapping of failed action_id to error message
            metadata: Optional additional metadata
        """
        total = actions_succeeded + actions_failed

        if actions_failed == 0:
            self.mark_succeeded(total, actions_succeeded, metadata)
        elif actions_succeeded == 0:
            self.mark_failed(error_summary, metadata)
        else:
            self.mark_partially_succeeded(
                total,
                actions_succeeded,
                actions_failed,
                error_summary,
                metadata,
            )

    def add_action_id(self, action_id: str) -> None:
        """Add an action ID to the list of actions being processed."""
        if self.action_ids is None:
            self.action_ids = []
        if action_id not in self.action_ids:
            self.action_ids = [*self.action_ids, action_id]

    def set_action_ids(self, action_ids: list[str]) -> None:
        """Set the full list of action IDs to process."""
        self.action_ids = action_ids
