"""
Integration tests for the Orders API endpoint.

GET /api/orders — paginated Shopify order list with UTM attribution overlay.

Tests cover:
- 200 with empty list when no data exists (not 500)
- 200 with order rows when data exists
- Graceful degradation (503) when dbt tables (canonical.orders /
  attribution.last_click) are missing — never a raw 500
- Tenant isolation — query is always scoped to the requesting tenant's ID
- Valid timeframe parameters are all accepted
- Pagination parameters (limit / offset)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.orders import router, _get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_A = "tenant-aaa-001"
TENANT_B = "tenant-bbb-002"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tenant_context_a():
    ctx = MagicMock()
    ctx.tenant_id = TENANT_A
    ctx.user_id = "user-a-001"
    return ctx


@pytest.fixture
def mock_tenant_context_b():
    ctx = MagicMock()
    ctx.tenant_id = TENANT_B
    ctx.user_id = "user-b-001"
    return ctx


def _make_order_row(
    order_id: str,
    revenue: float = 99.99,
    currency: str = "USD",
    financial_status: str = "paid",
    utm_source: str | None = "google",
):
    """Build a mock DB row that mirrors the columns selected by orders.py."""
    row = MagicMock()
    row.order_id = order_id
    row.order_number = "1001"
    row.order_name = "#1001"
    row.revenue = revenue
    row.currency = currency
    row.financial_status = financial_status
    row.created_at = datetime(2024, 3, 15, tzinfo=timezone.utc)
    row.utm_source = utm_source
    row.utm_medium = "cpc"
    row.utm_campaign = "spring-sale"
    row.platform = "google_ads"
    return row


def _make_db_mock(rows, total: int):
    """Return a mock DB session whose execute() mimics the two SQL calls in get_orders."""
    mock_db = MagicMock()
    count_row = MagicMock()
    count_row.total = total

    # execute() is called twice: fetchall() for rows, fetchone() for count
    execute_result = MagicMock()
    execute_result.fetchall.return_value = rows
    execute_result.fetchone.return_value = count_row
    mock_db.execute.return_value = execute_result
    return mock_db


def _make_app(mock_tenant_ctx, mock_db):
    """Create a test FastAPI app with orders router and dependency overrides."""
    app = FastAPI()
    app.include_router(router)

    def override_db():
        yield mock_db

    app.dependency_overrides[_get_db] = override_db
    return app


# ---------------------------------------------------------------------------
# Tests: basic response shape
# ---------------------------------------------------------------------------


class TestOrdersResponseShape:

    def test_empty_list_returns_200(self, mock_tenant_context_a):
        """When orders table is empty, returns 200 with empty list — not 500."""
        mock_db = _make_db_mock(rows=[], total=0)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_order_list_returns_correct_fields(self, mock_tenant_context_a):
        """Returned order objects include all expected fields."""
        row = _make_order_row("order-001", revenue=250.0)
        mock_db = _make_db_mock(rows=[row], total=1)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 200
        orders = response.json()["orders"]
        assert len(orders) == 1
        o = orders[0]
        assert o["order_id"] == "order-001"
        assert o["revenue"] == 250.0
        assert o["currency"] == "USD"
        assert o["financial_status"] == "paid"
        assert o["utm_source"] == "google"
        assert o["utm_campaign"] == "spring-sale"
        assert o["platform"] == "google_ads"

    def test_has_more_when_more_pages_exist(self, mock_tenant_context_a):
        """has_more is True when total > offset + limit."""
        rows = [_make_order_row(f"order-{i}") for i in range(50)]
        mock_db = _make_db_mock(rows=rows, total=150)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders?limit=50&offset=0")

        assert response.status_code == 200
        assert response.json()["has_more"] is True

    def test_has_more_false_on_last_page(self, mock_tenant_context_a):
        """has_more is False when offset + limit >= total."""
        rows = [_make_order_row(f"order-{i}") for i in range(10)]
        mock_db = _make_db_mock(rows=rows, total=10)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders?limit=50&offset=0")

        assert response.json()["has_more"] is False

    def test_null_utm_fields_returned_as_none(self, mock_tenant_context_a):
        """Orders with no UTM attribution return null fields, not missing keys."""
        row = _make_order_row("order-no-utm", utm_source=None)
        row.utm_medium = None
        row.utm_campaign = None
        row.platform = None
        mock_db = _make_db_mock(rows=[row], total=1)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        o = response.json()["orders"][0]
        assert o["utm_source"] is None
        assert o["platform"] is None


# ---------------------------------------------------------------------------
# Tests: graceful degradation — dbt tables missing
# ---------------------------------------------------------------------------


class TestOrdersGracefulDegradation:
    """
    When the dbt warehouse tables (canonical.orders, attribution.last_click)
    don't exist, the endpoint must return 503 — not 500 — and never crash.

    This is the canonical scenario for a fresh tenant or broken dbt run.
    """

    def test_returns_503_when_orders_table_missing(self, mock_tenant_context_a):
        """canonical.orders missing → 503, not 500."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception(
            "relation \"canonical.orders\" does not exist"
        )
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503

    def test_returns_503_when_attribution_table_missing(self, mock_tenant_context_a):
        """attribution.last_click missing → 503, not 500."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception(
            "relation \"attribution.last_click\" does not exist"
        )
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503

    def test_503_response_has_detail_field(self, mock_tenant_context_a):
        """503 response includes a human-readable detail message."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("table not found")
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert len(data["detail"]) > 0

    def test_never_returns_500_on_db_error(self, mock_tenant_context_a):
        """A raw DB error should never surface as HTTP 500 to the client."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("unexpected DB failure")
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code != 500, (
            "Orders endpoint must catch all DB errors and return 503, not 500"
        )

    def test_marts_table_error_returns_503(self, mock_tenant_context_a):
        """Any analytics schema error (marts/canonical/attribution) returns 503."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception(
            "schema \"canonical\" does not exist"
        )
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Tests: tenant isolation
# ---------------------------------------------------------------------------


