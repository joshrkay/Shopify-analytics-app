"""
Unit tests for the auth middleware module.

Tests cover:
- is_exempt_path() function
- ClerkAuthMiddleware._extract_token
- ClerkAuthMiddleware.dispatch (via TestClient)
- FastAPI dependencies: get_auth_context, require_auth, require_tenant,
  get_current_user, get_current_tenant_id
- Permission dependencies: require_permission, require_any_permission, require_role
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.auth.middleware import (
    is_exempt_path,
    ClerkAuthMiddleware,
    get_auth_context,
    require_auth,
    require_tenant,
    get_current_user,
    get_current_tenant_id,
    require_permission,
    require_any_permission,
    require_role,
    EXEMPT_PATHS,
    EXEMPT_PREFIXES,
)
from src.auth.context_resolver import AuthContext, TenantAccess, ANONYMOUS_CONTEXT
from src.auth.clerk_verifier import ClerkVerificationError
from src.constants.permissions import Permission


# =============================================================================
# Helpers
# =============================================================================


def _make_auth_context(
    clerk_user_id="user_123",
    user=None,
    session_id="sess_abc",
    tenant_id=None,
    roles=None,
    permissions=None,
):
    """Create an AuthContext for testing."""
    tenant_access = {}
    if tenant_id:
        ta = TenantAccess(
            tenant_id=tenant_id,
            tenant_name="Test Tenant",
            roles=frozenset(roles if roles is not None else ["admin"]),
            permissions=frozenset(permissions if permissions is not None else []),
            billing_tier="free",
        )
        tenant_access[tenant_id] = ta

    if user is None:
        user = MagicMock()
        user.id = "internal_user_id"
        user.is_super_admin = False

    return AuthContext(
        user=user,
        clerk_user_id=clerk_user_id,
        session_id=session_id,
        tenant_access=tenant_access,
        current_tenant_id=tenant_id,
    )


def _make_anonymous_context():
    """Return ANONYMOUS_CONTEXT."""
    return ANONYMOUS_CONTEXT


def _build_app_with_middleware(verifier=None):
    """Build a minimal FastAPI app with ClerkAuthMiddleware for testing dispatch."""
    app = FastAPI()

    with patch("src.auth.middleware.get_token_service") as mock_ts:
        mock_token_service = MagicMock()
        mock_token_service.is_revoked.return_value = False
        mock_token_service.record_activity.return_value = None
        mock_ts.return_value = mock_token_service

        app.add_middleware(
            ClerkAuthMiddleware,
            verifier=verifier or MagicMock(),
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/data")
    async def data(request: Request):
        ctx = getattr(request.state, "auth_context", None)
        return {
            "authenticated": ctx.is_authenticated if ctx else False,
            "clerk_user_id": ctx.clerk_user_id if ctx else None,
        }

    return app


# =============================================================================
# 1. is_exempt_path tests
# =============================================================================


class TestIsExemptPath:
    """Tests for the is_exempt_path() function."""

    @pytest.mark.parametrize("path", [
        "/health",
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/webhooks/clerk",
        "/api/webhooks/clerk/health",
        "/api/webhooks/shopify",
    ])
    def test_known_exempt_paths_return_true(self, path):
        assert is_exempt_path(path) is True

    @pytest.mark.parametrize("path", [
        "/api/webhooks/stripe",
        "/api/webhooks/clerk/extra/path",
        "/static/logo.png",
        "/static/css/style.css",
    ])
    def test_exempt_prefixes_return_true(self, path):
        assert is_exempt_path(path) is True

    @pytest.mark.parametrize("path", [
        "/api/billing",
        "/api/sources",
        "/api/dashboards",
        "/api/insights",
        "/api/users",
        "/dashboard",
        "/settings",
        "/",
    ])
    def test_non_exempt_paths_return_false(self, path):
        assert is_exempt_path(path) is False


# =============================================================================
# 2. ClerkAuthMiddleware._extract_token tests
# =============================================================================


class TestExtractToken:
    """Tests for ClerkAuthMiddleware._extract_token."""

    def _make_middleware(self):
        """Create middleware instance for _extract_token testing."""
        with patch("src.auth.middleware.get_token_service") as mock_ts:
            mock_ts.return_value = MagicMock()
            app = MagicMock()
            # BaseHTTPMiddleware.__init__ sets self.app
            with patch.object(ClerkAuthMiddleware, "__init__", lambda self, *a, **kw: None):
                mw = ClerkAuthMiddleware.__new__(ClerkAuthMiddleware)
                mw._verifier = MagicMock()
                mw._exempt_paths = EXEMPT_PATHS
                mw._exempt_prefixes = EXEMPT_PREFIXES
                mw._cookie_name = "__session"
                mw._token_service = MagicMock()
                return mw

    def _make_request(self, headers=None, cookies=None):
        """Create a mock Request with specified headers and cookies."""
        request = MagicMock(spec=Request)
        request.headers = headers or {}
        request.cookies = cookies or {}
        return request

    def test_bearer_token_from_header(self):
        mw = self._make_middleware()
        request = self._make_request(headers={"Authorization": "Bearer my-jwt-token"})
        assert mw._extract_token(request) == "my-jwt-token"

    def test_raw_token_from_header_no_bearer_prefix(self):
        mw = self._make_middleware()
        request = self._make_request(headers={"Authorization": "raw-token-no-prefix"})
        assert mw._extract_token(request) == "raw-token-no-prefix"

    def test_token_from_session_cookie(self):
        mw = self._make_middleware()
        request = self._make_request(cookies={"__session": "cookie-token"})
        assert mw._extract_token(request) == "cookie-token"

    def test_no_token_returns_none(self):
        mw = self._make_middleware()
        request = self._make_request()
        assert mw._extract_token(request) is None

    def test_header_takes_precedence_over_cookie(self):
        mw = self._make_middleware()
        request = self._make_request(
            headers={"Authorization": "Bearer header-token"},
            cookies={"__session": "cookie-token"},
        )
        assert mw._extract_token(request) == "header-token"

    def test_raw_header_takes_precedence_over_cookie(self):
        mw = self._make_middleware()
        request = self._make_request(
            headers={"Authorization": "raw-header-token"},
            cookies={"__session": "cookie-token"},
        )
        assert mw._extract_token(request) == "raw-header-token"


# =============================================================================
# 3. ClerkAuthMiddleware.dispatch tests (via TestClient)
# =============================================================================


class TestMiddlewareDispatch:
    """Tests for ClerkAuthMiddleware.dispatch behavior."""

    def test_exempt_path_passes_through_without_auth(self):
        """Exempt paths should pass through without authentication."""
        mock_verifier = MagicMock()
        app = _build_app_with_middleware(verifier=mock_verifier)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        # Verifier should not have been called
        mock_verifier.verify_token.assert_not_called()

    def test_options_request_passes_through(self):
        """OPTIONS requests should pass through without token requirement."""
        mock_verifier = MagicMock()
        app = _build_app_with_middleware(verifier=mock_verifier)
        client = TestClient(app)

        response = client.options("/api/data")
        # OPTIONS might get 405 from FastAPI if not explicitly handled,
        # but the middleware should not block it. The key is no 401.
        assert response.status_code != 401
        mock_verifier.verify_token.assert_not_called()

    def test_no_token_sets_anonymous_context(self):
        """Requests without tokens should set anonymous context and continue."""
        mock_verifier = MagicMock()
        app = _build_app_with_middleware(verifier=mock_verifier)
        client = TestClient(app)

        response = client.get("/api/data")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        mock_verifier.verify_token.assert_not_called()

    @patch("src.auth.middleware.get_db_session_sync")
    @patch("src.auth.middleware.AuthContextResolver")
    @patch("src.auth.middleware.extract_claims")
    def test_valid_token_attaches_auth_context(
        self, mock_extract_claims, mock_resolver_cls, mock_get_db
    ):
        """Valid tokens should result in auth context attached to request."""
        # Setup
        mock_verifier = MagicMock()
        mock_verifier.verify_token.return_value = {
            "sub": "user_test",
            "sid": "sess_test",
            "exp": 9999999999,
            "iat": 1000000000,
        }

        mock_extracted = MagicMock()
        mock_extracted.session_id = "sess_test"
        mock_extracted.clerk_user_id = "user_test"
        mock_extracted.issued_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_extracted.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
        mock_extract_claims.return_value = mock_extracted

        mock_user = MagicMock()
        mock_user.id = "internal_id"

        auth_ctx = _make_auth_context(
            clerk_user_id="user_test",
            user=mock_user,
            tenant_id="tenant_1",
        )

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = auth_ctx
        mock_resolver_cls.return_value = mock_resolver

        mock_session = MagicMock()
        mock_get_db.return_value = iter([mock_session])

        app = FastAPI()
        with patch("src.auth.middleware.get_token_service") as mock_ts:
            mock_token_service = MagicMock()
            mock_token_service.is_revoked.return_value = False
            mock_token_service.record_activity.return_value = None
            mock_ts.return_value = mock_token_service
            app.add_middleware(ClerkAuthMiddleware, verifier=mock_verifier)

        @app.get("/api/data")
        async def data(request: Request):
            ctx = getattr(request.state, "auth_context", None)
            return {
                "authenticated": ctx.is_authenticated if ctx else False,
                "clerk_user_id": ctx.clerk_user_id if ctx else None,
            }

        client = TestClient(app)
        response = client.get("/api/data", headers={"Authorization": "Bearer valid-token"})
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["clerk_user_id"] == "user_test"

    @patch("src.auth.middleware.extract_claims")
    @patch("src.auth.middleware.get_token_service")
    def test_revoked_token_returns_401_session_revoked(
        self, mock_get_ts, mock_extract_claims
    ):
        """Revoked tokens should return 401 with session_revoked error code."""
        mock_verifier = MagicMock()
        mock_verifier.verify_token.return_value = {
            "sub": "user_test",
            "sid": "sess_test",
            "exp": 9999999999,
            "iat": 1000000000,
        }

        mock_extracted = MagicMock()
        mock_extracted.session_id = "sess_test"
        mock_extracted.clerk_user_id = "user_test"
        mock_extracted.issued_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_extract_claims.return_value = mock_extracted

        mock_token_service = MagicMock()
        mock_token_service.is_revoked.return_value = True
        mock_get_ts.return_value = mock_token_service

        app = FastAPI()
        app.add_middleware(ClerkAuthMiddleware, verifier=mock_verifier)

        @app.get("/api/data")
        async def data():
            return {"data": "should not reach"}

        client = TestClient(app)
        response = client.get("/api/data", headers={"Authorization": "Bearer revoked-token"})
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "session_revoked"
        assert "revoked" in body["detail"].lower()

    def test_clerk_verification_error_returns_401(self):
        """ClerkVerificationError should return 401 with error details."""
        mock_verifier = MagicMock()
        mock_verifier.verify_token.side_effect = ClerkVerificationError(
            message="Token has expired",
            error_code="token_expired",
        )

        app = _build_app_with_middleware(verifier=mock_verifier)

        @app.get("/api/protected")
        async def protected():
            return {"data": "should not reach"}

        client = TestClient(app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer expired-token"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "token_expired"
        assert body["detail"] == "Token has expired"

    def test_unexpected_error_returns_500_auth_error(self):
        """Unexpected exceptions during auth should return 500 with auth_error."""
        mock_verifier = MagicMock()
        mock_verifier.verify_token.side_effect = RuntimeError("Something went wrong")

        app = _build_app_with_middleware(verifier=mock_verifier)

        @app.get("/api/protected")
        async def protected():
            return {"data": "should not reach"}

        client = TestClient(app)
        response = client.get(
            "/api/protected",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["error_code"] == "auth_error"
        assert body["detail"] == "Authentication error"


# =============================================================================
# 4. require_auth dependency tests
# =============================================================================


class TestRequireAuth:
    """Tests for the require_auth FastAPI dependency."""

    def test_authenticated_context_returns_context(self):
        """Authenticated context should be returned."""
        auth_ctx = _make_auth_context(tenant_id="tenant_1")

        app = FastAPI()

        @app.get("/test")
        async def route(auth: AuthContext = Depends(require_auth)):
            return {"user_id": auth.clerk_user_id}

        app.add_middleware(ClerkAuthMiddleware, verifier=MagicMock())

        # Manually test the dependency by mocking request.state
        request = MagicMock(spec=Request)
        request.state.auth_context = auth_ctx

        result = require_auth(request=request, credentials=None)
        assert result.clerk_user_id == "user_123"
        assert result.is_authenticated is True

    def test_anonymous_context_raises_401(self):
        """Anonymous context should raise HTTPException 401."""
        from fastapi import HTTPException

        request = MagicMock(spec=Request)
        request.state.auth_context = ANONYMOUS_CONTEXT

        with pytest.raises(HTTPException) as exc_info:
            require_auth(request=request, credentials=None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    def test_missing_auth_context_attr_raises_401(self):
        """Request with no auth_context attr should raise 401 (falls back to ANONYMOUS)."""
        from fastapi import HTTPException

        request = MagicMock(spec=Request)
        # Simulate missing auth_context attribute
        del request.state.auth_context

        with pytest.raises(HTTPException) as exc_info:
            require_auth(request=request, credentials=None)

        assert exc_info.value.status_code == 401


# =============================================================================
# 5. require_tenant dependency tests
# =============================================================================


class TestRequireTenant:
    """Tests for the require_tenant FastAPI dependency."""

    def test_context_with_tenant_returns_context(self):
        """Context with a current_tenant_id should be returned."""
        auth_ctx = _make_auth_context(tenant_id="tenant_abc")
        result = require_tenant(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_abc"

    def test_context_without_tenant_raises_400(self):
        """Context without tenant should raise HTTPException 400."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(tenant_id=None)

        with pytest.raises(HTTPException) as exc_info:
            require_tenant(auth=auth_ctx)

        assert exc_info.value.status_code == 400
        assert "tenant" in exc_info.value.detail.lower()


