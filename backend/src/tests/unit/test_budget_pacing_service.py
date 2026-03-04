"""
Unit tests for BudgetPacingService.

Layer 1 — Tests business logic with mocked DB session.
If these fail, the bug is in pacing math or CRUD logic.

Tests cover:
- CRUD operations (list, create, update, delete)
- Pacing calculations (pct_spent, pace_ratio, projected_total_cents)
- Status thresholds (on_pace, slightly_over, over_budget)
- Dollar-to-cents conversion from marketing_spend
- Edge cases (zero budget, disabled budgets, no spend data)
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.services.budget_pacing_service import BudgetPacingService
from src.models.ad_budget import AdBudget


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def tenant_id():
    return "tenant-test-123"


@pytest.fixture
def service(mock_db, tenant_id):
    return BudgetPacingService(mock_db, tenant_id)


@pytest.fixture
def sample_budget(tenant_id):
    budget = AdBudget(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        source_platform="meta",
        budget_monthly_cents=100000,  # $1,000
        start_date=date(2026, 1, 1),
        end_date=None,
        enabled=True,
    )
    return budget


class TestListBudgets:
    """list_budgets() should filter by tenant_id and order by platform."""

    def test_returns_budgets_for_tenant(self, service, mock_db, sample_budget):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_budget]
        mock_db.query.return_value = mock_query

        result = service.list_budgets()

        assert len(result) == 1
        assert result[0].source_platform == "meta"
        mock_db.query.assert_called_once_with(AdBudget)

    def test_returns_empty_list_when_none(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = service.list_budgets()
        assert result == []


class TestCreateBudget:
    """create_budget() generates UUID, commits, and returns the budget."""

    def test_creates_and_commits(self, service, mock_db):
        mock_db.refresh = Mock()

        with patch("src.services.budget_pacing_service.uuid.uuid4", return_value="test-uuid"):
            result = service.create_budget(
                source_platform="google",
                budget_monthly_cents=50000,
                start_date=date(2026, 3, 1),
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        added_budget = mock_db.add.call_args[0][0]
        assert added_budget.source_platform == "google"
        assert added_budget.budget_monthly_cents == 50000
        assert added_budget.tenant_id == "tenant-test-123"
        assert added_budget.id == "test-uuid"

    def test_sets_optional_end_date(self, service, mock_db):
        mock_db.refresh = Mock()

        service.create_budget(
            source_platform="meta",
            budget_monthly_cents=100000,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 12, 31),
        )

        added = mock_db.add.call_args[0][0]
        assert added.end_date == date(2026, 12, 31)


class TestUpdateBudget:
    """update_budget() applies partial kwargs, returns None if not found."""

    def test_applies_kwargs(self, service, mock_db, sample_budget):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_budget
        mock_db.query.return_value = mock_query
        mock_db.refresh = Mock()

        result = service.update_budget(sample_budget.id, budget_monthly_cents=200000)

        assert result is not None
        assert result.budget_monthly_cents == 200000
        mock_db.commit.assert_called_once()

    def test_returns_none_for_missing(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service.update_budget("nonexistent-id", budget_monthly_cents=999)
        assert result is None

    def test_ignores_unknown_kwargs(self, service, mock_db, sample_budget):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_budget
        mock_db.query.return_value = mock_query
        mock_db.refresh = Mock()

        result = service.update_budget(sample_budget.id, nonexistent_field="value")

        assert result is not None
        mock_db.commit.assert_called_once()


class TestDeleteBudget:
    """delete_budget() returns True/False and commits on success."""

    def test_deletes_existing(self, service, mock_db, sample_budget):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_budget
        mock_db.query.return_value = mock_query

        result = service.delete_budget(sample_budget.id)

        assert result is True
        mock_db.delete.assert_called_once_with(sample_budget)
        mock_db.commit.assert_called_once()

    def test_returns_false_for_missing(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service.delete_budget("nonexistent-id")
        assert result is False
        mock_db.delete.assert_not_called()


class TestGetPacing:
    """get_pacing() calculates spend ratios and status."""

    def _make_budget(self, tenant_id, platform="meta", cents=100000, enabled=True):
        return AdBudget(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            source_platform=platform,
            budget_monthly_cents=cents,
            start_date=date(2026, 1, 1),
            enabled=enabled,
        )

    def test_returns_empty_when_no_budgets(self, service, mock_db):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = service.get_pacing()
        assert result == []

    def test_excludes_disabled_budgets(self, service, mock_db, tenant_id):
        disabled = self._make_budget(tenant_id, enabled=False)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [disabled]
        mock_db.query.return_value = mock_query

        # Mock the raw SQL query for spend
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = service.get_pacing()
        assert result == []

    @patch("src.services.budget_pacing_service.date")
    def test_on_pace_status(self, mock_date, service, mock_db, tenant_id):
        """pace_ratio <= 1.1 → on_pace."""
        mock_date.today.return_value = date(2026, 3, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        budget = self._make_budget(tenant_id, "meta", 100000)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [budget]
        mock_db.query.return_value = mock_query

        # Spend $484 (48400 cents) out of $1000 budget, 15/31 = 48.4% through month
        # pct_spent = 48400/100000 = 0.484, pct_time = 15/31 ≈ 0.4839
        # pace_ratio = 0.484 / 0.4839 ≈ 1.0 → on_pace
        mock_row = Mock()
        mock_row.source_platform = "meta"
        mock_row.total_spend = "484.00"
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        result = service.get_pacing()

        assert len(result) == 1
        assert result[0]["status"] == "on_pace"
        assert result[0]["platform"] == "meta"
        assert result[0]["budget_cents"] == 100000
        assert result[0]["spent_cents"] == 48400  # $484 * 100

    @patch("src.services.budget_pacing_service.date")
    def test_slightly_over_status(self, mock_date, service, mock_db, tenant_id):
        """1.1 < pace_ratio <= 1.3 → slightly_over."""
        mock_date.today.return_value = date(2026, 3, 10)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        budget = self._make_budget(tenant_id, "meta", 100000)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [budget]
        mock_db.query.return_value = mock_query

        # 10/31 = 32.3% through month, but 40% of budget spent → pace_ratio ~1.24
        mock_row = Mock()
        mock_row.source_platform = "meta"
        mock_row.total_spend = "400.00"
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        result = service.get_pacing()
        assert result[0]["status"] == "slightly_over"

    @patch("src.services.budget_pacing_service.date")
    def test_over_budget_status(self, mock_date, service, mock_db, tenant_id):
        """pace_ratio > 1.3 → over_budget."""
        mock_date.today.return_value = date(2026, 3, 10)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        budget = self._make_budget(tenant_id, "meta", 100000)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [budget]
        mock_db.query.return_value = mock_query

        # 10/31 = 32.3% through month, but 60% of budget spent → pace_ratio ~1.86
        mock_row = Mock()
        mock_row.source_platform = "meta"
        mock_row.total_spend = "600.00"
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        result = service.get_pacing()
        assert result[0]["status"] == "over_budget"

    def test_no_spend_data_defaults_to_zero(self, service, mock_db, tenant_id):
        """When marketing_spend query fails, spend defaults to 0."""
        budget = self._make_budget(tenant_id, "meta", 100000)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [budget]
        mock_db.query.return_value = mock_query

        mock_db.execute.side_effect = Exception("analytics schema not found")

        result = service.get_pacing()
        assert len(result) == 1
        assert result[0]["spent_cents"] == 0
        assert result[0]["pct_spent"] == 0
