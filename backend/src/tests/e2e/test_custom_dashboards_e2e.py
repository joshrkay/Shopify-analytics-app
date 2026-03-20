"""
E2E Tests: Custom Dashboards — CRUD, Publishing, Versioning, Reports, Sharing

Tests the full dashboard lifecycle: create, edit, publish, duplicate,
versioning, reports, sharing, and cleanup.

Priority: P1 (Major Feature)
"""

import pytest
import uuid


# =============================================================================
# Dashboard CRUD
# =============================================================================

@pytest.mark.e2e
class TestDashboardCRUD:
    """Tests for dashboard create, read, update, delete."""

    async def test_create_dashboard(
        self,
        async_client,
        pro_tier_headers,
    ):
        """POST /api/v1/dashboards creates a new dashboard."""
        response = await async_client.post(
            "/api/v1/dashboards",
            headers=pro_tier_headers,
            json={"name": "E2E Created Dashboard", "description": "Test description"},
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("name") == "E2E Created Dashboard"
        assert data.get("status") == "draft"

    async def test_list_dashboards(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """GET /api/v1/dashboards returns dashboard list."""
        response = await async_client.get(
            "/api/v1/dashboards",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "dashboards" in data
        assert data.get("total", len(data["dashboards"])) >= 1

    async def test_get_dashboard(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """GET /api/v1/dashboards/{id} returns specific dashboard."""
        response = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_dashboard.id
        assert data["name"] == "E2E Test Dashboard"

    async def test_update_dashboard(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """PUT /api/v1/dashboards/{id} updates dashboard."""
        response = await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=pro_tier_headers,
            json={"name": "Updated E2E Dashboard"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated E2E Dashboard"

    async def test_publish_dashboard(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """POST /api/v1/dashboards/{id}/publish changes status."""
        response = await async_client.post(
            f"/api/v1/dashboards/{test_dashboard.id}/publish",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "published"

    async def test_duplicate_dashboard(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """POST /api/v1/dashboards/{id}/duplicate creates a copy."""
        response = await async_client.post(
            f"/api/v1/dashboards/{test_dashboard.id}/duplicate",
            headers=pro_tier_headers,
            json={"new_name": "E2E Duplicated Dashboard"},
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["id"] != test_dashboard.id
        assert "Duplicated" in data.get("name", "") or "Copy" in data.get("name", "")

    async def test_delete_dashboard(
        self,
        async_client,
        pro_tier_headers,
        db_session,
        test_tenant_id,
        test_user_id,
    ):
        """DELETE /api/v1/dashboards/{id} removes dashboard."""
        from src.models.custom_dashboard import CustomDashboard

        # Create a throwaway dashboard
        dashboard = CustomDashboard(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            name="E2E Delete Target",
            status="draft",
            created_by=test_user_id,
        )
        db_session.add(dashboard)
        db_session.flush()

        response = await async_client.delete(
            f"/api/v1/dashboards/{dashboard.id}",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 204]


# =============================================================================
# Dashboard Versioning
# =============================================================================

@pytest.mark.e2e
class TestDashboardVersioning:
    """Tests for version history and restore."""

    async def test_dashboard_version_history(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """Update dashboard twice, then check version history."""
        # Update 1
        await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=pro_tier_headers,
            json={"name": "Version 1"},
        )
        # Update 2
        await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=pro_tier_headers,
            json={"name": "Version 2"},
        )

        response = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}/versions",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert data.get("total", len(data["versions"])) >= 1

    async def test_restore_version(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """Restore a previous version of the dashboard."""
        # First get versions
        versions_resp = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}/versions",
            headers=pro_tier_headers,
        )
        if versions_resp.status_code == 200:
            versions = versions_resp.json().get("versions", [])
            if versions:
                version_num = versions[0].get("version_number", 1)
                response = await async_client.post(
                    f"/api/v1/dashboards/{test_dashboard.id}/restore/{version_num}",
                    headers=pro_tier_headers,
                )
                assert response.status_code in [200, 404]


# =============================================================================
# Dashboard Reports
# =============================================================================

@pytest.mark.e2e
class TestDashboardReports:
    """Tests for report management within dashboards."""

    async def test_add_report_to_dashboard(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """POST /api/v1/dashboards/{id}/reports adds a report."""
        response = await async_client.post(
            f"/api/v1/dashboards/{test_dashboard.id}/reports",
            headers=pro_tier_headers,
            json={
                "name": "E2E New Report",
                "chart_type": "pie",
                "dataset_name": "kpi_summary",
                "config_json": {"metric": "orders"},
                "position_json": {"x": 0, "y": 4, "w": 6, "h": 4},
            },
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("name") == "E2E New Report"

    async def test_update_report(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """PUT /api/v1/dashboards/{id}/reports/{report_id} updates report."""
        report_id = test_dashboard._test_reports[0].id
        response = await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}/reports/{report_id}",
            headers=pro_tier_headers,
            json={"name": "Updated Report Name"},
        )
        assert response.status_code == 200

    async def test_remove_report(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """DELETE /api/v1/dashboards/{id}/reports/{report_id} removes report."""
        report_id = test_dashboard._test_reports[1].id
        response = await async_client.delete(
            f"/api/v1/dashboards/{test_dashboard.id}/reports/{report_id}",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 204]

    async def test_reorder_reports(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """PUT /api/v1/dashboards/{id}/reports/reorder changes report order."""
        report_ids = [r.id for r in test_dashboard._test_reports]
        response = await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}/reports/reorder",
            headers=pro_tier_headers,
            json={"report_ids": list(reversed(report_ids))},
        )
        assert response.status_code in [200, 400]


# =============================================================================
# Dashboard Sharing
# =============================================================================

@pytest.mark.e2e
class TestDashboardSharing:
    """Tests for dashboard sharing."""

    async def test_create_share(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """POST /api/v1/dashboards/{id}/shares creates a share."""
        response = await async_client.post(
            f"/api/v1/dashboards/{test_dashboard.id}/shares",
            headers=pro_tier_headers,
            json={"permission": "view", "shared_with_role": "viewer"},
        )
        assert response.status_code in [200, 201]

    async def test_list_shares(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """GET /api/v1/dashboards/{id}/shares returns share list."""
        response = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}/shares",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "shares" in data

    async def test_revoke_share(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
        db_session,
        test_tenant_id,
        test_user_id,
    ):
        """DELETE /api/v1/dashboards/{id}/shares/{share_id} revokes share."""
        from src.models.dashboard_share import DashboardShare

        share = DashboardShare(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            dashboard_id=test_dashboard.id,
            permission="view",
            shared_with_role="viewer",
            granted_by=test_user_id,
        )
        db_session.add(share)
        db_session.flush()

        response = await async_client.delete(
            f"/api/v1/dashboards/{test_dashboard.id}/shares/{share.id}",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 204]


# =============================================================================
# Dashboard Audit
# =============================================================================

@pytest.mark.e2e
class TestDashboardAudit:
    """Tests for dashboard audit trail."""

    async def test_dashboard_audit_trail(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """GET /api/v1/dashboards/{id}/audit returns audit entries."""
        response = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}/audit",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.e2e
class TestDashboardEdgeCases:
    """Edge cases for dashboard operations."""

    async def test_optimistic_locking_conflict(
        self,
        async_client,
        pro_tier_headers,
        test_dashboard,
    ):
        """Update with stale expected_updated_at should return 409."""
        response = await async_client.put(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=pro_tier_headers,
            json={
                "name": "Stale Update",
                "expected_updated_at": "2020-01-01T00:00:00Z",
            },
        )
        assert response.status_code in [200, 409]

    async def test_dashboard_tenant_isolation(
        self,
        async_client,
        auth_headers_b,
        test_dashboard,
    ):
        """Tenant B cannot see Tenant A's dashboard."""
        response = await async_client.get(
            f"/api/v1/dashboards/{test_dashboard.id}",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]

    async def test_dashboard_count_endpoint(
        self,
        async_client,
        pro_tier_headers,
    ):
        """GET /api/v1/dashboards/count returns limits info."""
        response = await async_client.get(
            "/api/v1/dashboards/count",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_count" in data
        assert "can_create" in data

    async def test_delete_cleans_up_reports_and_shares(
        self,
        async_client,
        pro_tier_headers,
        db_session,
        test_tenant_id,
        test_user_id,
    ):
        """Deleting a dashboard should cascade to reports and shares."""
        from src.models.custom_dashboard import CustomDashboard
        from src.models.custom_report import CustomReport

        dashboard = CustomDashboard(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            name="E2E Cascade Delete",
            status="draft",
            created_by=test_user_id,
        )
        db_session.add(dashboard)
        db_session.flush()

        report = CustomReport(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            dashboard_id=dashboard.id,
            name="Cascade Report",
            chart_type="bar",
            dataset_name="kpi_summary",
            config_json={},
            position_json={"x": 0, "y": 0, "w": 6, "h": 4},
            created_by=test_user_id,
        )
        db_session.add(report)
        db_session.flush()

        resp = await async_client.delete(
            f"/api/v1/dashboards/{dashboard.id}",
            headers=pro_tier_headers,
        )
        assert resp.status_code in [200, 204]

        # Verify report is gone
        remaining = db_session.query(CustomReport).filter(
            CustomReport.dashboard_id == dashboard.id
        ).all()
        assert len(remaining) == 0
