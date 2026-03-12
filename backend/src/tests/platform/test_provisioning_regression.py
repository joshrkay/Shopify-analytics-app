"""
Provisioning regression tests.

Exercises the full /api/auth/provision → ClerkSyncService → TenantGuard
pipeline to prevent regressions in tenant provisioning.

These tests cover the scenarios most likely to break silently in production:

1. Happy path — new org gets provisioned end-to-end
2. Idempotency — calling provision twice returns the same tenant_id
3. Concurrent provision — IntegrityError handled, no duplicate Tenant rows
4. Missing JWT — returns 401
5. JWT without org claim — returns 403
6. ClerkSyncService failure — returns 503 (not 500)
7. Middleware PUBLIC_PATHS — /api/auth/provision bypasses TenantContextMiddleware

IMPORTANT: These tests mock DB and ClerkSyncService; they do NOT require a live
PostgreSQL or Clerk instance.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from src.api.routes.auth_provision import router as provision_router


# =============================================================================
# Fixtures
# =============================================================================

VALID_CLERK_USER_ID = "user_abc123"
VALID_CLERK_ORG_ID = "org_xyz987"
VALID_TENANT_UUID = "11111111-1111-1111-1111-111111111111"
VALID_JWT_PAYLOAD = {
    "sub": VALID_CLERK_USER_ID,
    "org_id": VALID_CLERK_ORG_ID,
    "org_role": "org:admin",
    "iss": "https://test.clerk.accounts.dev",
    "exp": 9999999999,
    "iat": 1000000000,
}
VALID_JWT_PAYLOAD_V2 = {
    "sub": VALID_CLERK_USER_ID,
    "o": {"id": VALID_CLERK_ORG_ID, "rol": "org:admin"},
    "iss": "https://test.clerk.accounts.dev",
    "exp": 9999999999,
    "iat": 1000000000,
}


def _make_mock_tenant(tenant_id: str = VALID_TENANT_UUID, clerk_org_id: str = VALID_CLERK_ORG_ID):
    t = MagicMock()
    t.id = tenant_id
    t.clerk_org_id = clerk_org_id
    return t


@pytest.fixture
def app():
    """Minimal FastAPI app with only the provision router."""
    a = FastAPI()
    a.include_router(provision_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _mock_jwt(payload: dict):
    """Patch _decode_clerk_jwt to return the given payload."""
    return patch(
        "src.api.routes.auth_provision._decode_clerk_jwt",
        return_value=payload,
    )


def _mock_db_session(mock_session):
    """Patch get_db_session_sync to yield mock_session."""
    return patch(
        "src.api.routes.auth_provision.get_db_session_sync",
        return_value=iter([mock_session]),
    )


# =============================================================================
# 1. Happy path
# =============================================================================

class TestProvisionHappyPath:
    def test_new_org_provisioned_successfully(self, client):
        """A new Clerk org with no DB records gets provisioned end-to-end."""
        mock_tenant = _make_mock_tenant()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tenant

        mock_sync = MagicMock()
        mock_sync_cls = MagicMock(return_value=mock_sync)

        with _mock_jwt(VALID_JWT_PAYLOAD), _mock_db_session(db):
            with patch("src.api.routes.auth_provision.ClerkSyncService", mock_sync_cls):
                res = client.post(
                    "/api/auth/provision",
                    headers={"Authorization": "Bearer fake.token.here"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["tenant_id"] == VALID_TENANT_UUID
        mock_sync.get_or_create_user.assert_called_once_with(clerk_user_id=VALID_CLERK_USER_ID)
        mock_sync.sync_tenant_from_org.assert_called_once()
        mock_sync.sync_membership.assert_called_once()
        db.commit.assert_called_once()

    def test_clerk_jwt_v2_format_accepted(self, client):
        """Clerk JWT v2 (org claims under 'o') works the same as v1."""
        mock_tenant = _make_mock_tenant()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tenant

        mock_sync = MagicMock()

        with _mock_jwt(VALID_JWT_PAYLOAD_V2), _mock_db_session(db):
            with patch("src.api.routes.auth_provision.ClerkSyncService", return_value=mock_sync):
                res = client.post(
                    "/api/auth/provision",
                    headers={"Authorization": "Bearer fake.token.here"},
                )

        assert res.status_code == 200
        assert res.json()["tenant_id"] == VALID_TENANT_UUID


# =============================================================================
# 2. Idempotency
# =============================================================================

class TestProvisionIdempotency:
    def test_second_call_returns_same_tenant_id(self, client):
        """Calling /provision twice returns identical tenant_id both times."""
        mock_tenant = _make_mock_tenant()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tenant

        mock_sync = MagicMock()

        for _ in range(2):
            with _mock_jwt(VALID_JWT_PAYLOAD), _mock_db_session(db):
                with patch("src.api.routes.auth_provision.ClerkSyncService", return_value=mock_sync):
                    res = client.post(
                        "/api/auth/provision",
                        headers={"Authorization": "Bearer fake.token.here"},
                    )
            assert res.status_code == 200
            assert res.json()["tenant_id"] == VALID_TENANT_UUID


# =============================================================================
# 3. Concurrent provision — IntegrityError handling
# =============================================================================

class TestProvisionConcurrency:
    def test_integrity_error_on_commit_resolves_via_requery(self, client):
        """
        When two requests race to create the same tenant, the loser gets an
        IntegrityError on commit.  The endpoint handles this by rolling back
        and re-querying — it must return 200 with the correct tenant_id.
        """
        mock_tenant = _make_mock_tenant()
        db = MagicMock()
        # commit raises IntegrityError (duplicate key)
        db.commit.side_effect = SAIntegrityError("duplicate", {}, Exception())
        # re-query after rollback finds the tenant
        db.query.return_value.filter.return_value.first.return_value = mock_tenant

        mock_sync = MagicMock()

        with _mock_jwt(VALID_JWT_PAYLOAD), _mock_db_session(db):
            with patch("src.api.routes.auth_provision.ClerkSyncService", return_value=mock_sync):
                res = client.post(
                    "/api/auth/provision",
                    headers={"Authorization": "Bearer fake.token.here"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["tenant_id"] == VALID_TENANT_UUID
        db.rollback.assert_called_once()

    def test_integrity_error_without_requery_result_returns_503(self, client):
        """
        If IntegrityError fires but the re-query also returns nothing (very
        unusual), the endpoint returns 503 so the client retries.
        """
        db = MagicMock()
        db.commit.side_effect = SAIntegrityError("duplicate", {}, Exception())
        db.query.return_value.filter.return_value.first.return_value = None  # not found

        mock_sync = MagicMock()

        with _mock_jwt(VALID_JWT_PAYLOAD), _mock_db_session(db):
            with patch("src.api.routes.auth_provision.ClerkSyncService", return_value=mock_sync):
                res = client.post(
                    "/api/auth/provision",
                    headers={"Authorization": "Bearer fake.token.here"},
                )

        assert res.status_code == 503


# =============================================================================
# 4. Auth failures
# =============================================================================

class TestProvisionAuthFailures:
    def test_missing_authorization_header_returns_401(self, client):
        res = client.post("/api/auth/provision")
        # HTTPBearer with auto_error=False yields None credentials,
        # which the handler converts to a 401.
        assert res.status_code == 401

    def test_invalid_jwt_returns_401(self, client):
        with patch(
            "src.api.routes.auth_provision._decode_clerk_jwt",
            side_effect=Exception("decode failed"),
        ):
            res = client.post(
                "/api/auth/provision",
                headers={"Authorization": "Bearer bad.token"},
            )
        assert res.status_code == 401

    def test_jwt_missing_sub_returns_403(self, client):
        payload_no_sub = {**VALID_JWT_PAYLOAD}
        del payload_no_sub["sub"]
        with _mock_jwt(payload_no_sub):
            res = client.post(
                "/api/auth/provision",
                headers={"Authorization": "Bearer fake.token.here"},
            )
        assert res.status_code == 403

    def test_jwt_missing_org_id_returns_403(self, client):
        payload_no_org = {
            "sub": VALID_CLERK_USER_ID,
            "iss": "https://test.clerk.accounts.dev",
            "exp": 9999999999,
            "iat": 1000000000,
        }
        with _mock_jwt(payload_no_org):
            res = client.post(
                "/api/auth/provision",
                headers={"Authorization": "Bearer fake.token.here"},
            )
        assert res.status_code == 403


# =============================================================================
# 5. ClerkSyncService failure returns 503
# =============================================================================

class TestProvisionSyncFailure:
    def test_sync_service_exception_returns_503(self, client):
        """
        If ClerkSyncService raises an unexpected error the endpoint must return
        503 (retryable) instead of 500 (which the frontend treats as fatal).
        """
        db = MagicMock()
        mock_sync = MagicMock()
        mock_sync.sync_tenant_from_org.side_effect = RuntimeError("DB connection lost")

        with _mock_jwt(VALID_JWT_PAYLOAD), _mock_db_session(db):
            with patch("src.api.routes.auth_provision.ClerkSyncService", return_value=mock_sync):
                res = client.post(
                    "/api/auth/provision",
                    headers={"Authorization": "Bearer fake.token.here"},
                )

        assert res.status_code == 503
        db.rollback.assert_called_once()


# =============================================================================
# 6. /api/auth/provision is in PUBLIC_PATHS (middleware bypass)
# =============================================================================

class TestProvisionMiddlewareBypass:
    def test_provision_path_in_public_paths(self):
        """
        /api/auth/provision must be in PUBLIC_PATHS so that
        TenantContextMiddleware does not intercept it and return 403 before
        the handler runs.
        """
        # We test the middleware source directly rather than spinning up the
        # full middleware stack, to keep this test fast and free of DB deps.
        #
        # NOTE: __call__ is a thin CORS-header wrapper that delegates all
        # request-handling logic to _handle_request.  PUBLIC_PATHS lives in
        # _handle_request, so that is the method we must inspect here.
        import inspect
        import src.platform.tenant_context as tc_module

        # Read the source of _handle_request and confirm the path is present
        source = inspect.getsource(tc_module.TenantContextMiddleware._handle_request)
        assert "/api/auth/provision" in source, (
            "/api/auth/provision is NOT in PUBLIC_PATHS inside "
            "TenantContextMiddleware._handle_request — unprovisioned users will "
            "never be able to reach the provision endpoint."
        )

        # Also assert __call__ delegates to _handle_request (structural guard:
        # if someone accidentally inlines the logic back into __call__ without
        # keeping PUBLIC_PATHS there, the first assertion above will catch it).
        call_source = inspect.getsource(tc_module.TenantContextMiddleware.__call__)
        assert "_handle_request" in call_source, (
            "TenantContextMiddleware.__call__ no longer delegates to _handle_request. "
            "Ensure PUBLIC_PATHS bypass is still reached on every request."
        )
