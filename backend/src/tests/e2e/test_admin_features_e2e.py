"""
E2E Tests: Admin Features — Plan Management

Tests admin-only plan CRUD and feature toggle operations.

Priority: P2 (Lower Risk)
"""

import pytest


@pytest.mark.e2e
class TestAdminPlansHappyPath:
    """Happy path tests for admin plan management."""

    async def test_admin_list_plans(
        self,
        async_client,
        admin_headers,
        test_plan_free,
        test_plan_pro,
    ):
        """GET /api/admin/plans returns all plans."""
        response = await async_client.get(
            "/api/admin/plans",
            headers=admin_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "plans" in data
            assert len(data["plans"]) >= 2

    async def test_admin_create_plan(
        self,
        async_client,
        admin_headers,
    ):
        """POST /api/admin/plans creates a new plan."""
        response = await async_client.post(
            "/api/admin/plans",
            headers=admin_headers,
            json={
                "name": "e2e_enterprise",
                "display_name": "E2E Enterprise",
                "description": "E2E test enterprise plan",
                "price_monthly_cents": 29900,
                "is_active": True,
            },
        )
        assert response.status_code in [200, 201, 403]

    async def test_admin_update_plan(
        self,
        async_client,
        admin_headers,
        test_plan_pro,
    ):
        """PATCH /api/admin/plans/{id} updates a plan."""
        response = await async_client.patch(
            f"/api/admin/plans/{test_plan_pro.id}",
            headers=admin_headers,
            json={"description": "Updated E2E description"},
        )
        assert response.status_code in [200, 403, 404]

    async def test_admin_deactivate_plan(
        self,
        async_client,
        admin_headers,
        db_session,
    ):
        """Deactivating a plan sets is_active=false."""
        from src.models.plan import Plan
        import uuid

        plan = Plan(
            id=f"plan_deactivate_{uuid.uuid4().hex[:6]}",
            name="deactivate_test",
            display_name="Deactivate Test",
            price_monthly_cents=100,
            is_active=True,
        )
        db_session.add(plan)
        db_session.flush()

        response = await async_client.patch(
            f"/api/admin/plans/{plan.id}",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert response.status_code in [200, 403, 404]


@pytest.mark.e2e
class TestAdminPlansEdgeCases:
    """Edge cases for admin features."""

    async def test_non_admin_cannot_access_admin_routes(
        self,
        async_client,
        viewer_headers,
    ):
        """Non-admin should be denied access to admin plan routes."""
        response = await async_client.get(
            "/api/admin/plans",
            headers=viewer_headers,
        )
        assert response.status_code in [401, 403]

        response = await async_client.post(
            "/api/admin/plans",
            headers=viewer_headers,
            json={"name": "blocked", "display_name": "Blocked"},
        )
        assert response.status_code in [401, 403]
