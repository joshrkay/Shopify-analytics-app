"""
BackfillExecution model for auditing dbt backfill runs.

Tracks execution metadata, status, and results for tenant-scoped and global backfills.
"""

import uuid
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, DateTime, Enum, Text, Integer, Float, JSON, Index
)

from src.db_base import Base
from src.models.base import TimestampMixin


class BackfillStatus(str, PyEnum):
    """Backfill execution status values."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackfillExecution(Base, TimestampMixin):
    """
    Audit log for dbt backfill executions.
    
    Tracks date ranges, tenant scope, models executed, and results.
    Supports both tenant-scoped and global backfills (tenant_id nullable for global).
    """
    
    __tablename__ = "backfill_executions"
    
    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )
    
    tenant_id = Column(
        String(255),
        nullable=True,  # Nullable for global backfills
        index=True,
        comment="Tenant identifier (nullable for global backfills)"
    )
    
    start_date = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start date for backfill date range"
    )
    
    end_date = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="End date for backfill date range"
    )
    
    models_run = Column(
        JSON,
        nullable=True,
        comment="Array of model names that were executed in this backfill"
    )
    
    status = Column(
        Enum(BackfillStatus),
        nullable=False,
        default=BackfillStatus.RUNNING,
        index=True,
        comment="Execution status: running, completed, failed"
    )
    
    records_processed = Column(
        Integer,
        nullable=True,
        comment="Total number of records processed (if available)"
    )
    
    duration_seconds = Column(
        Float,
        nullable=True,
        comment="Total execution duration in seconds"
    )
    
    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if status is failed"
    )
    
    # Indexes
    __table_args__ = (
        Index(
            "idx_backfill_executions_tenant_status",
            "tenant_id",
            "status"
        ),
        Index(
            "idx_backfill_executions_created_at",
            "created_at"
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<BackfillExecution(id={self.id}, tenant_id={self.tenant_id}, "
            f"status={self.status.value}, start_date={self.start_date}, end_date={self.end_date})>"
        )
