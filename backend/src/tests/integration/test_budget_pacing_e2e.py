"""
E2E integration tests for Budget Pacing.

Layer 5 — Full CRUD cycle via FastAPI TestClient with SQLite in-memory DB.
If these fail, the wiring between route → service → model is broken.

Tests cover:
- Create → List → Update → Delete lifecycle
- Pacing endpoint (with mocked marketing_spend raw SQL)
"""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.routes.budget_pacing import router
from src.api.dependencies.entitlements import check_budget_pacing_entitlement
from src.db_base import Base
# Import models so Base.metadata knows about them
from src.models.ad_budget import AdBudget  # noqa: F401


@pytest.fixture
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


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-e2e-budget"
    ctx.user_id = "user-1"
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[check_budget_pacing_entitlement] = lambda: db_session
    return app


@pytest.fixture
def client(app, mock_tenant_ctx):
    """Client with real DB session injected via dependency_overrides."""
    with patch("src.api.routes.budget_pacing.get_tenant_context", return_value=mock_tenant_ctx):
        yield TestClient(app)


class TestBudgetPacingE2E:
    """Full lifecycle: create → list → update → pacing → delete."""

    def test_full_crud_lifecycle(self, client, db_session):
        # 1. Create
        create_resp = client.post("/api/budgets", json={
            "source_platform": "meta",
            "budget_monthly_cents": 100000,
            "start_date": "2026-03-01",
        })
        assert create_resp.status_code == 201
        budget = create_resp.json()
        budget_id = budget["id"]
        assert budget["source_platform"] == "meta"
        assert budget["budget_monthly_cents"] == 100000
        assert budget["enabled"] is True

        # 2. List — budget appears
        list_resp = client.get("/api/budgets")
        assert list_resp.status_code == 200
        budgets = list_resp.json()
        assert any(b["id"] == budget_id for b in budgets)

        # 3. Update
        update_resp = client.put(f"/api/budgets/{budget_id}", json={
            "budget_monthly_cents": 200000,
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["budget_monthly_cents"] == 200000

        # 4. Delete
        delete_resp = client.delete(f"/api/budgets/{budget_id}")
        assert delete_resp.status_code == 204

        # 5. List — budget gone
        list_resp2 = client.get("/api/budgets")
        assert list_resp2.status_code == 200
        assert not any(b["id"] == budget_id for b in list_resp2.json())

    def test_pacing_endpoint_with_budget(self, client, db_session):
        """Pacing returns data when budgets exist (marketing_spend mocked)."""
        # Create an enabled budget
        create_resp = client.post("/api/budgets", json={
            "source_platform": "google",
            "budget_monthly_cents": 50000,
            "start_date": "2026-03-01",
        })
        assert create_resp.status_code == 201

        # The pacing endpoint queries analytics.marketing_spend via raw SQL.
        # In SQLite, this table doesn't exist, so the service gracefully
        # falls back to spend_by_platform = {} (zero spend).
        pacing_resp = client.get("/api/budget-pacing")
        assert pacing_resp.status_code == 200
        data = pacing_resp.json()
        assert "pacing" in data
        # Should have 1 pacing item for the "google" budget
        assert len(data["pacing"]) >= 1
        google_pacing = [p for p in data["pacing"] if p["platform"] == "google"]
        assert len(google_pacing) == 1
        assert google_pacing[0]["spent_cents"] == 0  # No spend data

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/budgets/nonexistent-id")
        assert resp.status_code == 404

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put("/api/budgets/nonexistent-id", json={
            "budget_monthly_cents": 999,
        })
        assert resp.status_code == 404

    def test_create_with_end_date(self, client):
        resp = client.post("/api/budgets", json={
            "source_platform": "tiktok",
            "budget_monthly_cents": 30000,
            "start_date": "2026-03-01",
            "end_date": "2026-12-31",
        })
        assert resp.status_code == 201
        assert resp.json()["end_date"] == "2026-12-31"