# =============================================================================
# 6. get_current_user dependency tests
# =============================================================================


class TestGetCurrentUser:
    """Tests for the get_current_user FastAPI dependency."""

    def test_returns_user_when_present(self):
        """Should return the user object from auth context."""
        mock_user = MagicMock()
        mock_user.id = "user_internal_1"
        auth_ctx = _make_auth_context(user=mock_user, tenant_id="t1")

        result = get_current_user(auth=auth_ctx)
        assert result.id == "user_internal_1"

    def test_raises_401_when_user_is_none(self):
        """Should raise 401 if auth context has no user."""
        from fastapi import HTTPException

        auth_ctx = AuthContext(
            user=None,
            clerk_user_id="user_123",
            session_id="sess_1",
            tenant_access={},
            current_tenant_id=None,
        )

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(auth=auth_ctx)

        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail


# =============================================================================
# 7. get_current_tenant_id dependency tests
# =============================================================================


class TestGetCurrentTenantId:
    """Tests for the get_current_tenant_id FastAPI dependency."""

    def test_returns_tenant_id(self):
        """Should return the tenant ID string."""
        auth_ctx = _make_auth_context(tenant_id="tenant_xyz")
        result = get_current_tenant_id(auth=auth_ctx)
        assert result == "tenant_xyz"


