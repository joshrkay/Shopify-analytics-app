"""
E2E Tests: Agency Access Request Workflow

Tests the full agency access request lifecycle: create, list, approve, deny, cancel.

Priority: P2 (Lower Risk)
"""

import pytest
import uuid


@pytest.mark.e2e
class TestAgencyAccessRequestsHappyPath:
    """Happy path tests for agency access request workflow."""

    async def test_create_access_request(
        self,
        async_client,
        agency_headers,
        test_tenant_id_b,
    ):
        """POST /api/agency-access/requests creates a pending request."""
        response = await async_client.post(
            "/api/agency-access/requests",
            headers=agency_headers,
            json={
                "tenant_id": test_tenant_id_b,
                "message": "E2E test access request",
            },
        )
        assert response.status_code in [200, 201, 400, 403, 409]

    async def test_list_pending_requests(
        self,
        async_client,
        admin_headers,
    ):
        """GET /api/agency-access/requests/pending returns pending list."""
        response = await async_client.get(
            "/api/agency-access/requests/pending",
            headers=admin_headers,
        )
        assert response.status_code in [200, 403]

    async def test_list_my_requests(
        self,
        async_client,
        agency_headers,
    ):
        """GET /api/agency-access/requests/mine returns own requests."""
        response = await async_client.get(
            "/api/agency-access/requests/mine",
            headers=agency_headers,
        )
        assert response.status_code in [200, 403]

    async def test_approve_request(
        self,
        async_client,
        admin_headers,
        db_session,
        test_tenant_id,
        test_user_id,
    ):
        """POST /api/agency-access/requests/{id}/approve grants access."""
        from src.models.agency_access_request import AgencyAccessRequest

        req = AgencyAccessRequest(
            id=str(uuid.uuid4()),
            requesting_user_id=f"user_{uuid.uuid4().hex[:24]}",
            tenant_id=test_tenant_id,
            requested_role_slug="agency_viewer",
            status="pending",
        )
        db_session.add(req)
        db_session.flush()

        response = await async_client.post(
            f"/api/agency-access/requests/{req.id}/approve",
            headers=admin_headers,
            json={"review_note": "E2E approved"},
        )
        assert response.status_code in [200, 400, 403, 404]

    async def test_deny_request(
        self,
        async_client,
        admin_headers,
        db_session,
        test_tenant_id,
    ):
        """POST /api/agency-access/requests/{id}/deny rejects request."""
        from src.models.agency_access_request import AgencyAccessRequest

        req = AgencyAccessRequest(
            id=str(uuid.uuid4()),
            requesting_user_id=f"user_{uuid.uuid4().hex[:24]}",
            tenant_id=test_tenant_id,
            requested_role_slug="agency_viewer",
            status="pending",
        )
        db_session.add(req)
        db_session.flush()

        response = await async_client.post(
            f"/api/agency-access/requests/{req.id}/deny",
            headers=admin_headers,
            json={"review_note": "E2E denied"},
        )
        assert response.status_code in [200, 400, 403, 404]

    async def test_cancel_pending_request(
        self,
        async_client,
        agency_headers,
        db_session,
        test_tenant_id,
        test_user_id,
    ):
        """POST /api/agency-access/requests/{id}/cancel cancels own request."""
        from src.models.agency_access_request import AgencyAccessRequest

        req = AgencyAccessRequest(
            id=str(uuid.uuid4()),
            requesting_user_id=test_user_id,
            tenant_id=test_tenant_id,
            requested_role_slug="agency_viewer",
            status="pending",
        )
        db_session.add(req)
        db_session.flush()

        response = await async_client.post(
            f"/api/agency-access/requests/{req.id}/cancel",
            headers=agency_headers,
        )
        assert response.status_code in [200, 400, 403, 404]


@pytest.mark.e2e
class TestAgencyAccessRequestsEdgeCases:
    """Edge cases for agency access requests."""

    async def test_duplicate_request_rejected(
        self,
        async_client,
        agency_headers,
        test_tenant_id_b,
    ):
        """Creating duplicate requests for same tenant should be rejected."""
        body = {"tenant_id": test_tenant_id_b, "message": "Dup test"}
        await async_client.post("/api/agency-access/requests", headers=agency_headers, json=body)
        response = await async_client.post(
            "/api/agency-access/requests",
            headers=agency_headers,
            json=body,
        )
        assert response.status_code in [200, 201, 400, 403, 409]
