"""
Unit tests for the unified Sources API.

Tests cover:
- normalize_connection_to_source maps Shopify connections correctly
- normalize_connection_to_source maps ad platform connections correctly
- normalize_connection_to_source handles edge cases (unknown, None)
- GET /api/sources returns mixed Shopify + ad sources
- GET /api/sources excludes deleted connections
- GET /api/sources returns empty list for tenant with no connections

Story 2.1.1 — Unified Source domain model
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.sources import router
from src.api.schemas.sources import normalize_connection_to_source
from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.airbyte_service import ConnectionInfo, ConnectionListResult


# =============================================================================
# Helpers
# =============================================================================

def make_connection_info(
    id: str = "conn-001",
    source_type: str = "shopify",
    connection_name: str = "My Store",
    status: str = "active",
    is_enabled: bool = True,
    last_sync_at: datetime = None,
    last_sync_status: str = None,
) -> ConnectionInfo:
    """Create a ConnectionInfo fixture."""
    return ConnectionInfo(
        id=id,
        airbyte_connection_id=f"ab-{id}",
        connection_name=connection_name,
        connection_type="source",
        source_type=source_type,
        status=status,
        is_enabled=is_enabled,
        is_active=is_enabled and status == "active",
        can_sync=is_enabled and status in ("active", "pending"),
        last_sync_at=last_sync_at,
        last_sync_status=last_sync_status,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# =============================================================================
# Normalizer Unit Tests
# =============================================================================

class TestNormalizeConnectionToSource:
    """Unit tests for normalize_connection_to_source."""

    def test_shopify_connection(self):
        """Shopify source_type maps to platform='shopify', auth_type='oauth'."""
        conn = make_connection_info(
            source_type="shopify",
            connection_name="My Shopify Store",
        )
        result = normalize_connection_to_source(conn)

        assert result.id == "conn-001"
        assert result.platform == "shopify"
        assert result.display_name == "My Shopify Store"
        assert result.auth_type == "oauth"
        assert result.status == "active"
        assert result.is_enabled is True

    def test_meta_ads_connection(self):
        """Meta Ads source_type maps to platform='meta_ads', auth_type='oauth'."""
        conn = make_connection_info(
            source_type="source-facebook-marketing",
            connection_name="Summer Campaign",
        )
        result = normalize_connection_to_source(conn)

        assert result.platform == "meta_ads"
        assert result.display_name == "Summer Campaign"
        assert result.auth_type == "oauth"

    def test_google_ads_connection(self):
        """Google Ads source_type maps to platform='google_ads', auth_type='oauth'."""
        conn = make_connection_info(
            source_type="source-google-ads",
            connection_name="Google Ads Account",
        )
        result = normalize_connection_to_source(conn)

        assert result.platform == "google_ads"
        assert result.auth_type == "oauth"

    def test_klaviyo_connection(self):
        """Klaviyo source_type maps to platform='klaviyo', auth_type='api_key'."""
        conn = make_connection_info(
            source_type="source-klaviyo",
            connection_name="Klaviyo Newsletter",
        )
        result = normalize_connection_to_source(conn)

        assert result.platform == "klaviyo"
        assert result.auth_type == "api_key"

    def test_tiktok_ads_connection(self):
        """TikTok Ads source_type maps correctly."""
        conn = make_connection_info(source_type="source-tiktok-marketing")
        result = normalize_connection_to_source(conn)

        assert result.platform == "tiktok_ads"
        assert result.auth_type == "oauth"

    def test_snapchat_ads_connection(self):
        """Snapchat Ads source_type maps correctly."""
        conn = make_connection_info(source_type="source-snapchat-marketing")
        result = normalize_connection_to_source(conn)

        assert result.platform == "snapchat_ads"
        assert result.auth_type == "oauth"

    def test_attentive_connection(self):
        """Attentive source_type maps to api_key auth."""
        conn = make_connection_info(source_type="source-attentive")
        result = normalize_connection_to_source(conn)

        assert result.platform == "attentive"
        assert result.auth_type == "api_key"

    def test_postscript_connection(self):
        """Postscript source_type maps to api_key auth."""
        conn = make_connection_info(source_type="source-postscript")
        result = normalize_connection_to_source(conn)

        assert result.platform == "postscript"
        assert result.auth_type == "api_key"

    def test_smsbump_connection(self):
        """SMSBump source_type maps to api_key auth."""
        conn = make_connection_info(source_type="source-smsbump")
        result = normalize_connection_to_source(conn)

        assert result.platform == "smsbump"
        assert result.auth_type == "api_key"

    def test_unknown_source_type_falls_back(self):
        """Unknown source_type uses raw value as platform, defaults auth to api_key."""
        conn = make_connection_info(source_type="source-custom-thing")
        result = normalize_connection_to_source(conn)

        assert result.platform == "source-custom-thing"
        assert result.auth_type == "api_key"

    def test_none_source_type(self):
        """None source_type maps to 'unknown' platform."""
        conn = make_connection_info(source_type=None)
        result = normalize_connection_to_source(conn)

        assert result.platform == "unknown"
        assert result.auth_type == "api_key"

    def test_last_sync_at_none(self):
        """None last_sync_at passes through as None."""
        conn = make_connection_info(last_sync_at=None)
        result = normalize_connection_to_source(conn)

        assert result.last_sync_at is None

    def test_last_sync_at_serialized_to_iso(self):
        """Datetime last_sync_at is serialized to ISO 8601."""
        dt = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        conn = make_connection_info(last_sync_at=dt)
        result = normalize_connection_to_source(conn)

        assert result.last_sync_at == "2025-06-15T10:30:00+00:00"

    def test_last_sync_status_passes_through(self):
        """last_sync_status value passes through."""
        conn = make_connection_info(last_sync_status="succeeded")
        result = normalize_connection_to_source(conn)

        assert result.last_sync_status == "succeeded"

    def test_disabled_connection(self):
        """is_enabled=False passes through correctly."""
        conn = make_connection_info(is_enabled=False)
        result = normalize_connection_to_source(conn)

        assert result.is_enabled is False

    def test_failed_status(self):
        """Failed status passes through."""
        conn = make_connection_info(status="failed")
        result = normalize_connection_to_source(conn)

        assert result.status == "failed"

    def test_source_shopify_variant(self):
        """'source-shopify' also maps to platform='shopify'."""
        conn = make_connection_info(source_type="source-shopify")
        result = normalize_connection_to_source(conn)

        assert result.platform == "shopify"
        assert result.auth_type == "oauth"


# =============================================================================
# Route Integration Tests
# =============================================================================

@pytest.fixture
def tenant_id():
    return "test-tenant-sources-001"


@pytest.fixture
def mock_tenant_context(tenant_id):
    context = MagicMock()
    context.tenant_id = tenant_id
    context.user_id = "user-001"
    return context


def create_test_app(mock_airbyte_service, mock_tenant_context):
    """Create a FastAPI test app with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)

    mock_db = MagicMock()

    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_tenant_context] = lambda: mock_tenant_context

    return app, mock_airbyte_service