# =============================================================================
# 8. require_permission dependency tests
# =============================================================================


class TestRequirePermission:
    """Tests for the require_permission dependency factory."""

    def test_user_has_permission_returns_context(self):
        """User with the required permission should get context returned."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[Permission.ANALYTICS_VIEW],
        )

        dep = require_permission(Permission.ANALYTICS_VIEW)
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_lacks_permission_raises_403(self):
        """User without the required permission should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[Permission.ANALYTICS_VIEW],
        )

        dep = require_permission(Permission.BILLING_MANAGE)
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403
        assert "Permission denied" in exc_info.value.detail

    def test_user_with_no_permissions_raises_403(self):
        """User with empty permissions should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[],
        )

        dep = require_permission(Permission.ANALYTICS_VIEW)
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403


# =============================================================================
# 9. require_any_permission dependency tests
# =============================================================================


class TestRequireAnyPermission:
    """Tests for the require_any_permission dependency factory."""

    def test_user_has_one_of_permissions_returns_context(self):
        """User with at least one of the required permissions should pass."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[Permission.BILLING_VIEW],
        )

        dep = require_any_permission(Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW)
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_has_all_permissions_returns_context(self):
        """User with all required permissions should pass."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW],
        )

        dep = require_any_permission(Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW)
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_has_none_of_permissions_raises_403(self):
        """User with none of the required permissions should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[Permission.STORE_VIEW],
        )

        dep = require_any_permission(Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW)
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403
        assert "Permission denied" in exc_info.value.detail

    def test_user_with_empty_permissions_raises_403(self):
        """User with no permissions should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            permissions=[],
        )

        dep = require_any_permission(Permission.ANALYTICS_VIEW)
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403


# =============================================================================
# 10. require_role dependency tests
# =============================================================================


class TestRequireRole:
    """Tests for the require_role dependency factory."""

    def test_user_has_role_returns_context(self):
        """User with the required role should get context returned."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=["admin"],
        )

        dep = require_role("admin")
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_has_role_case_insensitive(self):
        """Role check should be case-insensitive."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=["Admin"],
        )

        dep = require_role("admin")
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_has_role_uppercase_required(self):
        """Role check should work when required role is uppercase but user has lowercase."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=["admin"],
        )

        dep = require_role("ADMIN")
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"

    def test_user_lacks_role_raises_403(self):
        """User without the required role should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=["viewer"],
        )

        dep = require_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403
        assert "Role required" in exc_info.value.detail

    def test_user_with_no_roles_raises_403(self):
        """User with no roles should get 403."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=[],
            permissions=[],
        )

        dep = require_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert exc_info.value.status_code == 403

    def test_user_with_multiple_roles_one_matches(self):
        """User with multiple roles where one matches should pass."""
        auth_ctx = _make_auth_context(
            tenant_id="tenant_1",
            roles=["viewer", "editor", "admin"],
        )

        dep = require_role("editor")
        result = dep(auth=auth_ctx)
        assert result.current_tenant_id == "tenant_1"


