"""
Shared fixtures for integration tests.

Provides:
- dbt_absent_client: TestClient where every DB execute() raises ProgrammingError,
  simulating a fresh deploy where dbt tables (canonical.*, analytics.*, etc.) do
  not yet exist.  Used by test_graceful_degradation.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

TEST_TENANT_ID = "test-tenant-degradation-001"
TEST_USER_ID = "test-user-degradation-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_programmatic_error(*args, **kwargs):
    """Raise ProgrammingError simulating a missing dbt table."""
    raise ProgrammingError(
        statement="SELECT ... FROM canonical.orders ...",
        params={},
        orig=Exception('ERROR: relation "canonical.orders" does not exist'),
    )


def _make_test_tenant_context():
    """Return a MagicMock that satisfies all TenantContext attribute reads."""
    ctx = MagicMock()
    ctx.tenant_id = TEST_TENANT_ID
    ctx.user_id = TEST_USER_ID
    ctx.roles = ["admin"]
    ctx.billing_tier = "pro"
    ctx.is_agency_user = False
    ctx.allowed_tenants = [TEST_TENANT_ID]
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dbt_absent_client():
    """
    A TestClient configured to simulate missing dbt-managed tables.

    Behaviour:
      - Injects a valid TenantContext into every request (bypasses JWT/Clerk auth).
      - Mocks every DB session so that session.execute() raises ProgrammingError,
        exactly as it would when canonical.orders / marts.* / analytics.* are absent.

    Routes under test should catch this and return HTTP 503, not HTTP 500.
    The client is module-scoped for speed (setup/teardown once per test module).
    """
    from src.api.routes import channels, orders, attribution

    app = FastAPI()

    # ── Tenant context injector ─────────────────────────────────────────────
    # Sets request.state.tenant_context before any route handler runs.
    # get_tenant_context(request) reads from request.state, so this bypasses
    # all JWT/Clerk infrastructure.
    @app.middleware("http")
    async def inject_tenant_context(request: Request, call_next):
        request.state.tenant_context = _make_test_tenant_context()
        return await call_next(request)

    app.include_router(channels.router)
    app.include_router(orders.router)
    app.include_router(attribution.router)

    # ── DB session mock ─────────────────────────────────────────────────────
    # Build a mock session whose execute() always raises ProgrammingError.
    mock_session = MagicMock()
    mock_session.execute.side_effect = _make_programmatic_error
    mock_session.close = MagicMock()

    # Both patterns routes use to open sessions:
    #   channels.py:    db = get_session_factory()()
    #   orders.py:      from src.database.session import SessionLocal; db = SessionLocal()
    #   attribution.py: from src.database.session import SessionLocal; db = SessionLocal()
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_session_class = MagicMock(return_value=mock_session)

    patches = [
        # channels.py imports get_session_factory at module scope
        patch("src.api.routes.channels.get_session_factory", return_value=mock_session_factory),
        # orders.py and attribution.py import SessionLocal inside functions
        patch("src.database.session.SessionLocal", mock_session_class),
        # Belt-and-suspenders: also patch at the top-level session module
        patch("src.database.session.get_session_factory", return_value=mock_session_factory),
    ]

    with (
        patches[0],
        patches[1],
        patches[2],
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
