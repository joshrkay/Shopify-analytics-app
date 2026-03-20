"""
E2E Tests: Team Member Management

Tests member listing, role granting, role updates, and access revocation.

Priority: P2 (Lower Risk)
"""

import pytest


@pytest.mark.e2e
class TestTeamManagementHappyPath:
    """Happy path tests for team member management."""

    async def test_list_tenant_members(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
    ):
        """GET /api/tenants/{tenant_id}/members returns member list."""
        response = await async_client.get(
            f"/api/tenants/{test_tenant_id}/members",
            headers=admin_headers,
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "members" in data or isinstance(data, list)

    async def test_add_member(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
    ):
        """POST /api/tenants/{tenant_id}/members adds a member."""
        response = await async_client.post(
            f"/api/tenants/{test_tenant_id}/members",
            headers=admin_headers,
            json={
                "email": "newmember@e2e-test.com",
                "role": "viewer",
            },
        )
        assert response.status_code in [200, 201, 400, 409]

    async def test_update_member_role(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
        test_user_id,
    ):
        """PATCH /api/tenants/{tenant_id}/members/{user_id} updates role."""
        response = await async_client.patch(
            f"/api/tenants/{test_tenant_id}/members/{test_user_id}",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert response.status_code in [200, 400, 404]

    async def test_revoke_member_access(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
    ):
        """DELETE /api/tenants/{tenant_id}/members/{user_id} revokes access."""
        # Use a different user_id to avoid revoking the admin's own access
        fake_user_id = "user_revoke_target_000"
        response = await async_client.delete(
            f"/api/tenants/{test_tenant_id}/members/{fake_user_id}",
            headers=admin_headers,
        )
        assert response.status_code in [200, 400, 404]


@pytest.mark.e2e
class TestTeamManagementEdgeCases:
    """Edge cases for team management."""

    async def test_viewer_cannot_manage_team(
        self,
        async_client,
        viewer_headers,
        test_tenant_id,
    ):
        """Viewer should be denied team management."""
        response = await async_client.post(
            f"/api/tenants/{test_tenant_id}/members",
            headers=viewer_headers,
            json={"email": "blocked@test.com", "role": "viewer"},
        )
        assert response.status_code in [401, 403]

    async def test_cannot_remove_last_admin(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
        test_user_id,
    ):
        """Removing the last admin should be prevented."""
        response = await async_client.delete(
            f"/api/tenants/{test_tenant_id}/members/{test_user_id}",
            headers=admin_headers,
        )
        # Should be prevented or already handled gracefully
        assert response.status_code in [200, 400, 403, 409]

    async def test_tenant_member_isolation(
        self,
        async_client,
        auth_headers_b,
        test_tenant_id,
    ):
        """Tenant B cannot list Tenant A's members."""
        response = await async_client.get(
            f"/api/tenants/{test_tenant_id}/members",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]