class TestListSourcesEndpoint:
    """Integration tests for GET /api/sources."""

    def test_returns_mixed_shopify_and_ad_sources(self, tenant_id, mock_tenant_context):
        """Returns unified list of both Shopify and ad platform connections."""
        shopify_conn = make_connection_info(
            id="conn-shopify-1",
            source_type="shopify",
            connection_name="Main Store",
        )
        meta_conn = make_connection_info(
            id="conn-meta-1",
            source_type="source-facebook-marketing",
            connection_name="Summer Ads",
        )
        mock_result = ConnectionListResult(
            connections=[shopify_conn, meta_conn],
            total_count=2,
            has_more=False,
        )

        with patch("src.api.routes.sources.AirbyteService") as MockService, \
             patch("src.api.routes.sources.get_tenant_context", return_value=mock_tenant_context):
            instance = MockService.return_value
            instance.list_connections.return_value = mock_result

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_db_session] = lambda: MagicMock()

            client = TestClient(app)
            response = client.get("/api/sources")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["sources"]) == 2

        platforms = [s["platform"] for s in data["sources"]]
        assert "shopify" in platforms
        assert "meta_ads" in platforms

        shopify_source = next(s for s in data["sources"] if s["platform"] == "shopify")
        assert shopify_source["display_name"] == "Main Store"
        assert shopify_source["auth_type"] == "oauth"

        meta_source = next(s for s in data["sources"] if s["platform"] == "meta_ads")
        assert meta_source["display_name"] == "Summer Ads"
        assert meta_source["auth_type"] == "oauth"

    def test_excludes_deleted_connections(self, tenant_id, mock_tenant_context):
        """Deleted connections are filtered from the response."""
        active_conn = make_connection_info(
            id="conn-active",
            status="active",
        )
        deleted_conn = make_connection_info(
            id="conn-deleted",
            status="deleted",
        )
        mock_result = ConnectionListResult(
            connections=[active_conn, deleted_conn],
            total_count=2,
            has_more=False,
        )

        with patch("src.api.routes.sources.AirbyteService") as MockService, \
             patch("src.api.routes.sources.get_tenant_context", return_value=mock_tenant_context):
            instance = MockService.return_value
            instance.list_connections.return_value = mock_result

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_db_session] = lambda: MagicMock()

            client = TestClient(app)
            response = client.get("/api/sources")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["sources"][0]["id"] == "conn-active"

    def test_empty_list_for_no_connections(self, tenant_id, mock_tenant_context):
        """Returns empty list when tenant has no connections."""
        mock_result = ConnectionListResult(
            connections=[],
            total_count=0,
            has_more=False,
        )

        with patch("src.api.routes.sources.AirbyteService") as MockService, \
             patch("src.api.routes.sources.get_tenant_context", return_value=mock_tenant_context):
            instance = MockService.return_value
            instance.list_connections.return_value = mock_result

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_db_session] = lambda: MagicMock()

            client = TestClient(app)
            response = client.get("/api/sources")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["sources"] == []

    def test_includes_api_key_auth_types(self, tenant_id, mock_tenant_context):
        """Sources with api_key auth type are correctly identified."""
        klaviyo_conn = make_connection_info(
            id="conn-klaviyo-1",
            source_type="source-klaviyo",
            connection_name="Klaviyo Account",
        )
        mock_result = ConnectionListResult(
            connections=[klaviyo_conn],
            total_count=1,
            has_more=False,
        )

        with patch("src.api.routes.sources.AirbyteService") as MockService, \
             patch("src.api.routes.sources.get_tenant_context", return_value=mock_tenant_context):
            instance = MockService.return_value
            instance.list_connections.return_value = mock_result

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_db_session] = lambda: MagicMock()

            client = TestClient(app)
            response = client.get("/api/sources")

        assert response.status_code == 200
        data = response.json()
        source = data["sources"][0]
        assert source["platform"] == "klaviyo"
        assert source["auth_type"] == "api_key"
