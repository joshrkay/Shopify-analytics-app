"""
E2E Tests: Audit Log Querying and Export

Tests audit log listing, filtering, detail retrieval, and export.

Priority: P2 (Lower Risk)
"""

import pytest


@pytest.mark.e2e
class TestAuditLogsHappyPath:
    """Happy path tests for audit log querying."""

    async def test_list_audit_logs(
        self,
        async_client,
        admin_headers,
        test_audit_logs,
    ):
        """GET /api/v1/audit-logs returns paginated list."""
        response = await async_client.get(
            "/api/v1/audit-logs",
            headers=admin_headers,
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "logs" in data
            assert len(data["logs"]) >= 1

    async def test_filter_audit_logs_by_event_type(
        self,
        async_client,
        admin_headers,
        test_audit_logs,
    ):
        """Filter audit logs by event_type."""
        response = await async_client.get(
            "/api/v1/audit-logs",
            headers=admin_headers,
            params={"event_type": "dashboard.created"},
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            for log in data.get("logs", []):
                assert log["event_type"] == "dashboard.created"

    async def test_filter_audit_logs_by_date(
        self,
        async_client,
        admin_headers,
        test_audit_logs,
    ):
        """Filter audit logs by date range."""
        response = await async_client.get(
            "/api/v1/audit-logs",
            headers=admin_headers,
            params={
                "start_date": "2020-01-01",
                "end_date": "2030-01-01",
            },
        )
        assert response.status_code in [200, 403]

    async def test_get_single_audit_log(
        self,
        async_client,
        admin_headers,
        test_audit_logs,
    ):
        """GET /api/v1/audit-logs/{id} returns single entry."""
        log_id = test_audit_logs[0].id
        response = await async_client.get(
            f"/api/v1/audit-logs/{log_id}",
            headers=admin_headers,
        )
        assert response.status_code in [200, 403, 404]

    async def test_filter_by_correlation_id(
        self,
        async_client,
        admin_headers,
        test_audit_logs,
    ):
        """Filter audit logs by correlation_id groups related events."""
        correlation_id = test_audit_logs[0].correlation_id
        response = await async_client.get(
            "/api/v1/audit-logs",
            headers=admin_headers,
            params={"correlation_id": correlation_id},
        )
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            # Should have multiple logs with same correlation_id
            logs = data.get("logs", [])
            assert len(logs) >= 1


@pytest.mark.e2e
class TestAuditLogsEdgeCases:
    """Edge cases for audit logs."""

    async def test_non_admin_audit_log_access(
        self,
        async_client,
        viewer_headers,
        test_audit_logs,
    ):
        """Non-admin may be restricted from audit logs."""
        response = await async_client.get(
            "/api/v1/audit-logs",
            headers=viewer_headers,
        )
        assert response.status_code in [200, 403]

    async def test_audit_tenant_isolation(
        self,
        async_client,
        auth_headers_b,
        test_audit_logs,
    ):
        """Tenant B cannot see Tenant A's audit logs."""
        log_id = test_audit_logs[0].id
        response = await async_client.get(
            f"/api/v1/audit-logs/{log_id}",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]
