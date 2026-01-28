"""
AI Insights data models.

Provides:
- SQLAlchemy models for database persistence (AIInsight, AIInsightGenerationLog)
- Dataclasses for insight detection pipeline (InsightCandidate, MetricDelta, TenantMetrics)

SECURITY: All database models are tenant-scoped via tenant_id from JWT.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import (
    Column, String, Text, Numeric, DateTime, Date,
    Integer, Boolean, JSON, Index
)

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin, generate_uuid


# =============================================================================
# Enums
# =============================================================================

class InsightType(str, Enum):
    """Types of insights that can be detected."""
    SPEND_ANOMALY = "spend_anomaly"
    ROAS_CHANGE = "roas_change"
    REVENUE_SPEND_DIVERGENCE = "revenue_spend_divergence"
    CHANNEL_MIX_SHIFT = "channel_mix_shift"
    AOV_CHANGE = "aov_change"
    CONVERSION_RATE_CHANGE = "conversion_rate_change"
    CPA_ANOMALY = "cpa_anomaly"


class InsightCategory(str, Enum):
    """Categories of insights based on their nature."""
    ANOMALY = "anomaly"      # Unexpected deviation from normal
    TREND = "trend"          # Directional change over time
    OPPORTUNITY = "opportunity"  # Positive potential
    RISK = "risk"            # Negative potential


class InsightSeverity(str, Enum):
    """Severity levels for insights."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightStatus(str, Enum):
    """Status of an insight."""
    ACTIVE = "active"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class GenerationCadence(str, Enum):
    """How often insights are generated."""
    DAILY = "daily"
    HOURLY = "hourly"


