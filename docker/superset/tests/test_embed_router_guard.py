"""
Tests for Chrome-less Embed Router Guard.

Phase 3 (5.6.3) — Block non-embed routes in Superset.

Verifies:
- Allowed routes pass through (dashboard, chart, health, static)
- Blocked routes return 403 (sqllab, explore, dataset, login)
- Unknown routes pass through (handled by jwt_auth deny-by-default)
"""

import pytest
from unittest.mock import patch, Mock

from docker.superset.embed_router_guard import (
    _is_allowed_route,
    _is_blocked_route,
    guard_embed_navigation,
    ALLOWED_ROUTE_PREFIXES,
    BLOCKED_ROUTE_PREFIXES,
)


class TestRouteClassification:
    """Test route classification functions."""

    def test_dashboard_route_allowed(self):
        assert _is_allowed_route("/superset/dashboard/123") is True

    def test_chart_api_allowed(self):
        assert _is_allowed_route("/api/v1/chart/456") is True

    def test_dashboard_api_allowed(self):
        assert _is_allowed_route("/api/v1/dashboard/789") is True

    def test_health_allowed(self):
        assert _is_allowed_route("/health") is True

    def test_static_allowed(self):
        assert _is_allowed_route("/static/js/app.js") is True

    def test_guest_token_allowed(self):
        assert _is_allowed_route("/api/v1/guest_token/") is True

    def test_sqllab_blocked(self):
        assert _is_blocked_route("/superset/sqllab") is True

    def test_explore_blocked(self):
        assert _is_blocked_route("/superset/explore") is True

    def test_dataset_api_blocked(self):
        assert _is_blocked_route("/api/v1/dataset/1") is True

    def test_database_api_blocked(self):
        assert _is_blocked_route("/api/v1/database/1") is True

    def test_profile_blocked(self):
        assert _is_blocked_route("/superset/profile/admin") is True

    def test_login_blocked(self):
        assert _is_blocked_route("/login/") is True

    def test_register_blocked(self):
        assert _is_blocked_route("/register/") is True

    def test_unknown_route_neither_allowed_nor_blocked(self):
        """Unknown routes are not in either list."""
        assert _is_allowed_route("/api/v1/unknown") is False
        assert _is_blocked_route("/api/v1/unknown") is False


class TestGuardEmbedNavigation:
    """Test the Flask before_request handler."""

    @patch("docker.superset.embed_router_guard.request")
    def test_allowed_route_returns_none(self, mock_request):
        """Allowed routes pass through (return None)."""
        mock_request.path = "/superset/dashboard/123"
        result = guard_embed_navigation()
        assert result is None

    @patch("docker.superset.embed_router_guard.request")
    def test_blocked_route_returns_403(self, mock_request):
        """Blocked routes return 403 JSON response."""
        mock_request.path = "/superset/sqllab"
        mock_request.method = "GET"
        mock_request.remote_addr = "127.0.0.1"

        with patch("docker.superset.embed_router_guard.jsonify") as mock_jsonify:
            mock_response = Mock()
            mock_jsonify.return_value = mock_response

            result = guard_embed_navigation()

            assert result is mock_response
            mock_response.status_code = 403
            mock_jsonify.assert_called_once()
            call_args = mock_jsonify.call_args[0][0]
            assert "Navigation not allowed" in call_args["error"]

    @patch("docker.superset.embed_router_guard.request")
    def test_unknown_route_passes_through(self, mock_request):
        """Routes not in either list pass through."""
        mock_request.path = "/api/v1/some_new_endpoint"
        result = guard_embed_navigation()
        assert result is None
