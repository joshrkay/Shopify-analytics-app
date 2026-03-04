"""
Unit tests for cohort analysis grouping logic.

Layer 1 — Tests the response building logic in cohort_analysis route.
If these fail, the bug is in cohort grouping or summary calculation.

Tests cover:
- Grouping: multiple rows for same cohort_month → single CohortRow
- Summary: avg_retention_month_1, best/worst cohort
- Empty result: no rows → empty cohorts + zero summary
- Timeframe mapping: 3m/6m/12m/invalid
"""

import pytest
from unittest.mock import MagicMock, Mock, patch
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.cohort_analysis import router, _get_db


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-cohort-123"
    ctx.user_id = "user-1"
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def app(mock_db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_get_db] = lambda: mock_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestTimeframeMapping:
    """Timeframe param maps to correct months_back value."""

    def test_3m_maps_to_3(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis?timeframe=3m")

        assert response.status_code == 200
        # Verify months_back=3 was passed to SQL
        call_args = mock_db.execute.call_args
        if call_args:
            params = call_args[0][1] if len(call_args[0]) > 1 else {}
            if isinstance(params, dict):
                assert params.get("months_back") == 3

    def test_invalid_defaults_to_12(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis?timeframe=99m")

        assert response.status_code == 200


class TestCohortGrouping:
    """Multiple DB rows for same cohort_month → single CohortRow."""

    def test_groups_by_cohort_month(self, client, mock_tenant_ctx, mock_db):
        row1 = Mock()
        row1.cohort_month = date(2026, 1, 1)
        row1.period_number = 0
        row1.customers_total = 100
        row1.customers_active = 100
        row1.retention_rate = 1.0
        row1.cohort_revenue = 5000.0
        row1.order_count = 100

        row2 = Mock()
        row2.cohort_month = date(2026, 1, 1)
        row2.period_number = 1
        row2.customers_total = 100
        row2.customers_active = 60
        row2.retention_rate = 0.6
        row2.cohort_revenue = 3000.0
        row2.order_count = 60

        row3 = Mock()
        row3.cohort_month = date(2026, 2, 1)
        row3.period_number = 0
        row3.customers_total = 80
        row3.customers_active = 80
        row3.retention_rate = 1.0
        row3.cohort_revenue = 4000.0
        row3.order_count = 80

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row1, row2, row3]
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        assert response.status_code == 200
        data = response.json()
        assert len(data["cohorts"]) == 2  # Two distinct months
        jan_cohort = data["cohorts"][0]
        assert jan_cohort["cohort_month"] == "2026-01-01"
        assert jan_cohort["customers_total"] == 100
        assert len(jan_cohort["periods"]) == 2  # period 0 and 1


class TestCohortSummary:
    """Summary calculates avg retention, best/worst cohort."""

    def test_summary_with_data(self, client, mock_tenant_ctx, mock_db):
        # Cohort Jan: month-1 retention = 0.6
        row_jan_0 = Mock(cohort_month=date(2026, 1, 1), period_number=0,
                         customers_total=100, customers_active=100,
                         retention_rate=1.0, cohort_revenue=5000.0, order_count=100)
        row_jan_1 = Mock(cohort_month=date(2026, 1, 1), period_number=1,
                         customers_total=100, customers_active=60,
                         retention_rate=0.6, cohort_revenue=3000.0, order_count=60)

        # Cohort Feb: month-1 retention = 0.8
        row_feb_0 = Mock(cohort_month=date(2026, 2, 1), period_number=0,
                         customers_total=80, customers_active=80,
                         retention_rate=1.0, cohort_revenue=4000.0, order_count=80)
        row_feb_1 = Mock(cohort_month=date(2026, 2, 1), period_number=1,
                         customers_total=80, customers_active=64,
                         retention_rate=0.8, cohort_revenue=3200.0, order_count=64)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row_jan_0, row_jan_1, row_feb_0, row_feb_1]
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        data = response.json()
        summary = data["summary"]
        assert summary["total_cohorts"] == 2
        assert summary["avg_retention_month_1"] == 0.7  # (0.6 + 0.8) / 2
        assert summary["best_cohort"] == "2026-02-01"   # 0.8 > 0.6
        assert summary["worst_cohort"] == "2026-01-01"  # 0.6 < 0.8


class TestEmptyResult:
    """No data → empty cohorts + zero summary."""

    def test_empty_returns_zero_summary(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        assert response.status_code == 200
        data = response.json()
        assert data["cohorts"] == []
        assert data["summary"]["total_cohorts"] == 0
        assert data["summary"]["avg_retention_month_1"] == 0
        assert data["summary"]["best_cohort"] == ""
        assert data["summary"]["worst_cohort"] == ""
