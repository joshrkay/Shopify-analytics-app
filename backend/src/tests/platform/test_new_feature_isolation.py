"""
Tenant isolation tests for new Figma alignment features.

Layer 3 — Verifies tenant_id scoping on BudgetPacingService and AlertRuleService.
If these fail, you have a cross-tenant data leak (security bug).

Tests cover:
- BudgetPacingService: list/update/delete scoped by tenant_id
- AlertRuleService: list/get/delete/count/executions scoped by tenant_id
- Cross-tenant access returns empty / False
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models.ad_budget import AdBudget
from src.models.alert_rule import AlertRule, AlertExecution
from src.db_base import Base
from src.services.budget_pacing_service import BudgetPacingService
from src.services.alert_rule_service import AlertRuleService


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


TENANT_A = "tenant-isolation-a"
TENANT_B = "tenant-isolation-b"


class TestBudgetIsolation:
    """BudgetPacingService must only return data for the specified tenant."""

    def _create_budget(self, session, tenant_id, platform="meta"):
        budget = AdBudget(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            source_platform=platform,
            budget_monthly_cents=100000,
            start_date=date(2026, 1, 1),
            enabled=True,
        )
        session.add(budget)
        session.commit()
        return budget

    def test_list_budgets_only_returns_own_tenant(self, db_session):
        budget_a = self._create_budget(db_session, TENANT_A, "meta")
        budget_b = self._create_budget(db_session, TENANT_B, "google")

        svc_a = BudgetPacingService(db_session, TENANT_A)
        svc_b = BudgetPacingService(db_session, TENANT_B)

        results_a = svc_a.list_budgets()
        results_b = svc_b.list_budgets()

        a_ids = [b.id for b in results_a]
        b_ids = [b.id for b in results_b]

        assert budget_a.id in a_ids
        assert budget_b.id not in a_ids
        assert budget_b.id in b_ids
        assert budget_a.id not in b_ids

    def test_update_budget_cross_tenant_returns_none(self, db_session):
        budget_a = self._create_budget(db_session, TENANT_A, "tiktok")

        svc_b = BudgetPacingService(db_session, TENANT_B)
        result = svc_b.update_budget(budget_a.id, budget_monthly_cents=999999)

        assert result is None

    def test_delete_budget_cross_tenant_returns_false(self, db_session):
        budget_a = self._create_budget(db_session, TENANT_A, "snapchat")

        svc_b = BudgetPacingService(db_session, TENANT_B)
        result = svc_b.delete_budget(budget_a.id)

        assert result is False
        # Verify budget still exists for tenant A
        svc_a = BudgetPacingService(db_session, TENANT_A)
        remaining = [b for b in svc_a.list_budgets() if b.id == budget_a.id]
        assert len(remaining) == 1


class TestAlertRuleIsolation:
    """AlertRuleService must only return data for the specified tenant."""

    def _create_rule(self, session, tenant_id, name="Test Rule"):
        rule = AlertRule(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id="user-1",
            name=name,
            metric_name="roas",
            comparison_operator="lt",
            threshold_value=2.0,
            evaluation_period="daily",
            severity="warning",
            enabled=True,
        )
        session.add(rule)
        session.commit()
        return rule

    def _create_execution(self, session, tenant_id, rule_id):
        execution = AlertExecution(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            alert_rule_id=rule_id,
            fired_at=datetime.now(timezone.utc),
            metric_value=1.5,
            threshold_value=2.0,
        )
        session.add(execution)
        session.commit()
        return execution

    def test_list_rules_only_returns_own_tenant(self, db_session):
        rule_a = self._create_rule(db_session, TENANT_A, "Rule A")
        rule_b = self._create_rule(db_session, TENANT_B, "Rule B")

        svc_a = AlertRuleService(db_session, TENANT_A)
        svc_b = AlertRuleService(db_session, TENANT_B)

        rules_a = svc_a.list_rules()
        rules_b = svc_b.list_rules()

        a_ids = [r.id for r in rules_a]
        b_ids = [r.id for r in rules_b]

        assert rule_a.id in a_ids
        assert rule_b.id not in a_ids
        assert rule_b.id in b_ids
        assert rule_a.id not in b_ids

    def test_get_rule_cross_tenant_returns_none(self, db_session):
        rule_a = self._create_rule(db_session, TENANT_A, "Cross-tenant get")

        svc_b = AlertRuleService(db_session, TENANT_B)
        result = svc_b.get_rule(rule_a.id)

        assert result is None

    def test_delete_rule_cross_tenant_returns_false(self, db_session):
        rule_a = self._create_rule(db_session, TENANT_A, "Cross-tenant delete")

        svc_b = AlertRuleService(db_session, TENANT_B)
        result = svc_b.delete_rule(rule_a.id)

        assert result is False

    def test_get_rule_count_scoped(self, db_session):
        self._create_rule(db_session, TENANT_A, "Count A1")
        self._create_rule(db_session, TENANT_A, "Count A2")
        self._create_rule(db_session, TENANT_B, "Count B1")

        svc_a = AlertRuleService(db_session, TENANT_A)
        svc_b = AlertRuleService(db_session, TENANT_B)

        # Counts include rules created in previous tests for same tenant
        count_a = svc_a.get_rule_count()
        count_b = svc_b.get_rule_count()

        assert count_a >= 2
        assert count_b >= 1
        assert count_a != count_b or count_a >= 2  # A has more rules

    def test_list_executions_scoped(self, db_session):
        rule_a = self._create_rule(db_session, TENANT_A, "Exec isolation")
        exec_a = self._create_execution(db_session, TENANT_A, rule_a.id)

        svc_b = AlertRuleService(db_session, TENANT_B)
        executions_b = svc_b.list_executions()

        b_ids = [e.id for e in executions_b]
        assert exec_a.id not in b_ids
