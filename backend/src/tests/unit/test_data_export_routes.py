"""
Unit tests for the Data Export API routes.

Tests cover:
- GET /api/exports/datasets — List available datasets
- POST /api/exports/data — Export data as CSV/JSON
- POST /api/exports/sheets — Google Sheets export (stub)
- Entitlement gating (402 for free tier)
- Row limits by billing tier
- Rate limiting (10 per 24h)
- Input validation (unknown dataset, bad format)
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.data_export import (
    router,
    AVAILABLE_DATASETS,
    EXPORT_RATE_LIMIT,
    _export_counts,
    _get_row_limit,
    _check_rate_limit,
)
from src.database.session import get_db_session
from src.services.billing_entitlements import EntitlementCheckResult


# =============================================================================
# Fixtures
# =============================================================================

TENANT_ID = "test-tenant-export"


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limit counters between tests."""
    _export_counts.clear()
    yield
    _export_counts.clear()


@pytest.fixture
def mock_entitled():
    """Returns an entitled check result."""
    return EntitlementCheckResult(is_entitled=True, current_tier="growth")


@pytest.fixture
def mock_not_entitled():
    """Returns a not-entitled check result."""
    return EntitlementCheckResult(
        is_entitled=False, required_tier="growth", current_tier="free"
    )


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    return app


@pytest.fixture
def client(app, mock_entitled):
    with patch("src.api.routes.data_export.get_tenant_context") as mock_gtc, \
         patch("src.middleware.rate_limit.get_tenant_context") as mock_rl_gtc:
        ctx = MagicMock()
        ctx.tenant_id = TENANT_ID
        ctx.user_id = "test-user"
        mock_gtc.return_value = ctx
        mock_rl_gtc.return_value = ctx
        yield TestClient(app)


def _mock_entitlements(entitled=True, tier="growth"):
    """Create a mock BillingEntitlementsService."""
    mock = MagicMock()
    mock.check_feature_entitlement.return_value = EntitlementCheckResult(
        is_entitled=entitled,
        current_tier=tier,
        required_tier="growth" if not entitled else None,
    )
    mock.get_billing_tier.return_value = tier
    return mock


# =============================================================================
# GET /api/exports/datasets
# =============================================================================

class TestListDatasets:

    def test_returns_all_datasets(self, client):
        """Returns all available export datasets."""
        response = client.get("/api/exports/datasets")

        assert response.status_code == 200
        data = response.json()
        assert len(data["datasets"]) == len(AVAILABLE_DATASETS)

    def test_dataset_fields(self, client):
        """Each dataset has required fields."""
        response = client.get("/api/exports/datasets")

        data = response.json()
        for ds in data["datasets"]:
            assert "id" in ds
            assert "name" in ds
            assert "description" in ds
            assert "columns" in ds
            assert isinstance(ds["columns"], list)
            assert len(ds["columns"]) > 0

    def test_known_datasets_present(self, client):
        """Orders, marketing_metrics, marketing_spend, attribution are present."""
        response = client.get("/api/exports/datasets")

        ids = {ds["id"] for ds in response.json()["datasets"]}
        assert "orders" in ids
        assert "marketing_metrics" in ids
        assert "marketing_spend" in ids
        assert "attribution" in ids


# =============================================================================
# POST /api/exports/data — entitlement checks
# =============================================================================

