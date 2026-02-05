"""
Data Quality models for sync health monitoring.

Provides SQLAlchemy models for:
- DQCheck: Check definitions and thresholds
- DQResult: Per-run check execution results
- DQIncident: Severe failures and dashboard blocks
- SyncRun: Sync execution tracking with metrics
- BackfillJob: Merchant-triggered backfill requests

SECURITY: All tables are tenant-scoped via tenant_id from JWT.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Any

from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime,
    ForeignKey, Numeric, BigInteger, Index, JSON
)
from sqlalchemy.orm import relationship

from src.config.freshness_sla import get_sla_thresholds
from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin, generate_uuid


class DQCheckType(str, Enum):
    """Types of data quality checks."""
    FRESHNESS = "freshness"
    ROW_COUNT_DROP = "row_count_drop"
    ZERO_SPEND = "zero_spend"
    ZERO_ORDERS = "zero_orders"
    MISSING_DAYS = "missing_days"
    NEGATIVE_VALUES = "negative_values"
    DUPLICATE_PRIMARY_KEY = "duplicate_primary_key"


class DQSeverity(str, Enum):
    """Data quality issue severity levels."""
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class DQResultStatus(str, Enum):
    """Result status for a DQ check execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class DQIncidentStatus(str, Enum):
    """Status of a DQ incident."""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    AUTO_RESOLVED = "auto_resolved"


class SyncRunStatus(str, Enum):
    """Status of a sync run."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConnectorSourceType(str, Enum):
    """Connector source types with freshness SLAs."""
    # 2-hour SLA
    SHOPIFY_ORDERS = "shopify_orders"
    SHOPIFY_REFUNDS = "shopify_refunds"
    RECHARGE = "recharge"

    # 24-hour SLA
    META_ADS = "meta_ads"
    GOOGLE_ADS = "google_ads"
    TIKTOK_ADS = "tiktok_ads"
    PINTEREST_ADS = "pinterest_ads"
    SNAP_ADS = "snap_ads"
    AMAZON_ADS = "amazon_ads"
    KLAVIYO = "klaviyo"
    POSTSCRIPT = "postscript"
    ATTENTIVE = "attentive"
    GA4 = "ga4"


class BackfillJobStatus(str, Enum):
    """Status of a backfill job."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Map ConnectorSourceType to SLA config key (config/data_freshness_sla.yml).
# Sources not in config use the key of a similar source; config defaults apply.
CONNECTOR_SOURCE_TYPE_TO_SLA_KEY = {
    ConnectorSourceType.SHOPIFY_ORDERS: "shopify_orders",
    ConnectorSourceType.SHOPIFY_REFUNDS: "shopify_orders",
    ConnectorSourceType.RECHARGE: "shopify_orders",
    ConnectorSourceType.META_ADS: "facebook_ads",
    ConnectorSourceType.GOOGLE_ADS: "google_ads",
    ConnectorSourceType.TIKTOK_ADS: "tiktok_ads",
    ConnectorSourceType.PINTEREST_ADS: "facebook_ads",
    ConnectorSourceType.SNAP_ADS: "snapchat_ads",
    ConnectorSourceType.AMAZON_ADS: "facebook_ads",
    ConnectorSourceType.KLAVIYO: "email",
    ConnectorSourceType.POSTSCRIPT: "sms",
    ConnectorSourceType.ATTENTIVE: "sms",
    ConnectorSourceType.GA4: "google_ads",
}


def get_freshness_threshold(
    source_type: ConnectorSourceType,
    severity: DQSeverity,
    tier: str = "free",
) -> int:
    """
    Get freshness threshold in minutes for a source type, severity, and billing tier.

    Reads from config/data_freshness_sla.yml. Severity multipliers: warning = SLA,
    high = 2x, critical = 4x.
    """
    sla_key = CONNECTOR_SOURCE_TYPE_TO_SLA_KEY.get(
        source_type, "shopify_orders"
    )
    warn_minutes, _ = get_sla_thresholds(sla_key, tier)
    thresholds = {
        DQSeverity.WARNING.value: warn_minutes,
        DQSeverity.HIGH.value: warn_minutes * 2,
        DQSeverity.CRITICAL.value: warn_minutes * 4,
    }
    return thresholds.get(severity.value, warn_minutes)


def get_freshness_thresholds(
    source_type: ConnectorSourceType,
    tier: str = "free",
) -> dict:
    """
    Get warning, high, and critical thresholds in minutes (for severity calculation).

    Returns dict with keys "warning", "high", "critical".
    """
    sla_key = CONNECTOR_SOURCE_TYPE_TO_SLA_KEY.get(
        source_type, "shopify_orders"
    )
    warn_minutes, _ = get_sla_thresholds(sla_key, tier)
    return {
        "warning": warn_minutes,
        "high": warn_minutes * 2,
        "critical": warn_minutes * 4,
    }


def is_critical_source(source_type: ConnectorSourceType) -> bool:
    """Check if a source type is critical (Shopify, Recharge)."""
    return source_type in [
        ConnectorSourceType.SHOPIFY_ORDERS,
        ConnectorSourceType.SHOPIFY_REFUNDS,
        ConnectorSourceType.RECHARGE,
    ]


