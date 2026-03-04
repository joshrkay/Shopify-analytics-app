"""
Alert rule and execution models.

AlertRule: user-defined threshold monitoring rules.
AlertExecution: history of when rules fired.

SECURITY: Tenant isolation via TenantScopedMixin + RLS policies.

CRITICAL: All Enum() columns MUST include values_callable.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Float, Boolean, DateTime, Index, ForeignKey
from sqlalchemy import Enum as SAEnum

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class ComparisonOperator(str, enum.Enum):
    GT = "gt"
    LT = "lt"
    EQ = "eq"
    GTE = "gte"
    LTE = "lte"


class EvaluationPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertRule(Base, TimestampMixin, TenantScopedMixin):
    """User-defined alert rule with threshold monitoring."""

    __tablename__ = "alert_rules"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    metric_name = Column(String(100), nullable=False)
    comparison_operator = Column(
        SAEnum(ComparisonOperator, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    threshold_value = Column(Float, nullable=False)
    evaluation_period = Column(
        SAEnum(EvaluationPeriod, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    severity = Column(
        SAEnum(AlertSeverity, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=AlertSeverity.WARNING,
    )

    __table_args__ = (
        Index("ix_alert_rules_tenant_enabled", "tenant_id", "enabled"),
    )


class AlertExecution(Base, TimestampMixin, TenantScopedMixin):
    """Record of an alert rule firing."""

    __tablename__ = "alert_executions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_rule_id = Column(String(255), ForeignKey("alert_rules.id"), nullable=False, index=True)
    fired_at = Column(DateTime(timezone=True), nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    notification_id = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_alert_executions_tenant_rule", "tenant_id", "alert_rule_id"),
    )
