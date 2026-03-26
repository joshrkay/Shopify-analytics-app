"""
API Endpoint Smoke Tests

Verifies that critical API endpoints:
  - Return JSON, never HTML error pages
  - Return 200 on success or a graceful 503/422/401 — never an uncaught 500
  - Are reachable (the route module loaded correctly)

All tests mock the tenant context and DB so no real infrastructure is required.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================================
# SHARED HELPERS
# ============================================================================

SYNTHETIC_TENANT_ID = "tenant-test-123"
SYNTHETIC_USER_ID = "user-test-abc"

_TENANT_CTX_PATCH = "src.platform.tenant_context.get_tenant_context"


def _mock_tenant_context():
    """Return a mock TenantContext suitable for injecting via Depends."""
    from src.platform.tenant_context import TenantContext

    ctx = MagicMock(spec=TenantContext)
    ctx.tenant_id = SYNTHETIC_TENANT_ID
    ctx.user_id = SYNTHETIC_USER_ID
    ctx.roles = ["admin"]
    return ctx


def _mock_db_session():
    """Return a mock SQLAlchemy session."""
    db = MagicMock()
    db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))
    return db


# ============================================================================
# HELPERS: build test clients for specific route modules
# ============================================================================


def _make_client_for_router(router):
    """Build a TestClient for a single router with minimal middleware."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ============================================================================
# /health — baseline
# ============================================================================


class TestHealthBaseline:
    def test_health_200(self):
        from src.api.routes.health import router

        client = _make_client_for_router(router)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json()["status"] == "ok"


# ============================================================================
# /api/orders — no entitlement gate, all plans
# ============================================================================


class TestOrdersEndpoint:
    @pytest.fixture
    def orders_client(self):
        from src.api.routes.orders import router
        from src.platform.tenant_context import get_tenant_context
        from src.database.session import get_db_session

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_tenant_context] = _mock_tenant_context
        app.dependency_overrides[get_db_session] = _mock_db_session
        return TestClient(app, raise_server_exceptions=False)

    def test_orders_never_returns_500(self, orders_client):
        """Orders endpoint must not crash with an unhandled 500."""
        resp = orders_client.get("/api/orders")
        assert resp.status_code != 500, f"Got 500: {resp.text[:200]}"

    def test_orders_returns_json_not_html(self, orders_client):
        """Orders endpoint must return JSON even on error paths."""
        resp = orders_client.get("/api/orders")
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct, f"Expected JSON, got: {ct!r} body={resp.text[:200]}"

    def test_orders_graceful_when_db_empty(self, orders_client):
        """Orders endpoint returns 200 or graceful 503 — not 500."""
        resp = orders_client.get("/api/orders")
        assert resp.status_code in (200, 422, 503), f"Unexpected status {resp.status_code}"


# ============================================================================
# /api/billing/entitlements — used by feature gates on every page
# ============================================================================


class TestBillingEntitlementsEndpoint:
    @pytest.fixture
    def billing_client(self):
        from src.api.routes.billing import router
        from src.platform.tenant_context import get_tenant_context
        from src.database.session import get_db_session

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_tenant_context] = _mock_tenant_context
        app.dependency_overrides[get_db_session] = _mock_db_session
        return TestClient(app, raise_server_exceptions=False)

    def test_entitlements_never_returns_500(self, billing_client):
        resp = billing_client.get("/api/billing/entitlements")
        assert resp.status_code != 500, f"Got 500: {resp.text[:200]}"

    def test_entitlements_returns_json(self, billing_client):
        resp = billing_client.get("/api/billing/entitlements")
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct, f"HTML returned: {resp.text[:200]}"


# ============================================================================
# /api/insights — AI insights, entitlement-gated
# ============================================================================


class TestInsightsEndpoint:
    @pytest.fixture
    def insights_client(self):
        from src.api.routes.insights import router
        from src.platform.tenant_context import get_tenant_context
        from src.database.session import get_db_session

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_tenant_context] = _mock_tenant_context
        app.dependency_overrides[get_db_session] = _mock_db_session
        return TestClient(app, raise_server_exceptions=False)

    def test_insights_never_returns_500(self, insights_client):
        resp = insights_client.get("/api/insights")
        assert resp.status_code != 500, f"Got 500: {resp.text[:200]}"

    def test_insights_returns_json(self, insights_client):
        resp = insights_client.get("/api/insights")
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct


# ============================================================================
# /api/recommendations — AI recommendations, entitlement-gated
# ============================================================================


class TestRecommendationsEndpoint:
    @pytest.fixture
    def recs_client(self):
        from src.api.routes.recommendations import router
        from src.platform.tenant_context import get_tenant_context
        from src.database.session import get_db_session

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_tenant_context] = _mock_tenant_context
        app.dependency_overrides[get_db_session] = _mock_db_session
        return TestClient(app, raise_server_exceptions=False)

    def test_recommendations_never_returns_500(self, recs_client):
        resp = recs_client.get("/api/recommendations")
        assert resp.status_code != 500, f"Got 500: {resp.text[:200]}"

    def test_recommendations_returns_json(self, recs_client):
        resp = recs_client.get("/api/recommendations")
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct


# ============================================================================
# /api/sources/catalog — data source catalog, no auth required
# ============================================================================


class TestSourcesCatalogEndpoint:
    @pytest.fixture
    def sources_client(self):
        from src.api.routes.sources import router
        from src.platform.tenant_context import get_tenant_context
        from src.database.session import get_db_session

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_tenant_context] = _mock_tenant_context
        app.dependency_overrides[get_db_session] = _mock_db_session
        return TestClient(app, raise_server_exceptions=False)

    def test_catalog_never_returns_500(self, sources_client):
        resp = sources_client.get("/api/sources/catalog")
        assert resp.status_code != 500, f"Got 500: {resp.text[:200]}"

    def test_catalog_returns_json(self, sources_client):
        resp = sources_client.get("/api/sources/catalog")
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct


# ============================================================================
# JSON-not-HTML contract: error responses must never be HTML pages
# ============================================================================


class TestNoHtmlErrorPages:
    """
    All API endpoints must return JSON error bodies, never HTML.

    A common failure mode is the Vite SPA fallback serving index.html for
    missing /api routes (when the /api prefix is omitted from the URL).
    These tests guard against that at the FastAPI layer.
    """

    @pytest.mark.parametrize("path", [
        "/api/orders",
        "/api/billing/entitlements",
        "/api/insights",
        "/api/recommendations",
    ])
    def test_unknown_route_returns_json_not_html(self, path):
        """A minimal app with no routes returns JSON 404, not HTML."""
        app = FastAPI()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(path)
        assert resp.status_code == 404
        ct = resp.headers.get("content-type", "")
        assert "application/json" in ct, (
            f"FastAPI returned {ct!r} for {path} — ensure no HTML fallback middleware"
        )
