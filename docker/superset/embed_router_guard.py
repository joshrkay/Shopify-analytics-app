"""
Chrome-less Embed Router Guard for Superset.

Flask before_request handler that restricts navigation to embed-safe routes only.
This prevents users from accessing Superset's native UI (SQL Lab, Explore,
profile pages, login, etc.) when Superset is used as an embedded analytics engine.

SECURITY PRINCIPLES:
- Default deny: only explicitly allowed routes pass through
- All blocked attempts are audit-logged as structured JSON
- No Superset chrome surfaces are accessible in embedded mode

Phase 3 - Chrome-less Embed
"""

import json
import logging
from datetime import datetime, timezone

from flask import request, jsonify

logger = logging.getLogger(__name__)


# =============================================================================
# Route Definitions
# =============================================================================

# Routes that are explicitly BLOCKED (return 403)
# These are Superset chrome/admin surfaces that must not be accessible in embed mode.
BLOCKED_ROUTE_PREFIXES = (
    "/superset/sqllab",
    "/superset/explore",
    "/api/v1/dataset/",
    "/api/v1/database/",
    "/superset/profile/",
    "/superset/welcome/",
    "/register/",
    "/login/",
)

# Routes that are explicitly ALLOWED (pass through to jwt_auth handler)
# These are required for embedded dashboard rendering and the Superset SDK.
ALLOWED_ROUTE_PREFIXES = (
    "/superset/dashboard/",
    "/api/v1/chart/",
    "/api/v1/dashboard/",
    "/api/v1/guest_token/",
    "/health",
    "/static/",
)


# =============================================================================
# Superset-side audit logging (same pattern as jwt_auth.py)
# =============================================================================

def _emit_superset_audit_log(action: str, outcome: str, **extra):
    """Emit structured audit log for Superset-side events.

    Logs as structured JSON for collection by log aggregator.
    The backend audit DB is not accessible from the Superset container.
    """
    audit_entry = {
        "audit_source": "superset",
        "action": action,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    audit_entry.update(extra)
    logger.info(
        "AUDIT_EVENT: %s",
        json.dumps(audit_entry),
        extra={"audit": audit_entry},
    )


# =============================================================================
# Guard Implementation
# =============================================================================

def _is_allowed_route(path: str) -> bool:
    """Check if a request path matches an allowed route prefix."""
    for prefix in ALLOWED_ROUTE_PREFIXES:
        if path.startswith(prefix):
            return True
    # Exact match for /health without trailing slash
    if path == "/health":
        return True
    return False


def _is_blocked_route(path: str) -> bool:
    """Check if a request path matches a blocked route prefix."""
    for prefix in BLOCKED_ROUTE_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def guard_embed_navigation():
    """Flask before_request handler that blocks non-embed routes.

    Registered in FLASK_APP_MUTATOR alongside the JWT auth handler.
    This guard runs BEFORE jwt_auth to short-circuit blocked navigation
    without requiring a valid token.

    Returns:
        None if request is allowed (continues to next handler).
        JSON 403 response if route is blocked.
    """
    path = request.path

    # Fast path: explicitly allowed routes pass through immediately
    if _is_allowed_route(path):
        return None

    # Explicitly blocked routes return 403
    if _is_blocked_route(path):
        logger.warning(
            "Embed navigation blocked",
            extra={
                "path": path,
                "method": request.method,
                "remote_addr": request.remote_addr,
            },
        )

        _emit_superset_audit_log(
            "embed.navigation_blocked",
            "denied",
            path=path,
            method=request.method,
            remote_addr=request.remote_addr,
        )

        response = jsonify({
            "error": "Navigation not allowed in embedded mode",
            "blocked_path": path,
        })
        response.status_code = 403
        return response

    # Routes not in either list: allow through (handled by jwt_auth deny-by-default)
    # This ensures new Superset API endpoints required for dashboard rendering
    # are not accidentally blocked. The JWT auth handler enforces auth on all
    # non-health/static routes anyway.
    return None
