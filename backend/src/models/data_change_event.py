"""
Data change event model for Story 9.8.

Aggregated data change events for the "What Changed?" debug panel.
Provides merchant-safe summaries of changes that affect metric values.

SECURITY:
- Tenant-scoped via TenantScopedMixin
- Read-only for all users (no mutations via API)
- Never exposes raw logs, credentials, or sensitive implementation details
- All data is aggregated into human-readable summaries
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column, String, Text, DateTime,
    Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin, generate_uuid


class DataChangeEventType(str, Enum):
    """Types of data change events."""
    # Sync events
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"
    BACKFILL_COMPLETED = "backfill_completed"

    # Metric events
    METRIC_VERSION_CHANGED = "metric_version_changed"

    # AI action events
    AI_ACTION_EXECUTED = "ai_action_executed"
    AI_ACTION_APPROVED = "ai_action_approved"
    AI_ACTION_REJECTED = "ai_action_rejected"

    # Connector events
    CONNECTOR_STATUS_CHANGED = "connector_status_changed"
    CONNECTOR_ADDED = "connector_added"
    CONNECTOR_REMOVED = "connector_removed"

    # Data quality events
    DATA_QUALITY_INCIDENT = "data_quality_incident"
    DATA_QUALITY_RESOLVED = "data_quality_resolved"


# Metrics that can be affected by data changes
AFFECTED_METRICS = [
    "revenue",
    "roas",
    "cac",
    "aov",
    "orders",
    "sessions",
    "conversion_rate",
    "ad_spend",
    "ltv",
    "mrr",
]


class DataChangeEvent(Base, TimestampMixin, TenantScopedMixin):
    """
    Aggregated data change event for the debug panel.

    Summarizes changes that affect metric values without exposing
    raw logs, credentials, or sensitive implementation details.

    SECURITY:
    - tenant_id from JWT only
    - Read-only for all users
    - No raw logs or credentials
    - Aggregated into human-readable summaries

    Data is populated by the DataChangeAggregator service which:
    - Listens to sync completion events
    - Listens to AI action execution events
    - Listens to connector status changes
    - Listens to data quality incidents

    Attributes:
        id: Unique identifier (UUID)
        tenant_id: Tenant identifier from JWT
        event_type: Type of change event
        title: Human-readable title
        description: Detailed description (merchant-safe)
        affected_metrics: List of metrics affected by this change
        affected_connector_id: ID of affected connector (if applicable)
        affected_connector_name: Name of affected connector (if applicable)
        impact_summary: Summary of the impact (merchant-safe)
        affected_date_start: Start of affected date range
        affected_date_end: End of affected date range
        source_entity_type: Type of source entity (for linking)
        source_entity_id: ID of source entity (for linking)
        occurred_at: When the event occurred
    """
    __tablename__ = "data_change_events"

    id = Column(String(255), primary_key=True, default=generate_uuid)

    # Event type
    event_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of change event"
    )

    # Human-readable summary (merchant-safe, no sensitive data)
    title = Column(
        String(500),
        nullable=False,
        comment="Human-readable title"
    )
    description = Column(
        Text,
        nullable=False,
        comment="Detailed description (merchant-safe)"
    )

    # Affected metrics (for filtering)
    # Use JSON with JSONB variant for PostgreSQL compatibility
    affected_metrics = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        comment="List of metrics affected by this change"
    )

    # Affected connectors/sources
    affected_connector_id = Column(
        String(255),
        nullable=True,
        index=True,
        comment="ID of affected connector"
    )
    affected_connector_name = Column(
        String(255),
        nullable=True,
        comment="Name of affected connector (for display)"
    )

    # Impact details (merchant-safe summary)
    impact_summary = Column(
        Text,
        nullable=True,
        comment="Summary of the impact (merchant-safe)"
    )

    # Time range affected
    affected_date_start = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Start of affected date range"
    )
    affected_date_end = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="End of affected date range"
    )

    # Source reference (for linking to detailed views)
    source_entity_type = Column(
        String(100),
        nullable=True,
        comment="Type of source entity (e.g., 'sync_run', 'ai_action')"
    )
    source_entity_id = Column(
        String(255),
        nullable=True,
        comment="ID of source entity for detailed view"
    )

    # Event timestamp (when the change occurred)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        index=True,
        comment="When the event occurred"
    )

    __table_args__ = (
        Index(
            "ix_data_change_events_tenant_occurred",
            "tenant_id", "occurred_at"
        ),
        Index(
            "ix_data_change_events_tenant_type",
            "tenant_id", "event_type"
        ),
        Index(
            "ix_data_change_events_connector",
            "tenant_id", "affected_connector_id",
            postgresql_where=(affected_connector_id != None)
        ),
    )

    def __repr__(self) -> str:
        return f"<DataChangeEvent(id={self.id}, type={self.event_type}, title={self.title[:30]}...)>"
