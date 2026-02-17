"""
Action Execution Log model for detailed audit trail.

Stores a complete audit trail of all events during action execution,
including API requests/responses, state snapshots, and errors.

SECURITY:
- Tenant isolation via TenantScopedMixin (tenant_id from JWT only)
- Full request/response logging for audit compliance
- No modification after creation (append-only log)

AUDIT REQUIREMENTS:
- Log every API request sent to external platforms
- Log every API response received
- Capture state snapshots at key points
- Track who/what triggered each event

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import (
    Column,
    String,
    Integer,
    Enum,
    DateTime,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from src.db_base import Base
from src.models.base import TenantScopedMixin


# Use JSONB for PostgreSQL, JSON for other databases (testing)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ActionLogEventType(str, enum.Enum):
    """
    Types of events that can be logged during action execution.

    Events are logged in chronological order to provide a complete
    audit trail of the execution process.
    """
    # Lifecycle events
    CREATED = "created"
    APPROVED = "approved"
    QUEUED = "queued"
    CANCELLED = "cancelled"

    # Execution events
    EXECUTION_STARTED = "execution_started"
    BEFORE_STATE_CAPTURED = "before_state_captured"
    API_REQUEST_SENT = "api_request_sent"
    API_RESPONSE_RECEIVED = "api_response_received"
    AFTER_STATE_CAPTURED = "after_state_captured"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"

    # Rollback events
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_SUCCEEDED = "rollback_succeeded"
    ROLLBACK_FAILED = "rollback_failed"


class ActionExecutionLog(Base, TenantScopedMixin):
    """
    Detailed audit trail of action execution events.

    Each log entry represents a single event in the action execution
    lifecycle. Logs are append-only and should never be modified
    after creation.

    SECURITY: tenant_id from TenantScopedMixin ensures isolation.
    tenant_id is ONLY extracted from JWT, never from client input.

    IMMUTABILITY: Logs should never be updated or deleted (except
    for data retention policies). This ensures audit integrity.
    """

    __tablename__ = "action_execution_logs"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Unique log entry identifier (UUID)"
    )

    # Link to parent action
    action_id = Column(
        String(255),
        ForeignKey("ai_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the action this log entry belongs to"
    )

    # Event details
    event_type = Column(
        Enum(ActionLogEventType, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        index=True,
        comment="Type of event being logged"
    )

    event_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="When this event occurred"
    )

    # Full audit data - API interactions
    request_payload = Column(
        JSONType,
        nullable=True,
        comment="Full API request sent to external platform"
    )

    response_payload = Column(
        JSONType,
        nullable=True,
        comment="Full API response from external platform"
    )

    http_status_code = Column(
        Integer,
        nullable=True,
        comment="HTTP status code from API response"
    )

    # State snapshots
    state_snapshot = Column(
        JSONType,
        nullable=True,
        comment="Platform state at the time of this event"
    )

    # Error details if applicable
    error_details = Column(
        JSONType,
        nullable=True,
        comment="Error information if event represents a failure"
    )

    # Actor tracking - who/what triggered this event
    triggered_by = Column(
        String(255),
        nullable=True,
        comment="Actor: 'system', 'user:<id>', 'worker:<job_id>'"
    )

    # Timestamps (only created_at, no updated_at for append-only log)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this log entry was created"
    )

    # Relationship to action
    action = relationship(
        "AIAction",
        back_populates="execution_logs"
    )

    # Indexes for efficient querying
    __table_args__ = (
        # Tenant + timestamp for listing recent logs
        Index(
            "ix_action_logs_tenant_timestamp",
            "tenant_id",
            "event_timestamp",
            postgresql_ops={"event_timestamp": "DESC"}
        ),
        # Action + timestamp for getting logs for specific action in order
        Index(
            "ix_action_logs_action_timestamp",
            "action_id",
            "event_timestamp"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ActionExecutionLog("
            f"id={self.id}, "
            f"action_id={self.action_id}, "
            f"event_type={self.event_type.value if self.event_type else None}, "
            f"timestamp={self.event_timestamp}"
            f")>"
        )

    # ==========================================================================
    # Factory methods for creating specific log types
    # ==========================================================================

    @classmethod
    def log_created(
        cls,
        tenant_id: str,
        action_id: str,
        triggered_by: str = "system",
    ) -> "ActionExecutionLog":
        """Create a log entry for action creation."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.CREATED,
            triggered_by=triggered_by,
        )

    @classmethod
    def log_approved(
        cls,
        tenant_id: str,
        action_id: str,
        user_id: str,
    ) -> "ActionExecutionLog":
        """Create a log entry for action approval."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.APPROVED,
            triggered_by=f"user:{user_id}",
        )

    @classmethod
    def log_execution_started(
        cls,
        tenant_id: str,
        action_id: str,
        job_id: Optional[str] = None,
    ) -> "ActionExecutionLog":
        """Create a log entry for execution start."""
        triggered_by = f"worker:{job_id}" if job_id else "system"
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.EXECUTION_STARTED,
            triggered_by=triggered_by,
        )

    @classmethod
    def log_state_captured(
        cls,
        tenant_id: str,
        action_id: str,
        state_snapshot: dict,
        is_before: bool = True,
    ) -> "ActionExecutionLog":
        """Create a log entry for state capture."""
        event_type = (
            ActionLogEventType.BEFORE_STATE_CAPTURED
            if is_before
            else ActionLogEventType.AFTER_STATE_CAPTURED
        )
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=event_type,
            state_snapshot=state_snapshot,
            triggered_by="system",
        )

    @classmethod
    def log_api_request(
        cls,
        tenant_id: str,
        action_id: str,
        request_payload: dict,
    ) -> "ActionExecutionLog":
        """Create a log entry for API request sent."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.API_REQUEST_SENT,
            request_payload=request_payload,
            triggered_by="system",
        )

    @classmethod
    def log_api_response(
        cls,
        tenant_id: str,
        action_id: str,
        response_payload: dict,
        http_status_code: int,
    ) -> "ActionExecutionLog":
        """Create a log entry for API response received."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.API_RESPONSE_RECEIVED,
            response_payload=response_payload,
            http_status_code=http_status_code,
            triggered_by="system",
        )

    @classmethod
    def log_execution_succeeded(
        cls,
        tenant_id: str,
        action_id: str,
        state_snapshot: Optional[dict] = None,
    ) -> "ActionExecutionLog":
        """Create a log entry for successful execution."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.EXECUTION_SUCCEEDED,
            state_snapshot=state_snapshot,
            triggered_by="system",
        )

    @classmethod
    def log_execution_failed(
        cls,
        tenant_id: str,
        action_id: str,
        error_details: dict,
        http_status_code: Optional[int] = None,
    ) -> "ActionExecutionLog":
        """Create a log entry for failed execution."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.EXECUTION_FAILED,
            error_details=error_details,
            http_status_code=http_status_code,
            triggered_by="system",
        )

    @classmethod
    def log_rollback_started(
        cls,
        tenant_id: str,
        action_id: str,
        triggered_by: str = "system",
    ) -> "ActionExecutionLog":
        """Create a log entry for rollback start."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.ROLLBACK_STARTED,
            triggered_by=triggered_by,
        )

    @classmethod
    def log_rollback_succeeded(
        cls,
        tenant_id: str,
        action_id: str,
        state_snapshot: Optional[dict] = None,
    ) -> "ActionExecutionLog":
        """Create a log entry for successful rollback."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.ROLLBACK_SUCCEEDED,
            state_snapshot=state_snapshot,
            triggered_by="system",
        )

    @classmethod
    def log_rollback_failed(
        cls,
        tenant_id: str,
        action_id: str,
        error_details: dict,
    ) -> "ActionExecutionLog":
        """Create a log entry for failed rollback."""
        return cls(
            tenant_id=tenant_id,
            action_id=action_id,
            event_type=ActionLogEventType.ROLLBACK_FAILED,
            error_details=error_details,
            triggered_by="system",
        )
