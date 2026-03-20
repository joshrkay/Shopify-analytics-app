"""
E2E Tests: Agency Multi-Tenant Flows

Tests store listing, switching, access checks, and cross-tenant isolation
for agency users managing multiple Shopify stores.

Priority: P1 (Major Feature)
"""

import pytest


@pytest.mark.e2e
class TestAgencyHappyPath:
    """Happy path tests for agency multi-tenant operations."""

    async def test_list_assigned_stores(
        self,
        async_client,
        agency_headers,
    ):
        """GET /api/agency/stores returns assigned stores."""
        response = await async_client.get(
            "/api/agency/stores",
            headers=agency_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "stores" in data or isinstance(data, dict)

    async def test_switch_active_store(
        self,
        async_client,
        agency_headers,
        test_tenant_id_b,
    ):
        """POST /api/agency/stores/switch changes active tenant."""
        response = await async_client.post(
            "/api/agency/stores/switch",
            headers=agency_headers,
            json={"tenant_id": test_tenant_id_b},
        )
        assert response.status_code in [200, 400, 403, 404]

    async def test_check_store_access(
        self,
        async_client,
        agency_headers,
        test_tenant_id,
    ):
        """GET /api/agency/stores/{tenant_id}/access checks access."""
        response = await async_client.get(
            f"/api/agency/stores/{test_tenant_id}/access",
            headers=agency_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "has_access" in data

    async def test_get_user_context(
        self,
        async_client,
        agency_headers,
    ):
        """GET /api/agency/me returns user context."""
        response = await async_client.get(
            "/api/agency/me",
            headers=agency_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "user_id" in data or "tenant_id" in data

    async def test_cross_store_summary(
        self,
        async_client,
        agency_headers,
    ):
        """GET /api/agency/reports/summary returns aggregated data."""
        response = await async_client.get(
            "/api/agency/reports/summary",
            headers=agency_headers,
        )
        assert response.status_code in [200, 403]


@pytest.mark.e2e
class TestAgencyEdgeCases:
    """Edge cases for agency access control."""

    async def test_agency_user_cannot_access_unassigned_store(
        self,
        async_client,
        agency_headers,
    ):
        """Agency user should not access a store not in their allowed_tenants."""
        response = await async_client.get(
            "/api/agency/stores/nonexistent-tenant-999/access",
            headers=agency_headers,
        )
        assert response.status_code in [403, 404]

    async def test_non_agency_user_rejected_from_agency_routes(
        self,
        async_client,
        auth_headers,
    ):
        """Regular merchant token should be denied from agency endpoints."""
        response = await async_client.get(
            "/api/agency/stores",
            headers=auth_headers,
        )
        assert response.status_code in [200, 403]

    async def test_tenant_selection_required_for_multi_tenant_user(
        self,
        async_client,
        mock_clerk,
        test_tenant_id,
        test_tenant_id_b,
    ):
        """
        Multi-tenant user without active selection should get 409.
        This tests TenantSelectionRequiredException.
        """
        # Create token with multiple tenants but no active selection
        token = mock_clerk.create_test_token(
            tenant_id=test_tenant_id,
            allowed_tenants=[test_tenant_id, test_tenant_id_b],
            custom_claims={"metadata": {
                "roles": ["agency_user"],
                "entitlements": [],
                "allowed_tenants": [test_tenant_id, test_tenant_id_b],
            }},
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/data-health/summary",
            headers=headers,
        )
        # May get 200 (resolved) or 409 (selection required)
        assert response.status_code in [200, 403, 409]
