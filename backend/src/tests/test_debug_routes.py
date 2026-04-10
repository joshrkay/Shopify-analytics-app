"""
Tests for debug endpoint feature-flag + auth gating.

Debug endpoints expose sensitive diagnostics and MUST be:
1) disabled by default via DEBUG_ROUTES_ENABLED=false, and
2) protected by authenticated admin permission checks.
"""

import os
from unittest.mock import patch


def _get_client():
    """Create a TestClient for a minimal app with conditional debug mounting."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.routes import debug

    app = FastAPI()
    if debug.is_debug_routes_enabled():
        app.include_router(debug.router)
    return TestClient(app)


class TestDebugEnvStatus:
    """Tests for /debug/env-status endpoint."""

    def test_not_mounted_when_feature_flag_disabled(self):
        with patch.dict(os.environ, {"DEBUG_ROUTES_ENABLED": "false"}):
            client = _get_client()
            resp = client.get("/debug/env-status")
            assert resp.status_code == 404

    def test_requires_auth_when_feature_flag_enabled(self):
        with patch.dict(os.environ, {"DEBUG_ROUTES_ENABLED": "true"}):
            client = _get_client()
            resp = client.get("/debug/env-status")
            assert resp.status_code == 401

    def test_accessible_with_dependency_override(self):
        with patch.dict(os.environ, {"DEBUG_ROUTES_ENABLED": "true"}):
            client = _get_client()
            from src.api.routes import debug as debug_module
            try:
                client.app.dependency_overrides[debug_module.require_debug_admin_auth] = lambda: object()
                resp = client.get("/debug/env-status")
                assert resp.status_code == 200
            finally:
                client.app.dependency_overrides.clear()


class TestDebugAuthCheck:
    """Tests for /debug/auth-check endpoint."""

    def test_not_mounted_when_feature_flag_disabled(self):
        with patch.dict(os.environ, {"DEBUG_ROUTES_ENABLED": "false"}):
            client = _get_client()
            resp = client.get("/debug/auth-check")
            assert resp.status_code == 404

    def test_requires_auth_when_feature_flag_enabled(self):
        with patch.dict(os.environ, {"DEBUG_ROUTES_ENABLED": "true"}):
            client = _get_client()
            resp = client.get("/debug/auth-check")
            assert resp.status_code == 401
