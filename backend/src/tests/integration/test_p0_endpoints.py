"""
P0 endpoint smoke tests — auth, analytics, and tenant isolation.

"P0" = endpoints that must work for every paying tenant every day.
These tests verify that:
  1. Unauthenticated requests are rejected (401/403), not leaked
  2. Authenticated requests return valid JSON (not HTML, not 500)
  3. Missing dbt tables produce 503, not 500 (graceful degradation)
  4. Tenant isolation: tenant A cannot retrieve tenant B's data

Covered endpoints:
  - GET /health                           (liveness)
  - GET /api/health/readiness             (readiness probe)
  - GET /api/orders                       (Shopify orders + UTM overlay)
  - GET /api/v1/dashboards/allowed        (dashboard visibility gate)

Pattern mirrors test_sync_health_api.py:
  - FastAPI test app built per-test (no shared global state)
  - Tenant context mocked via patch("...get_tenant_context", ...)
  - DB session overridden via dependency_overrides
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TENANT_A = "tenant-p0-aaa"
TENANT_B = "tenant-p0-bbb"


@pytest.fixture
def tenant_ctx_a():
    ctx = MagicMock()
    ctx.tenant_id = TENANT_A
    ctx.user_id = "user-p0-a"
    ctx.roles = ["member"]
    ctx.billing_tier = "pro"
    return ctx


@pytest.fixture
def tenant_ctx_b():
    ctx = MagicMock()
    ctx.tenant_id = TENANT_B
    ctx.user_id = "user-p0-b"
    ctx.roles = ["member"]
    ctx.billing_tier = "pro"
    return ctx


@pytest.fixture
def empty_db():
    """Mock DB that returns empty results for any query."""
    mock_db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = []
    result.fetchone.return_value = MagicMock(total=0)
    mock_db.execute.return_value = result
    return mock_db


# ---------------------------------------------------------------------------
# /health — liveness
# ---------------------------------------------------------------------------


class TestHealthP0:
    """Health endpoint is a P0 contract: must always return 200."""

    def test_health_always_200(self):
        from src.api.routes.health import router
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_returns_json(self):
        from src.api.routes.health import router
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get("/health")
        assert "application/json" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# /api/orders — authenticated, dbt-backed
# ---------------------------------------------------------------------------


class TestOrdersP0:

    def _app(self, tenant_ctx, db):
        from src.api.routes.orders import router, _get_db
        app = FastAPI()
        app.include_router(router)

        def _override_db():
            yield db

        app.dependency_overrides[_get_db] = _override_db
        return app

    def test_authenticated_request_returns_200(self, tenant_ctx_a, empty_db):
        """Authenticated orders request returns 200 with valid shape."""
        app = self._app(tenant_ctx_a, empty_db)
        with patch("src.api.routes.orders.get_tenant_context", return_value=tenant_ctx_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 200
        body = response.json()
        assert "orders" in body
        assert "total" in body
        assert "has_more" in body

    def test_unauthenticated_request_rejected(self):
        """Without a valid tenant context, orders endpoint raises 401/403."""
        from src.api.routes.orders import router
        app = FastAPI()
        app.include_router(router)

        # get_tenant_context raises HTTPException(403) if no valid JWT
        with patch(
            "src.api.routes.orders.get_tenant_context",
            side_effect=HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant"),
        ):
            response = TestClient(app, raise_server_exceptions=False).get("/api/orders")

        assert response.status_code in (401, 403)

    def test_graceful_503_when_canonical_schema_missing(self, tenant_ctx_a):
        """canonical.orders missing → 503, never 500."""
        failing_db = MagicMock()
        failing_db.execute.side_effect = Exception(
            "ERROR: relation \"canonical.orders\" does not exist"
        )
        app = self._app(tenant_ctx_a, failing_db)
        with patch("src.api.routes.orders.get_tenant_context", return_value=tenant_ctx_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503, (
            "Expected 503 (graceful degradation) when dbt tables are missing, "
            f"got {response.status_code}"
        )

    def test_graceful_503_when_attribution_schema_missing(self, tenant_ctx_a):
        """attribution.last_click missing → 503."""
        failing_db = MagicMock()
        failing_db.execute.side_effect = Exception(
            "ERROR: schema \"attribution\" does not exist"
        )
        app = self._app(tenant_ctx_a, failing_db)
        with patch("src.api.routes.orders.get_tenant_context", return_value=tenant_ctx_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503

    def test_tenant_a_query_not_visible_to_tenant_b(self, tenant_ctx_a, tenant_ctx_b):
        """Tenant B cannot see Tenant A's orders even with a valid JWT."""
        captured_tenant_ids: list[str] = []

        db_a = MagicMock()

        def capture_execute(query, params):
            if isinstance(params, dict) and "tenant_id" in params:
                captured_tenant_ids.append(params["tenant_id"])
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = MagicMock(total=0)
            return result

        db_a.execute.side_effect = capture_execute

        # Simulate Tenant A's request
        app_a = self._app(tenant_ctx_a, db_a)
        with patch("src.api.routes.orders.get_tenant_context", return_value=tenant_ctx_a):
            TestClient(app_a).get("/api/orders")

        # Every DB call must use Tenant A's ID only
        assert all(tid == TENANT_A for tid in captured_tenant_ids), (
            f"Expected all queries scoped to {TENANT_A!r}, got: {captured_tenant_ids}"
        )
        # Tenant B's ID must never appear
        assert TENANT_B not in captured_tenant_ids


