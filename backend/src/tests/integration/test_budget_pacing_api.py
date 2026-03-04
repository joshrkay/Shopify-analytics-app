"""
Integration tests for Budget Pacing API.

Layer 2 — Tests HTTP request → response via FastAPI TestClient.
Uses dependency_overrides for DB session injection.
"""

import pytest
from datetime import date
from unittest.mock import Mock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.budget_pacing import router
from src.api.dependencies.entitlements import check_budget_pacing_entitlement
from src.models.ad_budget import AdBudget


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-budget-api"
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
    app.dependency_overrides[check_budget_pacing_entitlement] = lambda: mock_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def sample_budget():
    return AdBudget(
        id="budget-1",
        tenant_id="tenant-budget-api",
        source_platform="meta",
        budget_monthly_cents=100000,
        start_date=date(2026, 3, 1),
        end_date=None,
        enabled=True,
    )


class TestListBudgets:
    def test_returns_200_with_list(self, client, mock_tenant_ctx, sample_budget):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_budgets.return_value = [sample_budget]
                MockSvc.return_value = mock_svc

                response = client.get("/api/budgets")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "budget-1"
        assert data[0]["source_platform"] == "meta"
        assert data[0]["budget_monthly_cents"] == 100000

    def test_returns_empty_list(self, client, mock_tenant_ctx):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_budgets.return_value = []
                MockSvc.return_value = mock_svc

                response = client.get("/api/budgets")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateBudget:
    def test_returns_201_on_create(self, client, mock_tenant_ctx, sample_budget):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.create_budget.return_value = sample_budget
                MockSvc.return_value = mock_svc

                response = client.post("/api/budgets", json={
                    "source_platform": "meta",
                    "budget_monthly_cents": 100000,
                    "start_date": "2026-03-01",
                })

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "budget-1"
        assert data["source_platform"] == "meta"


class TestUpdateBudget:
    def test_returns_200_on_update(self, client, mock_tenant_ctx, sample_budget):
        sample_budget.budget_monthly_cents = 200000

        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.update_budget.return_value = sample_budget
                MockSvc.return_value = mock_svc

                response = client.put("/api/budgets/budget-1", json={
                    "budget_monthly_cents": 200000,
                })

        assert response.status_code == 200
        assert response.json()["budget_monthly_cents"] == 200000

    def test_returns_404_for_missing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.update_budget.return_value = None
                MockSvc.return_value = mock_svc

                response = client.put("/api/budgets/nonexistent", json={
                    "budget_monthly_cents": 999,
                })

        assert response.status_code == 404
        assert "Budget not found" in response.json()["detail"]


class TestDeleteBudget:
    def test_returns_204_on_delete(self, client, mock_tenant_ctx):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.delete_budget.return_value = True
                MockSvc.return_value = mock_svc

                response = client.delete("/api/budgets/budget-1")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.delete_budget.return_value = False
                MockSvc.return_value = mock_svc

                response = client.delete("/api/budgets/nonexistent")

        assert response.status_code == 404


class TestGetPacing:
    def test_returns_200_with_pacing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.budget_pacing.BudgetPacingService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.get_pacing.return_value = [{
                    "platform": "meta",
                    "budget_cents": 100000,
                    "spent_cents": 48400,
                    "pct_spent": 0.484,
                    "pct_time": 0.4839,
                    "pace_ratio": 1.0,
                    "projected_total_cents": 100041,
                    "status": "on_pace",
                    "budget_id": "budget-1",
                }]
                MockSvc.return_value = mock_svc

                response = client.get("/api/budget-pacing")

        assert response.status_code == 200
        data = response.json()
        assert "pacing" in data
        assert len(data["pacing"]) == 1
        assert data["pacing"][0]["platform"] == "meta"
        assert data["pacing"][0]["status"] == "on_pace"