class TestOrdersTenantIsolation:
    """
    Every SQL query in get_orders must be scoped to the requesting tenant's ID.
    Cross-tenant data must never be returned.
    """

    def test_query_scoped_to_requesting_tenant(self, mock_tenant_context_a):
        """The tenant_id bind parameter must equal the requesting tenant's ID."""
        captured_params = []

        mock_db = MagicMock()

        def capture_execute(query, params):
            captured_params.append(params.copy())
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = MagicMock(total=0)
            return result

        mock_db.execute.side_effect = capture_execute
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            TestClient(app).get("/api/orders")

        # Both SQL calls (rows + count) must use tenant_id = TENANT_A
        assert len(captured_params) >= 1
        for params in captured_params:
            assert params.get("tenant_id") == TENANT_A, (
                f"Expected tenant_id={TENANT_A!r}, got {params.get('tenant_id')!r}"
            )

    def test_tenant_b_gets_separate_scoped_query(self, mock_tenant_context_b):
        """Tenant B's request is scoped to TENANT_B, not TENANT_A."""
        captured_params = []

        mock_db = MagicMock()

        def capture_execute(query, params):
            captured_params.append(params.copy())
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = MagicMock(total=0)
            return result

        mock_db.execute.side_effect = capture_execute
        app = _make_app(mock_tenant_context_b, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_b):
            TestClient(app).get("/api/orders")

        for params in captured_params:
            assert params.get("tenant_id") == TENANT_B
            assert params.get("tenant_id") != TENANT_A


# ---------------------------------------------------------------------------
# Tests: query parameters
# ---------------------------------------------------------------------------


class TestOrdersQueryParams:

    @pytest.mark.parametrize("timeframe", [
        "7days", "30days", "90days", "thisWeek", "thisMonth", "thisQuarter",
    ])
    def test_valid_timeframes_return_200(self, mock_tenant_context_a, timeframe):
        """All documented timeframe values are accepted without error."""
        mock_db = _make_db_mock(rows=[], total=0)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get(f"/api/orders?timeframe={timeframe}")

        assert response.status_code == 200, (
            f"Expected 200 for timeframe={timeframe!r}, got {response.status_code}"
        )

    def test_unknown_timeframe_falls_back_to_30days(self, mock_tenant_context_a):
        """Unknown timeframe values fall back to 30-day window (not 422)."""
        mock_db = _make_db_mock(rows=[], total=0)
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            response = TestClient(app).get("/api/orders?timeframe=invalid_value")

        assert response.status_code == 200

    def test_limit_and_offset_are_forwarded(self, mock_tenant_context_a):
        """limit and offset params are passed to the DB query."""
        captured_params = []

        mock_db = MagicMock()

        def capture_execute(query, params):
            captured_params.append(params.copy())
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = MagicMock(total=0)
            return result

        mock_db.execute.side_effect = capture_execute
        app = _make_app(mock_tenant_context_a, mock_db)

        with patch("src.api.routes.orders.get_tenant_context", return_value=mock_tenant_context_a):
            TestClient(app).get("/api/orders?limit=10&offset=20")

        row_query_params = captured_params[0]
        assert row_query_params.get("limit") == 10
        assert row_query_params.get("offset") == 20