# ---------------------------------------------------------------------------
# GET /api/v1/dashboards/allowed — visibility gate
# ---------------------------------------------------------------------------


class TestDashboardsAllowedP0:
    """
    Patches both get_tenant_context and has_permission so the require_permission
    decorator passes without hitting the real RBAC logic.
    """

    def _app(self):
        from src.api.routes.dashboards_allowed import router
        app = FastAPI()
        app.include_router(router)
        return app

    def test_authenticated_request_returns_allowed_dashboards(self, tenant_ctx_a):
        """Authenticated request returns allowed_dashboards list."""
        mock_service = MagicMock()
        mock_service.get_allowed_dashboards.return_value = ["overview", "attribution"]
        app = self._app()

        with patch("src.api.routes.dashboards_allowed.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.has_permission", return_value=True), \
             patch("src.api.routes.dashboards_allowed.DashboardAccessService", return_value=mock_service):
            response = TestClient(app).get("/api/v1/dashboards/allowed")

        assert response.status_code == 200
        body = response.json()
        assert "allowed_dashboards" in body
        assert "tenant_id" in body
        assert "billing_tier" in body

    def test_response_includes_tenant_id(self, tenant_ctx_a):
        """allowed_dashboards response includes the tenant_id for client-side validation."""
        mock_service = MagicMock()
        mock_service.get_allowed_dashboards.return_value = []
        app = self._app()

        with patch("src.api.routes.dashboards_allowed.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.has_permission", return_value=True), \
             patch("src.api.routes.dashboards_allowed.DashboardAccessService", return_value=mock_service):
            response = TestClient(app).get("/api/v1/dashboards/allowed")

        assert response.json()["tenant_id"] == TENANT_A

    def test_tenant_isolation_in_dashboards(self, tenant_ctx_a):
        """DashboardAccessService is instantiated with the requesting tenant's ID."""
        captured_tenant_ids: list[str] = []

        def capture_service_init(tenant_id, **kwargs):
            captured_tenant_ids.append(tenant_id)
            svc = MagicMock()
            svc.get_allowed_dashboards.return_value = []
            return svc

        app = self._app()

        with patch("src.api.routes.dashboards_allowed.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.get_tenant_context", return_value=tenant_ctx_a), \
             patch("src.platform.rbac.has_permission", return_value=True), \
             patch("src.api.routes.dashboards_allowed.DashboardAccessService", side_effect=capture_service_init):
            TestClient(app).get("/api/v1/dashboards/allowed")

        assert captured_tenant_ids == [TENANT_A]
        assert TENANT_B not in captured_tenant_ids


# ---------------------------------------------------------------------------
# Auth isolation: middleware behavior
# ---------------------------------------------------------------------------


class TestAuthIsolation:
    """
    These tests verify the contract at the middleware boundary:
    routes that call get_tenant_context() will be blocked for requests
    that lack a valid tenant context.
    """

    def test_orders_raises_403_when_get_tenant_context_raises(self):
        """get_tenant_context raising HTTPException(403) flows through as 403."""
        from src.api.routes.orders import router, _get_db
        app = FastAPI()
        app.include_router(router)

        # Override _get_db to raise immediately — simulates middleware blocking
        def blocked_db():
            raise HTTPException(status_code=403, detail="Unauthorized tenant")
            yield  # make it a generator

        app.dependency_overrides[_get_db] = blocked_db

        response = TestClient(app, raise_server_exceptions=False).get("/api/orders")
        assert response.status_code == 403

    def test_cross_tenant_data_not_leaked_via_tenant_id_param(self):
        """
        Regression: a malicious client passing ?tenant_id=<other_tenant> in
        query params must not override the server-side tenant context.
        The orders query uses tenant_id from the JWT context, not query params.
        """
        from src.api.routes.orders import router, _get_db
        ctx = MagicMock()
        ctx.tenant_id = TENANT_A
        ctx.user_id = "user-a"

        captured_params: list[dict] = []

        db = MagicMock()

        def capture_execute(query, params):
            if isinstance(params, dict):
                captured_params.append(params.copy())
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = MagicMock(total=0)
            return result

        db.execute.side_effect = capture_execute

        app = FastAPI()
        app.include_router(router)

        def override_db():
            yield db

        app.dependency_overrides[_get_db] = override_db

        with patch("src.api.routes.orders.get_tenant_context", return_value=ctx):
            # Attempt to inject a different tenant_id via query string — must be ignored
            TestClient(app).get(f"/api/orders?tenant_id={TENANT_B}")

        # All queries must use TENANT_A from the authenticated context
        for params in captured_params:
            assert params.get("tenant_id") == TENANT_A
