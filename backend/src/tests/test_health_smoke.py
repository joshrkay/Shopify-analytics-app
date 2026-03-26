"""
Health Smoke Tests

Verifies:
- /health returns 200 with status ok
- /api/health/readiness endpoint is reachable
- App imports without crashing (all route modules load)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_app():
    """Minimal app with just the health routes — no middleware, no DB required."""
    from src.api.routes.health import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def health_client(health_app):
    return TestClient(health_app)


# ============================================================================
# /health
# ============================================================================


class TestHealthEndpoint:
    def test_health_returns_200(self, health_client):
        response = health_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, health_client):
        response = health_client.get("/health")
        assert response.headers["content-type"].startswith("application/json")

    def test_health_returns_status_ok(self, health_client):
        response = health_client.get("/health")
        body = response.json()
        assert body.get("status") == "ok"


# ============================================================================
# /api/health/readiness
# ============================================================================


class TestReadinessEndpoint:
    def test_readiness_returns_200_with_mocked_db(self, health_app):
        """Readiness probe returns 200 when DB check passes."""
        mock_db = MagicMock()

        from src.platform.db_readiness import DBReadinessResult

        mock_result = DBReadinessResult(
            ready=True,
            checked_tables=["users", "tenants"],
            missing_tables=[],
        )

        with patch(
            "src.api.routes.health.check_required_tables", return_value=mock_result
        ):
            with patch("src.api.routes.health.get_db_session", return_value=mock_db):
                client = TestClient(health_app)
                response = client.get("/api/health/readiness")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"

    def test_readiness_returns_not_ready_when_tables_missing(self, health_app):
        """Readiness probe reports not_ready when required tables are absent."""
        mock_db = MagicMock()

        from src.platform.db_readiness import DBReadinessResult

        mock_result = DBReadinessResult(
            ready=False,
            checked_tables=["users", "tenants"],
            missing_tables=["tenants"],
        )

        with patch(
            "src.api.routes.health.check_required_tables", return_value=mock_result
        ):
            with patch("src.api.routes.health.get_db_session", return_value=mock_db):
                client = TestClient(health_app)
                response = client.get("/api/health/readiness")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_ready"
        assert "tenants" in body["checks"]["identity_tables"]["missing"]


# ============================================================================
# App startup — all route modules must load without NameError
# ============================================================================


class TestAppStartup:
    def test_health_route_module_imports(self):
        """health.py must import without errors."""
        from src.api.routes import health  # noqa: F401

        assert hasattr(health, "router")

    def test_sources_route_module_imports(self):
        """sources.py must import without errors (most likely to have merge conflicts)."""
        from src.api.routes import sources  # noqa: F401

        assert hasattr(sources, "router")

    def test_billing_route_module_imports(self):
        from src.api.routes import billing  # noqa: F401

        assert hasattr(billing, "router")

    def test_orders_route_module_imports(self):
        from src.api.routes import orders  # noqa: F401

        assert hasattr(orders, "router")

    def test_insights_route_module_imports(self):
        from src.api.routes import insights  # noqa: F401

        assert hasattr(insights, "router")
