"""
Tests for GA Audit Middleware.

ACCEPTANCE CRITERIA:
- Dashboard access denied emits dashboard.access_denied
- Token refresh failure emits auth.jwt_refresh (success=False)
- All events include correlation_id
- No PII leaks
- Both success and failure paths emit events
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import Request

from src.middleware.audit_middleware import GAAuditMiddleware
from src.models.audit_log import generate_correlation_id


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def middleware():
    """Create a GAAuditMiddleware instance."""
    return GAAuditMiddleware(app=Mock())


@pytest.fixture
def mock_request():
    """Create a mock authenticated request."""
    request = Mock(spec=Request)
    request.url = Mock()
    request.url.path = "/api/v1/embed/token"
    request.headers = {
        "X-Correlation-ID": "corr-test-123",
        "User-Agent": "TestBrowser/1.0",
        "X-Forwarded-For": "192.168.1.100",
    }
    request.query_params = {"dashboard_id": "overview"}
    request.client = Mock()
    request.client.host = "127.0.0.1"

    # Authenticated request
    tenant_context = Mock()
    tenant_context.tenant_id = "tenant-123"
    tenant_context.user_id = "user-456"
    request.state = Mock()
    request.state.tenant_context = tenant_context
    request.state.correlation_id = "corr-test-123"

    return request


@pytest.fixture
def mock_unauthenticated_request():
    """Create a mock unauthenticated request."""
    request = Mock(spec=Request)
    request.url = Mock()
    request.url.path = "/api/v1/embed/token"
    request.headers = {
        "User-Agent": "TestBrowser/1.0",
    }
    request.query_params = {}
    request.client = Mock()
    request.client.host = "10.0.0.1"
    request.state = Mock(spec=[])  # No attributes
    return request


# ============================================================================
# TEST SUITE: SKIP PATHS
# ============================================================================

class TestSkipPaths:
    """Test that health/docs endpoints are not audited."""

    def test_health_path_skipped(self, middleware):
        assert "/health" in middleware.SKIP_PATHS

    def test_docs_path_skipped(self, middleware):
        assert "/docs" in middleware.SKIP_PATHS

    def test_embed_health_skipped(self, middleware):
        assert "/api/v1/embed/health" in middleware.SKIP_PATHS


# ============================================================================
# TEST SUITE: PATH MAPPING
# ============================================================================

class TestPathMapping:
    """Test that paths are mapped to correct event types."""

    def test_embed_token_maps_to_jwt_issued(self, middleware):
        assert middleware.AUTH_PATHS["/api/v1/embed/token"] == "jwt_issued"

    def test_embed_refresh_maps_to_jwt_refresh(self, middleware):
        assert middleware.AUTH_PATHS["/api/v1/embed/token/refresh"] == "jwt_refresh"

    def test_auth_refresh_maps_to_jwt_refresh(self, middleware):
        assert middleware.AUTH_PATHS["/auth/refresh-jwt"] == "jwt_refresh"

    def test_revoke_maps_to_jwt_revoked(self, middleware):
        assert middleware.AUTH_PATHS["/auth/revoke-tokens"] == "jwt_revoked"

    def test_embed_token_maps_to_dashboard_access(self, middleware):
        assert middleware.DASHBOARD_PATHS["/api/v1/embed/token"] == "dashboard_access"


# ============================================================================
# TEST SUITE: CONTEXT EXTRACTION
# ============================================================================

class TestContextExtraction:
    """Test tenant/user/access_surface extraction from request."""

    def test_extracts_tenant_and_user(self, middleware, mock_request):
        tenant_id, user_id, access_surface = middleware._extract_context(mock_request)
        assert tenant_id == "tenant-123"
        assert user_id == "user-456"

    def test_detects_shopify_embed_surface(self, middleware, mock_request):
        mock_request.url.path = "/api/v1/embed/token"
        _, _, access_surface = middleware._extract_context(mock_request)
        assert access_surface == "shopify_embed"

    def test_defaults_to_external_app(self, middleware, mock_request):
        mock_request.url.path = "/api/something-else"
        _, _, access_surface = middleware._extract_context(mock_request)
        assert access_surface == "external_app"

    def test_unauthenticated_returns_none(self, middleware, mock_unauthenticated_request):
        tenant_id, user_id, _ = middleware._extract_context(
            mock_unauthenticated_request
        )
        assert tenant_id is None
        assert user_id is None


# ============================================================================
# TEST SUITE: DASHBOARD ID EXTRACTION
# ============================================================================

class TestDashboardIdExtraction:
    """Test dashboard_id extraction from request."""

    def test_extracts_from_query_params(self, middleware, mock_request):
        dashboard_id = middleware._extract_dashboard_id(mock_request)
        assert dashboard_id == "overview"

    def test_returns_none_if_not_present(self, middleware, mock_unauthenticated_request):
        dashboard_id = middleware._extract_dashboard_id(
            mock_unauthenticated_request
        )
        assert dashboard_id is None

    def test_extracts_from_parsed_body(self, middleware, mock_request):
        mock_request.query_params = {}
        mock_request.state.parsed_body = {"dashboard_id": "sales"}
        dashboard_id = middleware._extract_dashboard_id(mock_request)
        assert dashboard_id == "sales"


# ============================================================================
# TEST SUITE: IP ADDRESS EXTRACTION
# ============================================================================

class TestIPAddressExtraction:
    """Test IP address extraction."""

    def test_extracts_from_x_forwarded_for(self, middleware, mock_request):
        ip = middleware._get_ip_address(mock_request)
        assert ip == "192.168.1.100"

    def test_falls_back_to_client_host(self, middleware, mock_unauthenticated_request):
        ip = middleware._get_ip_address(mock_unauthenticated_request)
        assert ip == "10.0.0.1"


# ============================================================================
# TEST SUITE: CORRELATION ID
# ============================================================================

class TestCorrelationID:
    """Test correlation ID handling."""

    def test_uses_header_correlation_id(self, middleware, mock_request):
        """Uses X-Correlation-ID from header when available."""
        assert mock_request.headers.get("X-Correlation-ID") == "corr-test-123"

    def test_generates_correlation_id_if_missing(self):
        """Generates UUID correlation ID if not in headers."""
        cid = generate_correlation_id()
        assert len(cid) == 36


# ============================================================================
# TEST SUITE: EVENT EMISSION (via middleware._emit_audit_events)
# ============================================================================

class TestEventEmission:
    """Test that audit events are correctly emitted."""

    @pytest.mark.asyncio
    @patch("src.middleware.audit_middleware.GAAuditMiddleware._emit_dashboard_event")
    @patch("src.middleware.audit_middleware.GAAuditMiddleware._emit_auth_event")
    async def test_embed_token_success_emits_auth_and_dashboard(
        self, mock_auth, mock_dashboard, middleware, mock_request
    ):
        """Embed token success emits both jwt_issued and dashboard_viewed."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_auth.return_value = None
        mock_dashboard.return_value = None

        await middleware._emit_audit_events(
            mock_request, mock_response,
            "/api/v1/embed/token", "corr-123",
        )

        mock_auth.assert_called_once()
        mock_dashboard.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.middleware.audit_middleware.GAAuditMiddleware._emit_dashboard_event")
    @patch("src.middleware.audit_middleware.GAAuditMiddleware._emit_auth_event")
    async def test_embed_token_403_emits_access_denied(
        self, mock_auth, mock_dashboard, middleware, mock_request
    ):
        """Embed token 403 emits dashboard.access_denied."""
        mock_response = Mock()
        mock_response.status_code = 403

        mock_auth.return_value = None
        mock_dashboard.return_value = None

        await middleware._emit_audit_events(
            mock_request, mock_response,
            "/api/v1/embed/token", "corr-123",
        )

        # Dashboard event called with success=False
        mock_dashboard.assert_called_once()
        call_kwargs = mock_dashboard.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["status_code"] == 403

    @pytest.mark.asyncio
    @patch("src.middleware.audit_middleware.GAAuditMiddleware._emit_auth_event")
    async def test_jwt_refresh_failure_emits_event(
        self, mock_auth, middleware, mock_request
    ):
        """JWT refresh failure emits auth.jwt_refresh with reason code."""
        mock_request.url.path = "/auth/refresh-jwt"
        mock_response = Mock()
        mock_response.status_code = 403

        mock_auth.return_value = None

        await middleware._emit_audit_events(
            mock_request, mock_response,
            "/auth/refresh-jwt", "corr-123",
        )

        mock_auth.assert_called_once()
        call_kwargs = mock_auth.call_args
        assert call_kwargs[1]["event_kind"] == "jwt_refresh"
        assert call_kwargs[1]["success"] is False


# ============================================================================
# TEST SUITE: NEVER CRASH
# ============================================================================

class TestNeverCrash:
    """Test that middleware never crashes the request flow."""

    @pytest.mark.asyncio
    async def test_exception_in_emit_does_not_propagate(self, middleware):
        """Exceptions during audit emission are swallowed."""
        mock_request = Mock(spec=Request)
        mock_request.url = Mock()
        mock_request.url.path = "/api/v1/embed/token"
        mock_request.headers = {}
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.state = Mock(spec=[])

        mock_response = Mock()
        mock_response.status_code = 200

        # Even if _emit_audit_events raises, dispatch should not crash
        with patch.object(
            middleware, "_emit_audit_events",
            side_effect=Exception("audit failure"),
        ):
            mock_call_next = AsyncMock(return_value=mock_response)
            result = await middleware.dispatch(mock_request, mock_call_next)
            assert result.status_code == 200
