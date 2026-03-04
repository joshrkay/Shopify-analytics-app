"""
Integration tests for Alerts API.

Layer 2 — Tests HTTP request → response via FastAPI TestClient.
Uses dependency_overrides for DB session injection.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.alerts import router
from src.api.dependencies.entitlements import check_alerts_entitlement
from src.models.alert_rule import AlertRule, AlertExecution


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-alerts-api"
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
    app.dependency_overrides[check_alerts_entitlement] = lambda: mock_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def sample_rule():
    return AlertRule(
        id="rule-1",
        tenant_id="tenant-alerts-api",
        user_id="user-1",
        name="ROAS Alert",
        description="Low ROAS warning",
        metric_name="roas",
        comparison_operator="lt",
        threshold_value=2.0,
        evaluation_period="daily",
        severity="warning",
        enabled=True,
    )


@pytest.fixture
def sample_execution():
    return AlertExecution(
        id="exec-1",
        tenant_id="tenant-alerts-api",
        alert_rule_id="rule-1",
        fired_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        metric_value=1.5,
        threshold_value=2.0,
        resolved_at=None,
    )


class TestListRules:
    def test_returns_200_with_rules(self, client, mock_tenant_ctx, sample_rule):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_rules.return_value = [sample_rule]
                mock_svc.get_rule_count.return_value = 1
                MockSvc.return_value = mock_svc

                response = client.get("/api/alerts/rules")

        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["rules"][0]["name"] == "ROAS Alert"
        assert data["rules"][0]["metric_name"] == "roas"


class TestCreateRule:
    def test_returns_201_on_create(self, client, mock_tenant_ctx, sample_rule):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.create_rule.return_value = sample_rule
                MockSvc.return_value = mock_svc

                response = client.post("/api/alerts/rules", json={
                    "name": "ROAS Alert",
                    "metric_name": "roas",
                    "comparison_operator": "lt",
                    "threshold_value": 2.0,
                    "evaluation_period": "daily",
                    "severity": "warning",
                })

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "rule-1"
        assert data["name"] == "ROAS Alert"


class TestUpdateRule:
    def test_returns_200_on_update(self, client, mock_tenant_ctx, sample_rule):
        sample_rule.name = "Updated ROAS Alert"

        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.update_rule.return_value = sample_rule
                MockSvc.return_value = mock_svc

                response = client.put("/api/alerts/rules/rule-1", json={
                    "name": "Updated ROAS Alert",
                })

        assert response.status_code == 200
        assert response.json()["name"] == "Updated ROAS Alert"

    def test_returns_404_for_missing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.update_rule.return_value = None
                MockSvc.return_value = mock_svc

                response = client.put("/api/alerts/rules/nonexistent", json={
                    "name": "X",
                })

        assert response.status_code == 404
        assert "Rule not found" in response.json()["detail"]


class TestDeleteRule:
    def test_returns_204_on_delete(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.delete_rule.return_value = True
                MockSvc.return_value = mock_svc

                response = client.delete("/api/alerts/rules/rule-1")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.delete_rule.return_value = False
                MockSvc.return_value = mock_svc

                response = client.delete("/api/alerts/rules/nonexistent")

        assert response.status_code == 404


class TestToggleRule:
    def test_toggle_returns_200(self, client, mock_tenant_ctx, sample_rule):
        sample_rule.enabled = False

        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.toggle_rule.return_value = sample_rule
                MockSvc.return_value = mock_svc

                response = client.patch("/api/alerts/rules/rule-1/toggle", json={
                    "enabled": False,
                })

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_toggle_404_for_missing(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.toggle_rule.return_value = None
                MockSvc.return_value = mock_svc

                response = client.patch("/api/alerts/rules/nonexistent/toggle", json={
                    "enabled": True,
                })

        assert response.status_code == 404


class TestListHistory:
    def test_returns_200_with_executions(self, client, mock_tenant_ctx, sample_execution):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_executions.return_value = [sample_execution]
                MockSvc.return_value = mock_svc

                response = client.get("/api/alerts/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["alert_rule_id"] == "rule-1"
        assert data[0]["metric_value"] == 1.5

    def test_pagination_params_forwarded(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_executions.return_value = []
                MockSvc.return_value = mock_svc

                response = client.get("/api/alerts/history?limit=10&offset=5")

        assert response.status_code == 200
        MockSvc.return_value.list_executions.assert_called_once_with(limit=10, offset=5)


class TestRuleHistory:
    def test_returns_200_filtered_by_rule(self, client, mock_tenant_ctx, sample_execution):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            with patch("src.api.routes.alerts.AlertRuleService") as MockSvc:
                mock_svc = MagicMock()
                mock_svc.list_executions.return_value = [sample_execution]
                MockSvc.return_value = mock_svc

                response = client.get("/api/alerts/rules/rule-1/history")

        assert response.status_code == 200
        MockSvc.return_value.list_executions.assert_called_once_with(
            rule_id="rule-1", limit=50, offset=0,
        )


class TestSchemaValidation:
    """Verify Literal-typed enum fields reject invalid values with 422."""

    def test_invalid_comparison_operator_returns_422(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.post("/api/alerts/rules", json={
                "name": "Bad Rule",
                "metric_name": "roas",
                "comparison_operator": "invalid_op",
                "threshold_value": 2.0,
                "evaluation_period": "daily",
                "severity": "warning",
            })
        assert response.status_code == 422

    def test_invalid_evaluation_period_returns_422(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.post("/api/alerts/rules", json={
                "name": "Bad Rule",
                "metric_name": "roas",
                "comparison_operator": "lt",
                "threshold_value": 2.0,
                "evaluation_period": "last_7_days",
                "severity": "warning",
            })
        assert response.status_code == 422

    def test_invalid_severity_returns_422(self, client, mock_tenant_ctx):
        with patch("src.api.routes.alerts.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.post("/api/alerts/rules", json={
                "name": "Bad Rule",
                "metric_name": "roas",
                "comparison_operator": "lt",
                "threshold_value": 2.0,
                "evaluation_period": "daily",
                "severity": "extreme",
            })
        assert response.status_code == 422
