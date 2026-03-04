"""Alert rule service — CRUD + threshold evaluation."""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.alert_rule import AlertRule, AlertExecution, ComparisonOperator, AlertSeverity, EvaluationPeriod

logger = logging.getLogger(__name__)


class AlertRuleService:

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def list_rules(self) -> List[AlertRule]:
        return (
            self.db.query(AlertRule)
            .filter(AlertRule.tenant_id == self.tenant_id)
            .order_by(AlertRule.created_at.desc())
            .all()
        )

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        return (
            self.db.query(AlertRule)
            .filter(AlertRule.id == rule_id, AlertRule.tenant_id == self.tenant_id)
            .first()
        )

    def create_rule(
        self,
        name: str,
        metric_name: str,
        comparison_operator: str,
        threshold_value: float,
        evaluation_period: str,
        severity: str = "warning",
        description: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> AlertRule:
        rule = AlertRule(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            user_id=user_id,
            name=name,
            description=description,
            metric_name=metric_name,
            comparison_operator=comparison_operator,
            threshold_value=threshold_value,
            evaluation_period=evaluation_period,
            severity=severity,
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update_rule(self, rule_id: str, **kwargs) -> Optional[AlertRule]:
        rule = self.get_rule(rule_id)
        if not rule:
            return None
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        rule = self.get_rule(rule_id)
        if not rule:
            return False
        self.db.delete(rule)
        self.db.commit()
        return True

    def toggle_rule(self, rule_id: str, enabled: bool) -> Optional[AlertRule]:
        return self.update_rule(rule_id, enabled=enabled)

    def get_rule_count(self) -> int:
        return (
            self.db.query(AlertRule)
            .filter(AlertRule.tenant_id == self.tenant_id)
            .count()
        )

    def list_executions(self, rule_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[AlertExecution]:
        query = (
            self.db.query(AlertExecution)
            .filter(AlertExecution.tenant_id == self.tenant_id)
        )
        if rule_id:
            query = query.filter(AlertExecution.alert_rule_id == rule_id)
        return (
            query
            .order_by(AlertExecution.fired_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def _compare(self, value: float, operator: str, threshold: float) -> bool:
        if operator == "gt":
            return value > threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "eq":
            return value == threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lte":
            return value <= threshold
        return False

    def evaluate_rules(self) -> dict:
        """Evaluate all enabled rules and create executions for triggered ones."""
        rules = (
            self.db.query(AlertRule)
            .filter(AlertRule.tenant_id == self.tenant_id, AlertRule.enabled == True)
            .all()
        )

        stats = {"evaluated": 0, "triggered": 0, "errors": 0}

        for rule in rules:
            stats["evaluated"] += 1
            try:
                value = self._get_metric_value(rule.metric_name)
                if value is None:
                    continue

                if self._compare(value, rule.comparison_operator, rule.threshold_value):
                    stats["triggered"] += 1
                    execution = AlertExecution(
                        id=str(uuid.uuid4()),
                        tenant_id=self.tenant_id,
                        alert_rule_id=rule.id,
                        fired_at=datetime.now(timezone.utc),
                        metric_value=value,
                        threshold_value=rule.threshold_value,
                    )
                    self.db.add(execution)

            except Exception as exc:
                stats["errors"] += 1
                logger.warning("Failed to evaluate rule %s: %s", rule.id, exc)

        self.db.commit()
        return stats

    def _get_metric_value(self, metric_name: str) -> Optional[float]:
        """Query the latest value for a named metric.

        Verified against dbt models:
          - marts.mart_marketing_metrics: gross_roas, spend columns
          - analytics.marketing_spend: spend column (per-row, not aggregated)
        """
        try:
            if metric_name == "roas":
                row = self.db.execute(text("""
                    SELECT gross_roas
                    FROM marts.mart_marketing_metrics
                    WHERE tenant_id = :tenant_id
                      AND period_type = 'last_7_days'
                    ORDER BY period_end DESC
                    LIMIT 1
                """), {"tenant_id": self.tenant_id}).fetchone()
                return float(row.gross_roas) if row and row.gross_roas else None

            elif metric_name == "spend":
                row = self.db.execute(text("""
                    SELECT spend
                    FROM marts.mart_marketing_metrics
                    WHERE tenant_id = :tenant_id
                      AND period_type = 'last_7_days'
                    ORDER BY period_end DESC
                    LIMIT 1
                """), {"tenant_id": self.tenant_id}).fetchone()
                return float(row.spend) if row and row.spend else None

            elif metric_name == "revenue":
                row = self.db.execute(text("""
                    SELECT SUM(revenue_gross) as total_revenue
                    FROM analytics.orders
                    WHERE tenant_id = :tenant_id
                      AND order_created_at >= current_date - interval '7 days'
                """), {"tenant_id": self.tenant_id}).fetchone()
                return float(row.total_revenue) if row and row.total_revenue else None

        except Exception as exc:
            logger.warning("Failed to get metric '%s': %s", metric_name, exc)

        return None