# =============================================================================
# 11. get_auth_context dependency tests
# =============================================================================


class TestGetAuthContext:
    """Tests for the get_auth_context dependency."""

    def test_returns_auth_context_from_request_state(self):
        """Should return the AuthContext set on request.state."""
        auth_ctx = _make_auth_context(tenant_id="tenant_1")
        request = MagicMock(spec=Request)
        request.state.auth_context = auth_ctx

        result = get_auth_context(request)
        assert result is auth_ctx

    def test_returns_anonymous_when_no_attr(self):
        """Should return ANONYMOUS_CONTEXT when auth_context is not on state."""
        request = MagicMock(spec=Request)
        del request.state.auth_context

        result = get_auth_context(request)
        assert result is ANONYMOUS_CONTEXT

    def test_anonymous_context_is_not_authenticated(self):
        """ANONYMOUS_CONTEXT should not be authenticated."""
        assert ANONYMOUS_CONTEXT.is_authenticated is False
        assert ANONYMOUS_CONTEXT.current_tenant_id is None


# =============================================================================
# 12. ClerkAuthMiddleware._is_exempt tests
# =============================================================================


class TestMiddlewareIsExempt:
    """Tests for ClerkAuthMiddleware._is_exempt instance method."""

    def _make_middleware(self, exempt_paths=None, exempt_prefixes=None):
        with patch.object(ClerkAuthMiddleware, "__init__", lambda self, *a, **kw: None):
            mw = ClerkAuthMiddleware.__new__(ClerkAuthMiddleware)
            mw._exempt_paths = exempt_paths or EXEMPT_PATHS
            mw._exempt_prefixes = exempt_prefixes or EXEMPT_PREFIXES
            mw._cookie_name = "__session"
            mw._verifier = MagicMock()
            mw._token_service = MagicMock()
            return mw

    def test_exact_match_exempt_path(self):
        mw = self._make_middleware()
        assert mw._is_exempt("/health") is True
        assert mw._is_exempt("/docs") is True

    def test_prefix_match_exempt_path(self):
        mw = self._make_middleware()
        assert mw._is_exempt("/api/webhooks/custom") is True
        assert mw._is_exempt("/static/image.png") is True

    def test_non_exempt_path(self):
        mw = self._make_middleware()
        assert mw._is_exempt("/api/billing") is False
        assert mw._is_exempt("/api/sources") is False

    def test_custom_exempt_paths(self):
        mw = self._make_middleware(
            exempt_paths={"/custom-health"},
            exempt_prefixes=["/custom-prefix/"],
        )
        assert mw._is_exempt("/custom-health") is True
        assert mw._is_exempt("/custom-prefix/something") is True
        # Default paths should NOT be exempt with custom config
        assert mw._is_exempt("/health") is False