class TestExportDataEntitlements:

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_free_tier_gets_402(self, MockBES, client):
        """Free tier without DATA_EXPORT entitlement gets 402."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.post(
            "/api/exports/data",
            json={"dataset": "orders", "format": "csv"},
        )

        assert response.status_code == 402
        assert "growth" in response.json()["detail"].lower()

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_growth_tier_allowed(self, MockBES, client):
        """Growth tier with DATA_EXPORT entitlement succeeds (mocked DB)."""
        mock_service = _mock_entitlements(entitled=True, tier="growth")
        MockBES.return_value = mock_service

        # Mock the db_session.execute to return empty results
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = ["order_id", "order_name"]

        with patch("src.api.routes.data_export.get_db_session") as mock_db:
            mock_session = MagicMock()
            mock_session.execute.return_value = mock_result

            # Override the dependency
            from src.database.session import get_db_session as real_dep
            client.app.dependency_overrides[real_dep] = lambda: mock_session

            response = client.post(
                "/api/exports/data",
                json={"dataset": "orders", "format": "json"},
            )

        # Should succeed (200) or return export response
        assert response.status_code == 200


# =============================================================================
# POST /api/exports/data — validation
# =============================================================================

class TestExportDataValidation:

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_unknown_dataset_returns_400(self, MockBES, client):
        """Unknown dataset returns 400."""
        MockBES.return_value = _mock_entitlements(entitled=True)

        response = client.post(
            "/api/exports/data",
            json={"dataset": "nonexistent", "format": "csv"},
        )

        assert response.status_code == 400
        assert "Unknown dataset" in response.json()["detail"]

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_invalid_format_returns_400(self, MockBES, client):
        """Invalid format returns 400."""
        MockBES.return_value = _mock_entitlements(entitled=True)

        response = client.post(
            "/api/exports/data",
            json={"dataset": "orders", "format": "xml"},
        )

        assert response.status_code == 400
        assert "Format must be" in response.json()["detail"]


# =============================================================================
# Rate limiting
# =============================================================================

class TestExportRateLimiting:

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_rate_limit_exceeded_returns_429(self, MockBES, client):
        """11th export in 24h returns 429."""
        MockBES.return_value = _mock_entitlements(entitled=True)

        # Exhaust the rate limit
        from datetime import datetime, timezone
        _export_counts[TENANT_ID] = [
            datetime.now(timezone.utc) for _ in range(EXPORT_RATE_LIMIT)
        ]

        response = client.post(
            "/api/exports/data",
            json={"dataset": "orders", "format": "csv"},
        )

        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()


# =============================================================================
# Row limits
# =============================================================================

class TestRowLimits:

    def test_free_tier_limit(self):
        assert _get_row_limit("free", None) == 100

    def test_growth_tier_limit(self):
        assert _get_row_limit("growth", None) == 10_000

    def test_pro_tier_limit(self):
        assert _get_row_limit("pro", None) == 100_000

    def test_enterprise_tier_limit(self):
        assert _get_row_limit("enterprise", None) == 1_000_000

    def test_requested_limit_capped_by_tier(self):
        """Requested limit is capped by tier max."""
        assert _get_row_limit("growth", 50_000) == 10_000

    def test_requested_limit_under_tier_max(self):
        """Requested limit below tier max is honored."""
        assert _get_row_limit("growth", 500) == 500

    def test_unknown_tier_defaults_to_100(self):
        assert _get_row_limit("unknown_tier", None) == 100


# =============================================================================
# Rate limit helper
# =============================================================================

class TestCheckRateLimit:

    def test_first_export_allowed(self):
        assert _check_rate_limit("new-tenant") is True

    def test_within_limit_allowed(self):
        from datetime import datetime, timezone
        _export_counts["tenant-a"] = [
            datetime.now(timezone.utc) for _ in range(9)
        ]
        assert _check_rate_limit("tenant-a") is True

    def test_at_limit_blocked(self):
        from datetime import datetime, timezone
        _export_counts["tenant-b"] = [
            datetime.now(timezone.utc) for _ in range(10)
        ]
        assert _check_rate_limit("tenant-b") is False

    def test_old_entries_expire(self):
        from datetime import datetime, timezone, timedelta
        # All entries are 25h old — should be pruned
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        _export_counts["tenant-c"] = [old_time for _ in range(10)]
        assert _check_rate_limit("tenant-c") is True


# =============================================================================
# POST /api/exports/sheets — stub
# =============================================================================

class TestSheetsExport:

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_sheets_returns_coming_soon(self, MockBES, client):
        """Sheets export stub returns coming soon message."""
        MockBES.return_value = _mock_entitlements(entitled=True)

        response = client.post(
            "/api/exports/sheets",
            json={"dataset": "orders"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "coming soon" in data["error"].lower()

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_sheets_requires_entitlement(self, MockBES, client):
        """Sheets export requires SHEETS_EXPORT entitlement."""
        MockBES.return_value = _mock_entitlements(entitled=False, tier="free")

        response = client.post(
            "/api/exports/sheets",
            json={"dataset": "orders"},
        )

        assert response.status_code == 402

    @patch("src.api.routes.data_export.BillingEntitlementsService")
    def test_sheets_unknown_dataset_returns_400(self, MockBES, client):
        """Unknown dataset returns 400."""
        MockBES.return_value = _mock_entitlements(entitled=True)

        response = client.post(
            "/api/exports/sheets",
            json={"dataset": "nonexistent"},
        )

        assert response.status_code == 400