class GenerationLogStatus(str, Enum):
    """Status of an insight generation run."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# SQLAlchemy Models
# =============================================================================

class AIInsight(Base, TenantScopedMixin, TimestampMixin):
    """
    AI-generated insight stored in the database.

    SECURITY: tenant_id is from JWT only, never from client input.
    """
    __tablename__ = "ai_insights"

    id = Column(String(255), primary_key=True, default=generate_uuid)

    # Insight identification
    insight_type = Column(String(50), nullable=False)
    insight_category = Column(String(50), nullable=False)

    # Content
    summary = Column(Text, nullable=False)
    supporting_metrics = Column(JSON, nullable=False, default=list)

    # Scoring
    confidence_score = Column(Numeric(3, 2), nullable=False)
    severity = Column(String(20), nullable=False, default=InsightSeverity.INFO.value)

    # Temporal context
    analysis_period_start = Column(Date, nullable=False)
    analysis_period_end = Column(Date, nullable=False)
    comparison_period_start = Column(Date, nullable=True)
    comparison_period_end = Column(Date, nullable=True)

    # Generation metadata
    generated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    generation_cadence = Column(String(20), nullable=False, default=GenerationCadence.DAILY.value)
    model_version = Column(String(20), nullable=False, default="v1.0")

    # Status
    status = Column(String(20), nullable=False, default=InsightStatus.ACTIVE.value)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_by = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_ai_insights_tenant_generated", "tenant_id", "generated_at"),
        Index("ix_ai_insights_tenant_type", "tenant_id", "insight_type"),
        Index("ix_ai_insights_tenant_status", "tenant_id", "status"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "insight_type": self.insight_type,
            "insight_category": self.insight_category,
            "summary": self.summary,
            "supporting_metrics": self.supporting_metrics,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "severity": self.severity,
            "analysis_period_start": self.analysis_period_start.isoformat() if self.analysis_period_start else None,
            "analysis_period_end": self.analysis_period_end.isoformat() if self.analysis_period_end else None,
            "comparison_period_start": self.comparison_period_start.isoformat() if self.comparison_period_start else None,
            "comparison_period_end": self.comparison_period_end.isoformat() if self.comparison_period_end else None,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "generation_cadence": self.generation_cadence,
            "model_version": self.model_version,
            "status": self.status,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AIInsightGenerationLog(Base, TenantScopedMixin):
    """
    Log entry for insight generation runs.

    Used for monitoring and debugging insight generation.
    """
    __tablename__ = "ai_insight_generation_logs"

    id = Column(String(255), primary_key=True, default=generate_uuid)

    # Run identification
    run_id = Column(String(255), nullable=False)

    # Execution details
    cadence = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default=GenerationLogStatus.RUNNING.value)

    # Results
    insights_generated = Column(Integer, default=0)
    detectors_run = Column(Integer, default=0)
    metrics_analyzed = Column(JSON, default=dict)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)

    # Analysis period
    analysis_date = Column(Date, nullable=False)

    # Audit
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ai_insight_logs_tenant", "tenant_id"),
        Index("ix_ai_insight_logs_run", "run_id"),
        Index("ix_ai_insight_logs_started", "started_at"),
    )


# =============================================================================
# Dataclasses for Insight Detection Pipeline
# =============================================================================

@dataclass
class MetricDelta:
    """
    Represents a change in a metric value.

    Used in supporting_metrics to document what triggered an insight.
    """
    metric_name: str
    current_value: Decimal
    previous_value: Decimal
    delta_absolute: Decimal
    delta_percent: Optional[float]
    timeframe: str  # "WoW", "MoM", "DoD"
    unit: str  # "USD", "ratio", "percentage", "count", "percentage_points"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "metric_name": self.metric_name,
            "current_value": float(self.current_value),
            "previous_value": float(self.previous_value),
            "delta_absolute": float(self.delta_absolute),
            "delta_percent": self.delta_percent,
            "timeframe": self.timeframe,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetricDelta":
        """Create from dictionary."""
        return cls(
            metric_name=data["metric_name"],
            current_value=Decimal(str(data["current_value"])),
            previous_value=Decimal(str(data["previous_value"])),
            delta_absolute=Decimal(str(data["delta_absolute"])),
            delta_percent=data.get("delta_percent"),
            timeframe=data["timeframe"],
            unit=data["unit"],
        )


@dataclass
class InsightCandidate:
    """
    A candidate insight before it's persisted.

    Produced by detectors, consumed by the insight service for
    validation, formatting, and persistence.
    """
    insight_type: InsightType
    category: InsightCategory
    severity: str
    confidence_score: float
    metrics: list[MetricDelta]
    context: Optional[dict] = None

    def __post_init__(self):
        """Validate confidence score range."""
        if not 0 <= self.confidence_score <= 1:
            raise ValueError(f"confidence_score must be between 0 and 1, got {self.confidence_score}")
        if self.severity not in [s.value for s in InsightSeverity]:
            raise ValueError(f"Invalid severity: {self.severity}")


@dataclass
class ChannelSpend:
    """Spend for a single marketing channel."""
    channel: str
    spend: Decimal

    def to_dict(self) -> dict:
        return {"channel": self.channel, "spend": float(self.spend)}


@dataclass
class TenantMetrics:
    """
    Aggregated metrics for a tenant used in insight detection.

    Fetched from dbt marts (fact_orders, fact_ad_spend, fact_campaign_performance).
    """
    tenant_id: str

    # Time periods
    current_period_start: date
    current_period_end: date
    previous_period_start: date
    previous_period_end: date

    # Revenue metrics (from fact_orders)
    current_week_revenue: Decimal = Decimal("0")
    previous_week_revenue: Decimal = Decimal("0")
    current_week_orders: int = 0
    previous_week_orders: int = 0
    current_week_aov: Decimal = Decimal("0")
    previous_week_aov: Decimal = Decimal("0")

    # Spend metrics (from fact_ad_spend)
    current_week_spend: Decimal = Decimal("0")
    previous_week_spend: Decimal = Decimal("0")
    current_week_channel_spend: list[ChannelSpend] = field(default_factory=list)
    previous_week_channel_spend: list[ChannelSpend] = field(default_factory=list)

    # Campaign metrics (from fact_campaign_performance)
    current_week_impressions: int = 0
    current_week_clicks: int = 0
    current_week_conversions: int = 0
    previous_week_conversions: int = 0

    # Statistical context
    spend_std_dev: Decimal = Decimal("0")
    revenue_std_dev: Decimal = Decimal("0")
    days_with_data: int = 0

    @property
    def has_sufficient_data(self) -> bool:
        """Check if there's enough data for meaningful analysis."""
        return (
            self.days_with_data >= 5 and
            (self.current_week_spend > 0 or self.current_week_revenue > 0)
        )

    @property
    def current_week_roas(self) -> Decimal:
        """Calculate current week ROAS."""
        if self.current_week_spend > 0:
            return self.current_week_revenue / self.current_week_spend
        return Decimal("0")

    @property
    def previous_week_roas(self) -> Decimal:
        """Calculate previous week ROAS."""
        if self.previous_week_spend > 0:
            return self.previous_week_revenue / self.previous_week_spend
        return Decimal("0")

    @property
    def current_week_cpa(self) -> Decimal:
        """Calculate current week CPA (cost per acquisition)."""
        if self.current_week_conversions > 0:
            return self.current_week_spend / Decimal(str(self.current_week_conversions))
        return Decimal("0")

    @property
    def previous_week_cpa(self) -> Decimal:
        """Calculate previous week CPA."""
        if self.previous_week_conversions > 0:
            return self.previous_week_spend / Decimal(str(self.previous_week_conversions))
        return Decimal("0")

    @property
    def current_week_ctr(self) -> Decimal:
        """Calculate current week CTR (click-through rate)."""
        if self.current_week_impressions > 0:
            return (Decimal(str(self.current_week_clicks)) / Decimal(str(self.current_week_impressions))) * 100
        return Decimal("0")


@dataclass
class InsightGenerationResult:
    """Result of insight generation for a tenant."""
    tenant_id: str
    insights_generated: int
    insights: list[Any]  # List of AIInsight or InsightCandidate
    duration_ms: int
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if generation was successful (no fatal errors)."""
        return len(self.errors) == 0 or self.insights_generated > 0
