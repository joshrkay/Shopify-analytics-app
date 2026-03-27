"""Integration tests for agency store-switch token issuance."""

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.routes.agency import router as agency_router
from src.constants.permissions import Permission
from src.platform.tenant_context import TenantContext


def _agency_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-a",
        user_id="user-123",
        roles=["agency_admin"],
        org_id="org_123",
        allowed_tenants=["tenant-a", "tenant-b"],
        billing_tier="professional",
        resolved_permissions={
            Permission.AGENCY_STORES_SWITCH.value,
            Permission.MULTI_TENANT_ACCESS.value,
            Permission.AGENCY_STORES_VIEW.value,
        },
    )


def _build_client(db_session, tenant_context: TenantContext) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def attach_db(request: Request, call_next):
        request.state.db = db_session
        return await call_next(request)

    app.include_router(agency_router)

    return TestClient(app)


class TestAgencyStoreSwitchAPI:
    """Coverage for successful and unauthorized store switch paths."""

    def test_switch_store_success_issues_signed_token(self, db_session):
        tenant_context = _agency_context()

        with patch(
            "src.api.routes.agency.AgencyTokenService.issue_switched_token",
            return_value="signed-token-from-issuer",
        ) as issue_token, patch(
            "src.api.routes.agency.get_tenant_context", return_value=tenant_context
        ), patch(
            "src.platform.rbac.get_tenant_context", return_value=tenant_context
        ):
            with _build_client(db_session, tenant_context) as client:
                response = client.post("/api/agency/stores/switch", json={"tenant_id": "tenant-b"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["jwt_token"] == "signed-token-from-issuer"
        assert body["active_tenant_id"] == "tenant-b"

        issued_claims = issue_token.call_args[0][0]
        assert issued_claims.tenant_id == "tenant-b"
        assert issued_claims.allowed_tenants == ["tenant-a", "tenant-b"]
        assert issued_claims.roles == ["agency_admin"]

    def test_switch_store_unauthorized_target_returns_403(self, db_session):
        tenant_context = _agency_context()

        with patch("src.api.routes.agency.AgencyTokenService.issue_switched_token") as issue_token, patch(
            "src.api.routes.agency.get_tenant_context", return_value=tenant_context
        ), patch(
            "src.platform.rbac.get_tenant_context", return_value=tenant_context
        ):
            with _build_client(db_session, tenant_context) as client:
                response = client.post(
                    "/api/agency/stores/switch",
                    json={"tenant_id": "tenant-not-allowed"},
                )

        assert response.status_code == 403
        assert response.json()["detail"] == "You do not have access to this store"
        issue_token.assert_not_called()