class DQCheck(Base, TimestampMixin):
    """
    Data quality check definition.

    Stores check configurations and thresholds.
    """
    __tablename__ = "dq_checks"

    id = Column(String(255), primary_key=True, default=generate_uuid)
    check_name = Column(String(255), nullable=False)
    check_type = Column(String(50), nullable=False)
    source_type = Column(String(50), nullable=True)

    # Thresholds (in minutes for freshness)
    warning_threshold = Column(Integer, nullable=True)
    high_threshold = Column(Integer, nullable=True)
    critical_threshold = Column(Integer, nullable=True)

    # For anomaly checks
    anomaly_threshold_percent = Column(Numeric(5, 2), nullable=True)

    # Behavior
    is_enabled = Column(Boolean, nullable=False, default=True)
    is_blocking = Column(Boolean, nullable=False, default=False)

    # Messages
    description = Column(Text, nullable=True)
    merchant_message = Column(Text, nullable=True)
    support_message = Column(Text, nullable=True)
    recommended_actions = Column(JSON, nullable=False, default=list)

    # Relationships
    results = relationship("DQResult", back_populates="check")
    incidents = relationship("DQIncident", back_populates="check")


class DQResult(Base, TenantScopedMixin):
    """
    Data quality check execution result.

    Stores per-run results for each check.
    SECURITY: tenant_id is from JWT only.
    """
    __tablename__ = "dq_results"

    id = Column(String(255), primary_key=True, default=generate_uuid)
    check_id = Column(String(255), ForeignKey("dq_checks.id"), nullable=False)
    connector_id = Column(String(255), nullable=False)
    run_id = Column(String(255), nullable=False)
    correlation_id = Column(String(255), nullable=True)

    # Result
    status = Column(String(20), nullable=False)
    severity = Column(String(20), nullable=True)

    # Observed values
    observed_value = Column(Numeric(20, 4), nullable=True)
    expected_value = Column(Numeric(20, 4), nullable=True)
    threshold_value = Column(Numeric(20, 4), nullable=True)
    minutes_since_sync = Column(Integer, nullable=True)

    # Messages
    message = Column(Text, nullable=True)
    merchant_message = Column(Text, nullable=True)
    support_details = Column(Text, nullable=True)

    # Context
    context_metadata = Column(JSON, nullable=False, default=dict)

    # Timestamps
    executed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    check = relationship("DQCheck", back_populates="results")

    __table_args__ = (
        Index("ix_dq_results_tenant_connector", "tenant_id", "connector_id"),
        Index("ix_dq_results_run_id", "run_id"),
    )


class DQIncident(Base, TenantScopedMixin, TimestampMixin):
    """
    Data quality incident for severe failures.

    Tracks critical issues that may block dashboards.
    SECURITY: tenant_id is from JWT only.
    """
    __tablename__ = "dq_incidents"

    id = Column(String(255), primary_key=True, default=generate_uuid)
    connector_id = Column(String(255), nullable=False)
    check_id = Column(String(255), ForeignKey("dq_checks.id"), nullable=False)
    result_id = Column(String(255), ForeignKey("dq_results.id"), nullable=True)
    run_id = Column(String(255), nullable=True)
    correlation_id = Column(String(255), nullable=True)

    # Incident details
    severity = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=DQIncidentStatus.OPEN.value)
    is_blocking = Column(Boolean, nullable=False, default=False)

    # Description
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Messages
    merchant_message = Column(Text, nullable=True)
    support_details = Column(Text, nullable=True)
    recommended_actions = Column(JSON, nullable=False, default=list)

    # Resolution tracking
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # When opened
    opened_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    check = relationship("DQCheck", back_populates="incidents")

    __table_args__ = (
        Index("ix_dq_incidents_tenant_connector", "tenant_id", "connector_id"),
        Index("ix_dq_incidents_status", "status"),
    )


class SyncRun(Base, TenantScopedMixin, TimestampMixin):
    """
    Sync run tracking with metrics.

    SECURITY: tenant_id is from JWT only.
    """
    __tablename__ = "sync_runs"

    run_id = Column(String(255), primary_key=True, default=generate_uuid)
    connector_id = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default=SyncRunStatus.RUNNING.value)
    source_type = Column(String(50), nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Metrics
    rows_synced = Column(Integer, nullable=True)
    rows_updated = Column(Integer, nullable=True)
    rows_deleted = Column(Integer, nullable=True)
    bytes_synced = Column(BigInteger, nullable=True)
    duration_seconds = Column(Numeric(10, 2), nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)

    # Metadata
    run_metadata = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_sync_runs_tenant_connector", "tenant_id", "connector_id"),
        Index("ix_sync_runs_status", "status"),
    )


class BackfillJob(Base, TenantScopedMixin, TimestampMixin):
    """
    Merchant-triggered backfill job.

    SECURITY: tenant_id is from JWT only.
    Max 90 days for merchants.
    """
    __tablename__ = "backfill_jobs"

    id = Column(String(255), primary_key=True, default=generate_uuid)
    connector_id = Column(String(255), nullable=False)

    # Date range
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    # Status
    status = Column(String(50), nullable=False, default=BackfillJobStatus.QUEUED.value)

    # Requesting user
    requested_by = Column(String(255), nullable=False)

    # Execution tracking
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Results
    rows_backfilled = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_backfill_jobs_tenant_connector", "tenant_id", "connector_id"),
        Index("ix_backfill_jobs_status", "status"),
    )


# Maximum backfill days for merchants
MAX_MERCHANT_BACKFILL_DAYS = 90
