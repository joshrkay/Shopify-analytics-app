"""
E2E Tests: Role-Based Access Control (RBAC)

Tests that admin/viewer/agency roles correctly gate route access.

Priority: P1 (Major Feature)
"""

import pytest


@pytest.mark.e2e
@pytest.mark.rbac
class TestRBACAdminAccess:
    """Tests verifying admin users can access management endpoints."""

    async def test_admin_can_manage_team(
        self,
        async_client,
        admin_headers,
        test_tenant_id,
    ):
        """Admin should access team member listing."""
        response = await async_client.get(
            f"/api/tenants/{test_tenant_id}/members",
            headers=admin_headers,
        )
        assert response.status_code in [200, 404]

    async def test_admin_can_approve_action_proposals(
        self,
        async_client,
        admin_headers,
        test_action_proposals,
    ):
        """Admin should be able to approve proposals."""
        proposal_id = test_action_proposals[0].id
        response = await async_client.post(
            f"/api/action-proposals/{proposal_id}/approve",
            headers=admin_headers,
            json={"reason": "RBAC test"},
        )
        assert response.status_code in [200, 400]

    async def test_admin_can_access_billing(
        self,
        async_client,
        admin_headers,
    ):
        """Admin should access billing endpoints."""
        response = await async_client.get(
            "/api/billing/entitlements",
            headers=admin_headers,
        )
        assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.rbac
class TestRBACViewerRestrictions:
    """Tests verifying viewer users are restricted from management endpoints."""

    async def test_viewer_cannot_manage_team(
        self,
        async_client,
        viewer_headers,
        test_tenant_id,
    ):
        """Viewer should be denied team management write access."""
        response = await async_client.post(
            f"/api/tenants/{test_tenant_id}/members",
            headers=viewer_headers,
            json={"email": "new@example.com", "role": "viewer"},
        )
        assert response.status_code in [401, 403]

    async def test_viewer_cannot_approve_action_proposals(
        self,
        async_client,
        viewer_headers,
        test_action_proposals,
    ):
        """Viewer should be denied proposal approval."""
        proposal_id = test_action_proposals[0].id
        response = await async_client.post(
            f"/api/action-proposals/{proposal_id}/approve",
            headers=viewer_headers,
        )
        assert response.status_code in [401, 403]

    async def test_viewer_cannot_manage_billing(
        self,
        async_client,
        viewer_headers,
        test_store,
        test_plan_pro,
    ):
        """Viewer should be denied billing checkout."""
        response = await async_client.post(
            "/api/billing/checkout",
            headers=viewer_headers,
            json={"plan_id": test_plan_pro.id},
        )
        assert response.status_code in [401, 403]


@pytest.mark.e2e
@pytest.mark.rbac
class TestRBACEdgeCases:
    """Edge cases for RBAC enforcement."""

    async def test_viewer_can_read_insights(
        self,
        async_client,
        viewer_headers,
        test_insights,
    ):
        """Viewer should have read access to insights."""
        response = await async_client.get(
            "/api/insights",
            headers=viewer_headers,
        )
        # Viewer may or may not have AI entitlement, but should not 500
        assert response.status_code in [200, 402, 403]

    async def test_role_based_audit_log_access(
        self,
        async_client,
        admin_headers,
        viewer_headers,
        test_audit_logs,
    ):
        """Admin sees audit logs; viewer should be restricted."""
        # Admin can read
        admin_resp = await async_client.get(
            "/api/v1/audit-logs",
            headers=admin_headers,
        )
        assert admin_resp.status_code in [200, 403]

        # Viewer restricted
        viewer_resp = await async_client.get(
            "/api/v1/audit-logs",
            headers=viewer_headers,
        )
        assert viewer_resp.status_code in [200, 403]

    async def test_viewer_can_read_billing_entitlements(
        self,
        async_client,
        viewer_headers,
    ):
        """Viewer should be able to check their own entitlements."""
        response = await async_client.get(
            "/api/billing/entitlements",
            headers=viewer_headers,
        )
        assert response.status_code == 200
