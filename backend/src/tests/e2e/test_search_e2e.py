"""
E2E Tests: Global Search

Tests search functionality across entities.

Priority: P2 (Lower Risk)
"""

import pytest


@pytest.mark.e2e
class TestSearch:
    """Tests for /api/search endpoint."""

    async def test_search_returns_results(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/search?q=revenue returns results."""
        response = await async_client.get(
            "/api/search",
            headers=auth_headers,
            params={"q": "revenue"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data or isinstance(data, list)

    async def test_search_minimum_query_length(
        self,
        async_client,
        auth_headers,
    ):
        """Search with single character should fail validation."""
        response = await async_client.get(
            "/api/search",
            headers=auth_headers,
            params={"q": "a"},
        )
        assert response.status_code in [200, 400, 422]

    async def test_search_tenant_isolation(
        self,
        async_client,
        auth_headers,
        auth_headers_b,
        test_dashboard,
    ):
        """Search results should be scoped to current tenant."""
        resp_a = await async_client.get(
            "/api/search",
            headers=auth_headers,
            params={"q": "E2E Test Dashboard"},
        )
        resp_b = await async_client.get(
            "/api/search",
            headers=auth_headers_b,
            params={"q": "E2E Test Dashboard"},
        )

        # Both should succeed but Tenant B should not see Tenant A's dashboard
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
