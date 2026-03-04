"""
Unit tests for AlertRuleService.

Layer 1 — Tests business logic with mocked DB session.
If these fail, the bug is in CRUD logic, comparison operators, or metric evaluation.

Tests cover:
- CRUD operations (list, create, get, update, delete, toggle)
- _compare() method for all 5 operators + unknown
- _get_metric_value() for roas, spend, revenue + error handling
- evaluate_rules() — triggered/not-triggered/error isolation
- get_rule_count()
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from src.services.alert_rule_service import AlertRuleService
from src.models.alert_rule import AlertRule, AlertExecution


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def tenant_id():
    return "tenant-test-456"


@pytest.fixture
def service(mock_db, tenant_id):
    return AlertRuleService(mock_db, tenant_id)


@pytest.fixture
def sample_rule(tenant_id):
    return AlertRule(
        id="rule-1",
        tenant_id=tenant_id,
        user_id="user-1",
        name="ROAS Alert",
        description="Alert when ROAS drops",
        metric_name="roas",
        comparison_operator="lt",
        threshold_value=2.0,
        evaluation_period="daily",
        severity="warning",
        enabled=True,
    )


class TestCompare:
    """_compare() tests all 5 operators."""

    def test_gt(self, service):
        assert service._compare(10, "gt", 5) is True
        assert service._compare(5, "gt", 5) is False
        assert service._compare(3, "gt", 5) is False

    def test_lt(self, service):
        assert service._compare(3, "lt", 5) is True
        assert service._compare(5, "lt", 5) is False
        assert service._compare(10, "lt", 5) is False

    def test_eq(self, service):
        assert service._compare(5, "eq", 5) is True
        assert service._compare(5.0, "eq", 5.0) is True
        assert service._compare(4.9, "eq", 5) is False

    def test_gte(self, service):
        assert service._compare(5, "gte", 5) is True
        assert service._compare(6, "gte", 5) is True
        assert service._compare(4, "gte", 5) is False

    def test_lte(self, service):
        assert service._compare(5, "lte", 5) is True
        assert service._compare(4, "lte", 5) is True
        assert service._compare(6, "lte", 5) is False

    def test_unknown_operator_returns_false(self, service):
        assert service._compare(5, "neq", 5) is False
        assert service._compare(5, "invalid", 5) is False


class TestListRules:
    def test_returns_tenant_rules(self, service, mock_db, sample_rule):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_rule]
        mock_db.query.return_value = mock_query

        result = service.list_rules()
        assert len(result) == 1
        assert result[0].name == "ROAS Alert"


class TestCreateRule:
    def test_creates_with_uuid(self, service, mock_db):
        mock_db.refresh = Mock()

        with patch("src.services.alert_rule_service.uuid.uuid4", return_value="test-rule-uuid"):
            result = service.create_rule(
                name="Spend Alert",
                metric_name="spend",
                comparison_operator="gt",
                threshold_value=1000,
                evaluation_period="daily",
                severity="critical",
                user_id="user-1",
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.id == "test-rule-uuid"
        assert added.name == "Spend Alert"
        assert added.metric_name == "spend"
        assert added.tenant_id == "tenant-test-456"


class TestUpdateRule:
    def test_applies_updates(self, service, mock_db, sample_rule):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_rule
        mock_db.query.return_value = mock_query
        mock_db.refresh = Mock()

        result = service.update_rule("rule-1", name="Updated Name", threshold_value=3.0)

        assert result.name == "Updated Name"
        assert result.threshold_value == 3.0
        mock_db.commit.assert_called_once()

    def test_returns_none_for_missing(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service.update_rule("nonexistent", name="X")
        assert result is None


class TestDeleteRule:
    def test_deletes_existing(self, service, mock_db, sample_rule):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_rule
        mock_db.query.return_value = mock_query

        assert service.delete_rule("rule-1") is True
        mock_db.delete.assert_called_once_with(sample_rule)

    def test_returns_false_for_missing(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        assert service.delete_rule("nonexistent") is False


class TestToggleRule:
    def test_toggle_delegates_to_update(self, service, mock_db, sample_rule):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_rule
        mock_db.query.return_value = mock_query
        mock_db.refresh = Mock()

        result = service.toggle_rule("rule-1", False)
        assert result.enabled is False


class TestGetRuleCount:
    def test_counts_tenant_rules(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 7
        mock_db.query.return_value = mock_query

        assert service.get_rule_count() == 7


class TestGetMetricValue:
    def test_roas_metric(self, service, mock_db):
        mock_row = Mock()
        mock_row.gross_roas = 3.5
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = service._get_metric_value("roas")
        assert result == 3.5

    def test_spend_metric(self, service, mock_db):
        mock_row = Mock()
        mock_row.spend = 1500.0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = service._get_metric_value("spend")
        assert result == 1500.0

    def test_revenue_metric(self, service, mock_db):
        mock_row = Mock()
        mock_row.total_revenue = 25000.0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = service._get_metric_value("revenue")
        assert result == 25000.0

    def test_returns_none_when_no_rows(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        assert service._get_metric_value("roas") is None

    def test_returns_none_on_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("connection lost")
        assert service._get_metric_value("roas") is None

    def test_returns_none_for_unknown_metric(self, service, mock_db):
        assert service._get_metric_value("unknown_metric") is None


class TestEvaluateRules:
    def test_triggered_rule_creates_execution(self, service, mock_db):
        rule = AlertRule(
            id="rule-1", tenant_id="tenant-test-456", name="Test",
            metric_name="roas", comparison_operator="lt",
            threshold_value=2.0, evaluation_period="daily",
            severity="warning", enabled=True,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [rule]
        mock_db.query.return_value = mock_query

        # ROAS = 1.5, threshold = 2.0, operator = lt → 1.5 < 2.0 → triggered
        mock_row = Mock()
        mock_row.gross_roas = 1.5
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        stats = service.evaluate_rules()

        assert stats["evaluated"] == 1
        assert stats["triggered"] == 1
        assert stats["errors"] == 0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_not_triggered_skips_execution(self, service, mock_db):
        rule = AlertRule(
            id="rule-1", tenant_id="tenant-test-456", name="Test",
            metric_name="roas", comparison_operator="lt",
            threshold_value=2.0, evaluation_period="daily",
            severity="warning", enabled=True,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [rule]
        mock_db.query.return_value = mock_query

        # ROAS = 3.0, threshold = 2.0, operator = lt → 3.0 < 2.0 = False → not triggered
        mock_row = Mock()
        mock_row.gross_roas = 3.0
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        stats = service.evaluate_rules()

        assert stats["evaluated"] == 1
        assert stats["triggered"] == 0
        mock_db.add.assert_not_called()

    def test_metric_failure_skips_rule_gracefully(self, service, mock_db):
        """When _get_metric_value fails internally, rule is skipped (None → continue)."""
        rule1 = AlertRule(
            id="rule-1", tenant_id="tenant-test-456", name="Bad Metric",
            metric_name="roas", comparison_operator="lt",
            threshold_value=2.0, evaluation_period="daily",
            severity="warning", enabled=True,
        )
        rule2 = AlertRule(
            id="rule-2", tenant_id="tenant-test-456", name="Good",
            metric_name="spend", comparison_operator="gt",
            threshold_value=500, evaluation_period="daily",
            severity="warning", enabled=True,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [rule1, rule2]
        mock_db.query.return_value = mock_query

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _get_metric_value catches this and returns None
                raise Exception("rule1 metric query failed")
            mock_row = Mock()
            mock_row.spend = 1000.0
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            return mock_result

        mock_db.execute.side_effect = side_effect

        stats = service.evaluate_rules()

        # Both evaluated, rule1 skipped (metric=None), rule2 triggered (1000 > 500)
        assert stats["evaluated"] == 2
        assert stats["errors"] == 0  # error handled inside _get_metric_value
        assert stats["triggered"] == 1
