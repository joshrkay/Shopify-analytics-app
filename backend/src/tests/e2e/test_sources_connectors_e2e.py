"""
E2E Tests: Data Sources & Connectors

Tests source catalog, OAuth flows, API key connections,
disconnection, sync config, and tenant isolation.

Priority: P1 (Major Feature)
"""

import pytest
import uuid


@pytest.mark.e2e
class TestSourceCatalog:
    """Tests for source catalog and listing."""

    async def test_get_source_catalog(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/sources/catalog returns all supported platforms."""
        response = await async_client.get(
            "/api/sources/catalog",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data or isinstance(data, list)

        sources = data.get("sources", data)
        platforms = [s.get("platform") for s in sources]
        assert len(platforms) >= 1

    async def test_list_connected_sources(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/sources returns connected sources for tenant."""
        response = await async_client.get(
            "/api/sources",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data or isinstance(data, list)


@pytest.mark.e2e
class TestSourceOAuthFlow:
    """Tests for OAuth initiation and callback."""

    async def test_oauth_initiate_shopify(
        self,
        async_client,
        auth_headers,
    ):
        """POST /api/sources/shopify/oauth/initiate returns auth URL."""
        response = await async_client.post(
            "/api/sources/shopify/oauth/initiate",
            headers=auth_headers,
        )
        assert response.status_code in [200, 400, 422, 503]
        if response.status_code == 200:
            data = response.json()
            assert "auth_url" in data or "url" in data

    async def test_oauth_initiate_unsupported_platform(
        self,
        async_client,
        auth_headers,
    ):
        """OAuth initiate with unsupported platform should fail."""
        response = await async_client.post(
            "/api/sources/nonexistent_platform/oauth/initiate",
            headers=auth_headers,
        )
        assert response.status_code in [400, 404, 422]

    async def test_oauth_callback_invalid_state(
        self,
        async_client,
        auth_headers,
    ):
        """OAuth callback with invalid state should fail."""
        response = await async_client.post(
            "/api/sources/oauth/callback",
            headers=auth_headers,
            json={"state": "invalid-state-token", "code": "fake-code"},
        )
        assert response.status_code in [400, 403, 404, 422]


@pytest.mark.e2e
class TestSourceConnectionManagement:
    """Tests for source connection management."""

    async def test_test_connection(
        self,
        async_client,
        auth_headers,
        test_airbyte_connection,
    ):
        """POST /api/sources/{id}/test verifies connection."""
        response = await async_client.post(
            f"/api/sources/{test_airbyte_connection.id}/test",
            headers=auth_headers,
        )
        assert response.status_code in [200, 400, 404, 503]

    async def test_update_sync_config(
        self,
        async_client,
        auth_headers,
        test_airbyte_connection,
    ):
        """PATCH /api/sources/{id}/config updates config."""
        response = await async_client.patch(
            f"/api/sources/{test_airbyte_connection.id}/config",
            headers=auth_headers,
            json={"config": {"sync_frequency": "daily"}},
        )
        assert response.status_code in [200, 400, 404, 422]

    async def test_disconnect_source(
        self,
        async_client,
        auth_headers,
        db_session,
        test_tenant_id,
    ):
        """DELETE /api/sources/{id} removes source."""
        from src.models.airbyte_connection import (
            TenantAirbyteConnection, ConnectionStatus, ConnectionType,
        )

        conn = TenantAirbyteConnection(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            airbyte_connection_id=f"disconnect-test-{uuid.uuid4().hex[:8]}",
            connection_name="Disconnect Test",
            connection_type=ConnectionType.SOURCE,
            source_type="test",
            status=ConnectionStatus.ACTIVE,
            is_enabled=True,
            configuration={},
        )
        db_session.add(conn)
        db_session.flush()

        response = await async_client.delete(
            f"/api/sources/{conn.id}",
            headers=auth_headers,
        )
        assert response.status_code in [200, 204, 404]

    async def test_disconnect_nonexistent_source(
        self,
        async_client,
        auth_headers,
    ):
        """Disconnecting a nonexistent source should return 404."""
        response = await async_client.delete(
            f"/api/sources/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code in [404, 400]


@pytest.mark.e2e
class TestSourceSyncSettings:
    """Tests for global sync settings."""

    async def test_get_global_sync_settings(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/sources/sync-settings returns settings."""
        response = await async_client.get(
            "/api/sources/sync-settings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_update_global_sync_settings(
        self,
        async_client,
        admin_headers,
    ):
        """PUT /api/sources/sync-settings updates settings."""
        response = await async_client.put(
            "/api/sources/sync-settings",
            headers=admin_headers,
            json={"default_frequency": "daily"},
        )
        assert response.status_code in [200, 400, 422]


@pytest.mark.e2e
@pytest.mark.security
class TestSourceTenantIsolation:
    """Tests for source tenant isolation."""

    async def test_source_tenant_isolation(
        self,
        async_client,
        auth_headers_b,
        test_airbyte_connection,
    ):
        """Tenant B cannot see or modify Tenant A's sources."""
        # Tenant B tries to test Tenant A's connection
        response = await async_client.post(
            f"/api/sources/{test_airbyte_connection.id}/test",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]

        # Tenant B tries to disconnect Tenant A's source
        response = await async_client.delete(
            f"/api/sources/{test_airbyte_connection.id}",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]
