"""
Integration tests for Cohort Analysis API.

Layer 2 — Tests HTTP request → response via FastAPI TestClient.
Uses dependency_overrides for DB session injection.
"""

import pytest
from datetime import date
from unittest.mock import Mock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.cohort_analysis import router
from src.api.dependencies.entitlements import check_cohort_analysis_entitlement


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-cohort-api"
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
    app.dependency_overrides[check_cohort_analysis_entitlement] = lambda: mock_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestGetCohortAnalysis:

    def test_returns_200_with_data(self, client, mock_tenant_ctx, mock_db):
        row = Mock(cohort_month=date(2026, 1, 1), period_number=0,
                   customers_total=50, customers_active=50,
                   retention_rate=1.0, cohort_revenue=2500.0, order_count=50)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        assert response.status_code == 200
        data = response.json()
        assert "cohorts" in data
        assert "summary" in data
        assert len(data["cohorts"]) == 1
        assert data["cohorts"][0]["cohort_month"] == "2026-01-01"

    def test_timeframe_3m_accepted(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis?timeframe=3m")

        assert response.status_code == 200

    def test_db_failure_returns_503(self, client, mock_tenant_ctx, mock_db):
        mock_db.execute.side_effect = Exception("connection refused")

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        assert response.status_code == 503
        assert "Cohort data unavailable" in response.json()["detail"]

    def test_empty_result_returns_zero_summary(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.cohort_analysis.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/analytics/cohort-analysis")

        assert response.status_code == 200
        data = response.json()
        assert data["cohorts"] == []
        assert data["summary"]["total_cohorts"] == 0
