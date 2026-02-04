"""
Shared pytest fixtures for platform tests.

These fixtures are automatically available to all tests in the platform directory.
"""

import pytest
from unittest.mock import MagicMock, patch


# ============================================================================
# MOCK AUTHORIZATION HELPERS
# ============================================================================

def create_mock_authz_result(is_authorized=True, roles=None, tenant_id=None, user_id=None):
    """Create a mock AuthorizationResult for testing.

    Note: roles defaults to None so that the JWT roles are used in the tenant
    context instead of being overridden by the mock.
    """
    from src.services.tenant_guard import AuthorizationResult
    return AuthorizationResult(
        is_authorized=is_authorized,
        user_id=user_id or "test-user-id",
        tenant_id=tenant_id,
        roles=roles,  # None by default - uses JWT roles
        billing_tier="pro",
        denial_reason=None if is_authorized else "Access denied",
        error_code=None if is_authorized else "ACCESS_DENIED",
        roles_changed=False,
        previous_roles=[],
        audit_action=None,
        audit_metadata={},
    )


@pytest.fixture(autouse=True)
def mock_authorization_enforcement():
    """Mock TenantGuard.enforce_authorization to skip DB checks in tests.

    This fixture is automatically applied to all tests in the platform directory.
    It prevents the TenantContextMiddleware from making actual database calls
    during authorization enforcement.
    """
    # Reset the global TenantGuard class cache to ensure mock is used
    import src.platform.tenant_context as tenant_context_module
    original_class = tenant_context_module._tenant_guard_class
    tenant_context_module._tenant_guard_class = None

    # Create mock guard instance
    mock_guard = MagicMock()
    mock_guard.enforce_authorization.return_value = create_mock_authz_result()
    mock_guard.emit_enforcement_audit_event.return_value = None

    # Create a mock TenantGuard class that returns our mock guard instance
    mock_tenant_guard_class = MagicMock(return_value=mock_guard)

    # Patch _get_tenant_guard_class to return our mock class
    with patch('src.platform.tenant_context._get_tenant_guard_class', return_value=mock_tenant_guard_class):
        # Also patch the database session to prevent any DB calls
        # Use side_effect to return a fresh generator for each call
        with patch('src.platform.tenant_context.get_db_session_sync') as mock_db:
            mock_session = MagicMock()
            # side_effect with a callable creates a fresh iterator for each call
            mock_db.side_effect = lambda: iter([mock_session])
            yield mock_guard

    # Restore original class cache
    tenant_context_module._tenant_guard_class = original_class
