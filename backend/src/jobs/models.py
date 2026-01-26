"""
Job status models for background job tracking.

Tracks job status including blocked_due_to_billing for auto-retry on recovery.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Integer, DateTime, Enum, Text, JSON,
    ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy.orm import relationship

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class JobStatus(str, PyEnum):
    """Job status values for background jobs."""
    PENDING = "pending"  # Job queued, not yet started
    RUNNING = "running"  # Job currently executing
    COMPLETED = "completed"  # Job completed successfully
    FAILED = "failed"  # Job failed with error
    BLOCKED_DUE_TO_BILLING = "blocked_due_to_billing"  # Blocked due to billing state
    RETRYING = "retrying"  # Job is being retried after recovery
    CANCELLED = "cancelled"  # Job was cancelled


class JobCategory(str, PyEnum):
    """Job category for premium gating."""
    EXPORTS = "exports"
    AI = "ai"
    HEAVY_RECOMPUTE = "heavy_recompute"
    OTHER = "other"  # Non-premium jobs


# PostgreSQL enum type names - distinct from ingestion.jobs.models to avoid conflicts
# Use values_callable to store lowercase string values (e.g., 'blocked_due_to_billing')
# instead of member names (e.g., 'BLOCKED_DUE_TO_BILLING')
BACKGROUND_JOB_STATUS_ENUM = Enum(
    JobStatus,
    name="background_job_status",  # Unique name to avoid conflict with ingestion JobStatus
    create_constraint=True,
    metadata=Base.metadata,
    validate_strings=True,
    values_callable=lambda enum: [e.value for e in enum],
)

BACKGROUND_JOB_CATEGORY_ENUM = Enum(
    JobCategory,
    name="background_job_category",
    create_constraint=True,
    metadata=Base.metadata,
    validate_strings=True,
    values_callable=lambda enum: [e.value for e in enum],
)


class BackgroundJob(Base, TimestampMixin, TenantScopedMixin):
    """
    Background job tracking model.
    
    Tracks job execution status, retry counts, and billing-related blocks.
    Used for auto-retry when billing state recovers.
    """
    
    __tablename__ = "background_jobs"
    
    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )
    
    job_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Type of job (sync, export, ai_action, backfill, etc.)"
    )
    
    category = Column(
        BACKGROUND_JOB_CATEGORY_ENUM,
        nullable=False,
        default=JobCategory.OTHER,
        index=True,
        comment="Premium category for gating (exports, ai, heavy_recompute, other)"
    )
    
    status = Column(
        BACKGROUND_JOB_STATUS_ENUM,
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
        comment="Current job status"
    )
    
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts"
    )
    
    max_retries = Column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum retry attempts allowed"
    )
    
    blocked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When job was blocked due to billing"
    )
    
    blocked_billing_state = Column(
        String(50),
        nullable=True,
        comment="Billing state that caused the block"
    )
    
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When job execution started"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When job execution completed"
    )
    
    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if job failed"
    )
    
    job_metadata = Column(
        JSON,
        nullable=True,
        comment="Additional job metadata (parameters, context, etc.)"
    )
    
    # Table constraints and indexes
    __table_args__ = (
        Index("ix_background_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_background_jobs_tenant_category", "tenant_id", "category"),
        Index("ix_background_jobs_blocked_billing", "status", "blocked_billing_state"),
        Index(
            "ix_background_jobs_blocked_retry",
            "status",
            "blocked_billing_state",
            postgresql_where=text("status = 'blocked_due_to_billing'::background_job_status")
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<BackgroundJob(id={self.id}, tenant_id={self.tenant_id}, "
            f"job_type={self.job_type}, status={self.status}, retry_count={self.retry_count})>"
        )
    
    def mark_blocked(self, billing_state: str) -> None:
        """Mark job as blocked due to billing state."""
        self.status = JobStatus.BLOCKED_DUE_TO_BILLING
        self.blocked_at = datetime.now(timezone.utc)
        self.blocked_billing_state = billing_state
    
    def mark_retrying(self) -> None:
        """Mark job as retrying after recovery."""
        self.status = JobStatus.RETRYING
        self.retry_count += 1
        self.blocked_at = None
        self.blocked_billing_state = None
        self.started_at = datetime.now(timezone.utc)
    
    def mark_completed(self) -> None:
        """Mark job as completed successfully."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error_message: str) -> None:
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now(timezone.utc)
    
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.retry_count < self.max_retries
