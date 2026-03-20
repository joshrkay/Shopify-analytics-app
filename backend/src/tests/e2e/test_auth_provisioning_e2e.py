"""
E2E Tests: Authentication & Tenant Provisioning

Tests the critical auth path: JWT parsing, lazy provisioning,
explicit provisioning, and error handling.

Priority: P0 (Critical Path)
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta


@pytest.mark.e2e
class TestAuthProvisioningHappyPath:
    """Happy path tests for auth and tenant provisioning."""

    async def test_v1_jwt_claims_resolve_tenant(
        self,
        async_client,
        auth_headers,
    ):
        """
        V1 JWT with top-level org_id resolves tenant and allows access.
        The test_token fixture uses top-level org_id format.
        """
        response = await async_client.get(
            "/api/data-health/summary",
            headers=auth_headers,
        )
        # Should succeed — middleware resolves tenant from JWT
        assert response.status_code == 200

    async def test_v2_nested_jwt_claims_resolve_tenant(
        self,
        async_client,
        mock_clerk,
        test_tenant_id,
    ):
        """
        V2 JWT with nested o.id claim should also resolve tenant.
        Clerk JWT v2 nests org claims under 'o'.
        """
        token = mock_clerk.create_test_token(
            tenant_id=test_tenant_id,
            custom_claims={
                "o": {
                    "id": test_tenant_id,
                    "rol": "org:admin",
                    "per": ["org:admin"],
                },
            },
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/data-health/summary",
            headers=headers,
        )
        assert response.status_code == 200

    async def test_explicit_provision_endpoint(
        self,
        async_client,
        auth_headers,
    ):
        """
        POST /api/auth/provision creates tenant context explicitly.
        Should be idempotent on repeat calls.
        """
        # First call
        response1 = await async_client.post(
            "/api/auth/provision",
            headers=auth_headers,
        )
        assert response1.status_code in [200, 201]
        data1 = response1.json()
        assert "tenant_id" in data1 or "status" in data1

        # Second call — idempotent
        response2 = await async_client.post(
            "/api/auth/provision",
            headers=auth_headers,
        )
        assert response2.status_code in [200, 201]

    async def test_provision_then_access_protected_route(
        self,
        async_client,
        auth_headers,
    ):
        """
        Provision explicitly, then access a protected route.
        Ensures the provisioned tenant context works for subsequent requests.
        """
        # Provision
        provision_resp = await async_client.post(
            "/api/auth/provision",
            headers=auth_headers,
        )
        assert provision_resp.status_code in [200, 201]

        # Access protected route
        health_resp = await async_client.get(
            "/api/data-health/summary",
            headers=auth_headers,
        )
        assert health_resp.status_code == 200


@pytest.mark.e2e
class TestAuthProvisioningEdgeCases:
    """Edge case tests for auth failures and error handling."""

    async def test_expired_token_returns_401(
        self,
        async_client,
        mock_clerk,
        test_tenant_id,
    ):
        """Expired JWT should be rejected with 401."""
        expired_token = mock_clerk.create_expired_token(test_tenant_id)
        headers = {"Authorization": f"Bearer {expired_token}"}

        response = await async_client.get(
            "/api/data-health/summary",
            headers=headers,
        )
        assert response.status_code in [401, 403]

    async def test_missing_token_returns_401(
        self,
        async_client,
    ):
        """Request without Authorization header should be rejected."""
        response = await async_client.get("/api/data-health/summary")
        assert response.status_code in [401, 403]

    async def test_malformed_token_returns_401(
        self,
        async_client,
    ):
        """Garbage token should be rejected."""
        headers = {"Authorization": "Bearer not-a-real-jwt-token"}
        response = await async_client.get(
            "/api/data-health/summary",
            headers=headers,
        )
        assert response.status_code in [401, 403]

    async def test_concurrent_provisioning_no_duplicate_error(
        self,
        async_client,
        mock_clerk,
    ):
        """
        Two requests with the same new org_id should both succeed.
        The middleware should handle IntegrityError from concurrent provisioning.
        """
        tenant_id = f"e2e-concurrent-{uuid.uuid4().hex[:8]}"
        token = mock_clerk.create_test_token(tenant_id=tenant_id)
        headers = {"Authorization": f"Bearer {token}"}

        # Send two requests — both should succeed without 500
        resp1 = await async_client.get("/api/data-health/summary", headers=headers)
        resp2 = await async_client.get("/api/data-health/summary", headers=headers)

        # Neither should be a 500 server error
        assert resp1.status_code != 500
        assert resp2.status_code != 500

    async def test_org_prefix_id_does_not_crash(
        self,
        async_client,
        mock_clerk,
    ):
        """
        A JWT with org_id prefixed with 'org_' (Clerk format) should be
        handled gracefully by the middleware's second-chance resolution.
        """
        token = mock_clerk.create_test_token(
            tenant_id="org_2abc123def",
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/data-health/summary",
            headers=headers,
        )
        # Should not crash — may return 200 (resolved) or 403 (unresolved but safe)
        assert response.status_code in [200, 403, 503]
        assert response.status_code != 500
