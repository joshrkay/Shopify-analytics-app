"""
E2E integration tests for Alerts.

Layer 5 — Full lifecycle via FastAPI TestClient with SQLite in-memory DB.
If these fail, the wiring between route → service → model is broken.

Tests cover:
- Create rule → List → Toggle → Delete lifecycle
- History endpoints
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.routes.alerts import router
from src.api.dependencies.entitlements import check_alerts_entitlement
from src.db_base import Base
# Import models so Base.metadata knows about them
from src.models.alert_rule import AlertRule, AlertExecution  # noqa: F401


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
    ctx.tenant_id = "tenant-e2e-alerts"
    ctx.user_id = "user-1"
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[check_alerts_entitlement] = lambda: db_session
    return app


@pytest.fixture
def client(app, mock_tenant_ctx):
    with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
        yield TestClient(app)


class TestAlertsE2E:
    """Full lifecycle: create → list → toggle → history → delete."""

    def test_full_rule_lifecycle(self, client, db_session):
        # 1. Create rule
        create_resp = client.post("/api/alerts/rules", json={
            "name": "ROAS Alert",
            "metric_name": "roas",
            "comparison_operator": "lt",
            "threshold_value": 2.0,
            "evaluation_period": "daily",
            "severity": "warning",
            "description": "Alert when ROAS drops below 2",
        })
        assert create_resp.status_code == 201
        rule = create_resp.json()
        rule_id = rule["id"]
        assert rule["name"] == "ROAS Alert"
        assert rule["enabled"] is True

        # 2. List rules — rule appears
        list_resp = client.get("/api/alerts/rules")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["count"] >= 1
        assert any(r["id"] == rule_id for r in data["rules"])

        # 3. Toggle off
        toggle_resp = client.patch(f"/api/alerts/rules/{rule_id}/toggle", json={
            "enabled": False,
        })
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["enabled"] is False

        # 4. Toggle back on
        toggle_resp2 = client.patch(f"/api/alerts/rules/{rule_id}/toggle", json={
            "enabled": True,
        })
        assert toggle_resp2.status_code == 200
        assert toggle_resp2.json()["enabled"] is True

        # 5. Update rule
        update_resp = client.put(f"/api/alerts/rules/{rule_id}", json={
            "name": "Updated ROAS Alert",
            "threshold_value": 1.5,
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated ROAS Alert"
        assert update_resp.json()["threshold_value"] == 1.5

        # 6. Delete rule
        delete_resp = client.delete(f"/api/alerts/rules/{rule_id}")
        assert delete_resp.status_code == 204

        # 7. List — rule gone
        list_resp2 = client.get("/api/alerts/rules")
        assert list_resp2.status_code == 200
        assert not any(r["id"] == rule_id for r in list_resp2.json()["rules"])

    def test_history_endpoints(self, client, db_session, mock_tenant_ctx):
        """Create rule + manually insert execution → verify history."""
        # Create a rule
        create_resp = client.post("/api/alerts/rules", json={
            "name": "Spend Alert",
            "metric_name": "spend",
            "comparison_operator": "gt",
            "threshold_value": 1000,
            "evaluation_period": "daily",
        })
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # Manually insert an execution
        import uuid
        execution = AlertExecution(
            id=str(uuid.uuid4()),
            tenant_id=mock_tenant_ctx.tenant_id,
            alert_rule_id=rule_id,
            fired_at=datetime.now(timezone.utc),
            metric_value=1500.0,
            threshold_value=1000.0,
        )
        db_session.add(execution)
        db_session.commit()

        # Get all history
        history_resp = client.get("/api/alerts/history")
        assert history_resp.status_code == 200
        executions = history_resp.json()
        assert len(executions) >= 1
        assert any(e["alert_rule_id"] == rule_id for e in executions)

        # Get rule-specific history
        rule_history_resp = client.get(f"/api/alerts/rules/{rule_id}/history")
        assert rule_history_resp.status_code == 200
        rule_executions = rule_history_resp.json()
        assert len(rule_executions) >= 1
        assert all(e["alert_rule_id"] == rule_id for e in rule_executions)

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/alerts/rules/nonexistent-id")
        assert resp.status_code == 404

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put("/api/alerts/rules/nonexistent-id", json={
            "name": "X",
        })
        assert resp.status_code == 404

    def test_toggle_nonexistent_returns_404(self, client):
        resp = client.patch("/api/alerts/rules/nonexistent-id/toggle", json={
            "enabled": True,
        })
        assert resp.status_code == 404