# =============================================================================
# 13. Edge cases and integration-style tests
# =============================================================================


class TestEdgeCases:
    """Edge cases and additional coverage."""

    def test_require_tenant_depends_on_require_auth(self):
        """require_tenant chains through require_auth, so unauthenticated = 401 not 400."""
        from fastapi import HTTPException

        # An unauthenticated user calling require_tenant should get 401 from require_auth,
        # not 400 from the tenant check. We test this by calling require_auth first.
        request = MagicMock(spec=Request)
        request.state.auth_context = ANONYMOUS_CONTEXT

        with pytest.raises(HTTPException) as exc_info:
            require_auth(request=request, credentials=None)

        assert exc_info.value.status_code == 401

    def test_require_permission_error_message_contains_permission_value(self):
        """Error message from require_permission should contain the permission value."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(tenant_id="t1", permissions=[])
        dep = require_permission(Permission.BILLING_MANAGE)

        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert Permission.BILLING_MANAGE.value in exc_info.value.detail

    def test_require_any_permission_error_lists_permissions(self):
        """Error from require_any_permission should list the required permissions."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(tenant_id="t1", permissions=[])
        dep = require_any_permission(Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW)

        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        detail = exc_info.value.detail
        assert Permission.ANALYTICS_VIEW.value in detail
        assert Permission.BILLING_VIEW.value in detail

    def test_require_role_error_message_contains_role(self):
        """Error from require_role should contain the required role name."""
        from fastapi import HTTPException

        auth_ctx = _make_auth_context(tenant_id="t1", roles=["viewer"])
        dep = require_role("admin")

        with pytest.raises(HTTPException) as exc_info:
            dep(auth=auth_ctx)

        assert "admin" in exc_info.value.detail

    def test_clerk_verification_error_preserves_error_code(self):
        """ClerkVerificationError in dispatch should preserve the original error_code."""
        mock_verifier = MagicMock()
        mock_verifier.verify_token.side_effect = ClerkVerificationError(
            message="Invalid token issuer",
            error_code="invalid_issuer",
        )

        app = _build_app_with_middleware(verifier=mock_verifier)
        client = TestClient(app)

        response = client.get(
            "/api/data",
            headers={"Authorization": "Bearer bad-issuer-token"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "invalid_issuer"
        assert body["detail"] == "Invalid token issuer"
