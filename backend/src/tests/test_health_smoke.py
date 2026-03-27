"""
Health/startup smoke tests for MarkInsight API.

Verifies:
- /health returns 200 {"status": "ok"}
- /api/health/readiness returns proper structure (ready / not_ready)
- All critical route modules load without ImportError

A broken import in any route module crashes the *entire* FastAPI app on
startup — no routes serve, not just the broken one. These tests are the
earliest CI signal for that failure mode.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.health import router as health_router
from src.database.session import get_db_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def health_app():
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.fixture
def health_client(health_app):
    return TestClient(health_app)


@pytest.fixture
def ready_db_result():
    result = MagicMock()
    result.ready = True
    result.checked_tables = ["users", "tenants", "user_tenant_roles"]
    result.missing_tables = []
    return result


@pytest.fixture
def not_ready_db_result():
    result = MagicMock()
    result.ready = False
    result.checked_tables = ["users", "tenants", "user_tenant_roles"]
    result.missing_tables = ["users", "tenants"]
    return result


# ---------------------------------------------------------------------------
# /health — simple liveness probe
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_returns_200(self, health_client):
        response = health_client.get("/health")
        assert response.status_code == 200

    def test_returns_ok_body(self, health_client):
        response = health_client.get("/health")
        assert response.json() == {"status": "ok"}

    def test_no_auth_required(self, health_client):
        """Liveness probe must be reachable without any Authorization header."""
        response = health_client.get("/health")
        assert response.status_code != 401
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# /api/health/readiness — readiness probe
# ---------------------------------------------------------------------------


class TestReadinessEndpoint:
    def _app_with_db_result(self, mock_result):
        app = FastAPI()
        app.include_router(health_router)
        mock_db = MagicMock()
        app.dependency_overrides[get_db_session] = lambda: mock_db
        return app, mock_db, mock_result

    def test_ready_when_tables_exist(self, ready_db_result):
        app, mock_db, result = self._app_with_db_result(ready_db_result)
        with patch("src.api.routes.health.check_required_tables", return_value=result):
            client = TestClient(app)
            response = client.get("/api/health/readiness")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["identity_tables"]["missing"] == []

    def test_not_ready_when_tables_missing(self, not_ready_db_result):
        app, mock_db, result = self._app_with_db_result(not_ready_db_result)
        with patch("src.api.routes.health.check_required_tables", return_value=result):
            client = TestClient(app)
            response = client.get("/api/health/readiness")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_ready"
        assert len(data["checks"]["identity_tables"]["missing"]) > 0

    def test_readiness_includes_required_fields(self, ready_db_result):
        app, mock_db, result = self._app_with_db_result(ready_db_result)
        with patch("src.api.routes.health.check_required_tables", return_value=result):
            client = TestClient(app)
            response = client.get("/api/health/readiness")

        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "identity_tables" in data["checks"]
        assert "required" in data["checks"]["identity_tables"]
        assert "missing" in data["checks"]["identity_tables"]


# ---------------------------------------------------------------------------
# Route module import checks
#
# If any of these fail with ImportError / NameError, the app crashes on
# startup — CI catches it here before any route test runs.
# ---------------------------------------------------------------------------


class TestRouteModuleImports:
    """All critical route modules must import cleanly."""

    def test_health_module_loads(self):
        from src.api.routes import health
        assert health.router is not None

    def test_orders_module_loads(self):
        from src.api.routes import orders
        assert orders.router is not None

    def test_sources_module_loads(self):
        from src.api.routes import sources
        assert sources.router is not None

    def test_billing_module_loads(self):
        from src.api.routes import billing
        assert billing.router is not None

    def test_insights_module_loads(self):
        from src.api.routes import insights
        assert insights.router is not None

    def test_recommendations_module_loads(self):
        from src.api.routes import recommendations
        assert recommendations.router is not None

    def test_actions_module_loads(self):
        from src.api.routes import actions
        assert actions.router is not None

    def test_dashboards_allowed_module_loads(self):
        from src.api.routes import dashboards_allowed
        assert dashboards_allowed.router is not None

    def test_webhooks_clerk_module_loads(self):
        from src.api.routes import webhooks_clerk
        assert webhooks_clerk.router is not None

    def test_webhooks_shopify_module_loads(self):
        from src.api.routes import webhooks_shopify
        assert webhooks_shopify.router is not None

    def test_datasets_module_loads(self):
        from src.api.routes import datasets
        assert datasets.router is not None

    def test_channels_module_loads(self):
        from src.api.routes import channels
        assert channels.router is not None

    def test_attribution_module_loads(self):
        from src.api.routes import attribution
        assert attribution.router is not None

    def test_sync_health_module_loads(self):
        from src.api.dq import routes as sync_health
        assert sync_health.router is not None
