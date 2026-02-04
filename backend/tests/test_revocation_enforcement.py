"""
Tests for authorization enforcement (DB-as-source-of-truth).

These tests verify that authorization changes are enforced immediately:
- Tenant access revoked → next request fails with 403
- Role changed → permissions reflect immediately
- Billing downgrade → invalid role blocked with BILLING_ROLE_NOT_ALLOWED

Story: Authorization Hardening - DB-as-source-of-truth checks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.services.tenant_guard import (
    TenantGuard,
    AuthorizationResult,
    ValidationResult,
    ViolationType,
)
from src.models.user import User
from src.models.tenant import Tenant, TenantStatus
from src.models.user_tenant_roles import UserTenantRole
from src.platform.audit import AuditAction


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def active_user():
    """Create an active user fixture."""
    user = Mock(spec=User)
    user.id = "user-123"
    user.clerk_user_id = "clerk_user_123"
    user.is_active = True
    user.email = "test@example.com"
    return user


@pytest.fixture
def inactive_user():
    """Create an inactive user fixture."""
    user = Mock(spec=User)
    user.id = "user-456"
    user.clerk_user_id = "clerk_user_456"
    user.is_active = False
    user.email = "inactive@example.com"
    return user


@pytest.fixture
def active_tenant():
    """Create an active tenant fixture."""
    tenant = Mock(spec=Tenant)
    tenant.id = "tenant-123"
    tenant.status = TenantStatus.ACTIVE
    tenant.billing_tier = "growth"
    tenant.name = "Test Store"
    return tenant


@pytest.fixture
def suspended_tenant():
    """Create a suspended tenant fixture."""
    tenant = Mock(spec=Tenant)
    tenant.id = "tenant-456"
    tenant.status = TenantStatus.SUSPENDED
    tenant.billing_tier = "growth"
    tenant.name = "Suspended Store"
    return tenant


@pytest.fixture
def free_tier_tenant():
    """Create a free tier tenant fixture."""
    tenant = Mock(spec=Tenant)
    tenant.id = "tenant-789"
    tenant.status = TenantStatus.ACTIVE
    tenant.billing_tier = "free"
    tenant.name = "Free Store"
    return tenant


@pytest.fixture
def merchant_admin_role():
    """Create a merchant_admin role fixture."""
    role = Mock(spec=UserTenantRole)
    role.id = "role-123"
    role.user_id = "user-123"
    role.tenant_id = "tenant-123"
    role.role = "merchant_admin"
    role.is_active = True
    return role


@pytest.fixture
def agency_admin_role():
    """Create an agency_admin role fixture."""
    role = Mock(spec=UserTenantRole)
    role.id = "role-456"
    role.user_id = "user-123"
    role.tenant_id = "tenant-123"
    role.role = "agency_admin"
    role.is_active = True
    return role


# =============================================================================
# Test: Tenant Access Revoked → Request Fails
# =============================================================================


class TestTenantAccessRevoked:
    """Tests for tenant access revocation enforcement."""

    def test_revoked_access_returns_403(self, mock_db, active_user, active_tenant):
        """
        When a user's tenant access is revoked, the next request should fail.

        Scenario:
        1. User has access to tenant-123
        2. Admin revokes user's access (deactivates UserTenantRole)
        3. User's next request to tenant-123 returns 403
        """
        # Setup: User exists but has no active roles for the tenant
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,  # User query
            active_tenant,  # Tenant query
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []  # No roles

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["merchant_admin"],  # JWT still has old roles
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "ACCESS_REVOKED"
        assert result.audit_action == AuditAction.IDENTITY_ACCESS_REVOKED_ENFORCED
        assert "tenant-123" in result.audit_metadata.get("tenant_id", "")

    def test_revoked_access_includes_previous_roles_in_audit(
        self, mock_db, active_user, active_tenant
    ):
        """Audit event should include the previous roles for tracking."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["merchant_admin", "billing_manager"],
            request_path="/api/data",
            request_method="GET",
        )

        assert result.previous_roles == ["merchant_admin", "billing_manager"]
        assert result.audit_metadata.get("previous_roles") == [
            "merchant_admin",
            "billing_manager",
        ]

    def test_user_not_found_returns_unauthorized(self, mock_db):
        """If user doesn't exist in local DB, return unauthorized."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="unknown_clerk_user",
            active_tenant_id="tenant-123",
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "USER_NOT_FOUND"

    def test_inactive_user_returns_unauthorized(self, mock_db, inactive_user):
        """If user is deactivated, return unauthorized."""
        mock_db.query.return_value.filter.return_value.first.return_value = inactive_user

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_456",
            active_tenant_id="tenant-123",
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "USER_INACTIVE"


# =============================================================================
# Test: Role Changed → Permissions Reflect Immediately
# =============================================================================


class TestRoleChangeEnforcement:
    """Tests for role change detection and enforcement."""

    def test_role_change_detected(
        self, mock_db, active_user, active_tenant, merchant_admin_role
    ):
        """
        When a user's role changes, the new role should be reflected immediately.

        Scenario:
        1. User's JWT says "agency_admin"
        2. DB says "merchant_admin" (role was changed)
        3. Response should use DB role, not JWT role
        """
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["agency_admin"],  # JWT has old role
            request_path="/api/data",
            request_method="GET",
        )

        assert result.is_authorized
        assert result.roles == ["merchant_admin"]  # DB role used
        assert result.roles_changed is True
        assert result.previous_roles == ["agency_admin"]

    def test_role_change_emits_audit_event(
        self, mock_db, active_user, active_tenant, merchant_admin_role
    ):
        """Role changes should emit an audit event for tracking."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["agency_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        assert result.audit_action == AuditAction.IDENTITY_ROLE_CHANGE_ENFORCED
        assert result.audit_metadata.get("previous_roles") == ["agency_admin"]
        assert result.audit_metadata.get("new_roles") == ["merchant_admin"]

    def test_no_role_change_when_roles_match(
        self, mock_db, active_user, active_tenant, merchant_admin_role
    ):
        """No audit event when roles haven't changed."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["merchant_admin"],  # Matches DB
            request_path="/api/data",
            request_method="GET",
        )

        assert result.is_authorized
        assert result.roles_changed is False
        assert result.audit_action is None


# =============================================================================
# Test: Billing Downgrade → Invalid Role Blocked
# =============================================================================


class TestBillingDowngradeEnforcement:
    """Tests for billing tier role validation."""

    def test_agency_role_blocked_on_free_tier(
        self, mock_db, active_user, free_tier_tenant, agency_admin_role
    ):
        """
        Agency roles require paid tier. Free tier should block agency_admin.

        Scenario:
        1. Tenant downgrades from Growth to Free
        2. User has agency_admin role
        3. Request should fail with BILLING_ROLE_NOT_ALLOWED
        """
        agency_admin_role.tenant_id = "tenant-789"
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            free_tier_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            agency_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-789",
            jwt_roles=["agency_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "BILLING_ROLE_NOT_ALLOWED"
        assert result.audit_action == AuditAction.BILLING_ROLE_REVOKED_DUE_TO_DOWNGRADE
        assert result.billing_tier == "free"

    def test_merchant_role_allowed_on_free_tier(
        self, mock_db, active_user, free_tier_tenant, merchant_admin_role
    ):
        """Merchant roles should work on free tier."""
        merchant_admin_role.tenant_id = "tenant-789"
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            free_tier_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-789",
            jwt_roles=["merchant_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        assert result.is_authorized
        assert result.roles == ["merchant_admin"]

    def test_billing_downgrade_includes_allowed_roles(
        self, mock_db, active_user, free_tier_tenant, agency_admin_role
    ):
        """Error response should include which roles are allowed for the tier."""
        agency_admin_role.tenant_id = "tenant-789"
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            free_tier_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            agency_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-789",
            jwt_roles=["agency_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        assert "allowed_roles" in result.audit_metadata
        allowed = result.audit_metadata["allowed_roles"]
        assert "merchant_admin" in allowed
        assert "merchant_viewer" in allowed

    def test_mixed_roles_filters_to_valid_only(self, mock_db, active_user, free_tier_tenant):
        """If user has both valid and invalid roles, only valid roles are used."""
        # Create both roles
        merchant_role = Mock(spec=UserTenantRole)
        merchant_role.role = "merchant_admin"
        merchant_role.is_active = True

        agency_role = Mock(spec=UserTenantRole)
        agency_role.role = "agency_admin"
        agency_role.is_active = True

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            free_tier_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_role,
            agency_role,
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-789",
            jwt_roles=["agency_admin", "merchant_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        # Should be authorized with only the valid role
        assert result.is_authorized
        assert "merchant_admin" in result.roles
        assert "agency_admin" not in result.roles


# =============================================================================
# Test: Tenant Suspended → Access Denied
# =============================================================================


class TestTenantSuspensionEnforcement:
    """Tests for tenant status enforcement."""

    def test_suspended_tenant_returns_403(
        self, mock_db, active_user, suspended_tenant, merchant_admin_role
    ):
        """Suspended tenant should block all access."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            suspended_tenant,
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-456",
            jwt_roles=["merchant_admin"],
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "TENANT_SUSPENDED"
        assert result.audit_action == AuditAction.IDENTITY_ACCESS_REVOKED_ENFORCED

    def test_tenant_not_found_returns_error(self, mock_db, active_user):
        """Non-existent tenant should return error."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            None,  # Tenant not found
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="nonexistent-tenant",
            request_path="/api/data",
            request_method="GET",
        )

        assert not result.is_authorized
        assert result.error_code == "TENANT_NOT_FOUND"


# =============================================================================
# Test: Concurrency and Race Conditions
# =============================================================================


class TestConcurrencyHandling:
    """Tests for concurrent request handling during revocation."""

    def test_concurrent_requests_during_revocation(
        self, mock_db, active_user, active_tenant
    ):
        """
        If user changes tenant while revocation happens, enforcement still works.

        This test verifies that each request gets a fresh DB check.
        """
        # First request: user still has access
        merchant_role = Mock(spec=UserTenantRole)
        merchant_role.role = "merchant_admin"
        merchant_role.is_active = True

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [merchant_role]

        guard = TenantGuard(mock_db)
        result1 = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            request_path="/api/data",
            request_method="GET",
        )
        assert result1.is_authorized

        # Second request: access revoked
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []  # Revoked

        result2 = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            request_path="/api/data",
            request_method="GET",
        )
        assert not result2.is_authorized
        assert result2.error_code == "ACCESS_REVOKED"


# =============================================================================
# Test: Audit Event Emission
# =============================================================================


class TestAuditEventEmission:
    """Tests for audit event emission on enforcement actions."""

    def test_emit_enforcement_audit_event(self, mock_db, active_user, active_tenant):
        """Test that emit_enforcement_audit_event writes to DB."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            request_path="/api/data",
            request_method="GET",
        )

        # Create mock request
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"user-agent": "test-agent"}

        # Mock the write_audit_log_sync function
        with patch("src.services.tenant_guard.write_audit_log_sync") as mock_write:
            guard.emit_enforcement_audit_event(mock_request, result)
            mock_write.assert_called_once()
            call_args = mock_write.call_args
            audit_event = call_args[0][1]  # Second positional arg is the event
            assert audit_event.action == AuditAction.IDENTITY_ACCESS_REVOKED_ENFORCED

    def test_no_audit_event_for_successful_auth(
        self, mock_db, active_user, active_tenant, merchant_admin_role
    ):
        """No audit event should be emitted for normal successful auth."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            active_user,
            active_tenant,
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            merchant_admin_role
        ]

        guard = TenantGuard(mock_db)
        result = guard.enforce_authorization(
            clerk_user_id="clerk_user_123",
            active_tenant_id="tenant-123",
            jwt_roles=["merchant_admin"],  # Matches DB
            request_path="/api/data",
            request_method="GET",
        )

        assert result.is_authorized
        assert result.audit_action is None  # No audit event needed


# =============================================================================
# Integration Test: Full Middleware Flow
# =============================================================================


class TestMiddlewareIntegration:
    """Integration tests for the full middleware flow."""

    @pytest.mark.asyncio
    async def test_middleware_blocks_revoked_access(self):
        """
        Test that TenantContextMiddleware blocks revoked access.

        This is a higher-level test that verifies the middleware integration.
        """
        # This would require a full FastAPI test client setup
        # For now, we mark it as a placeholder for integration testing
        pass

    @pytest.mark.asyncio
    async def test_middleware_updates_tenant_context_with_db_roles(self):
        """
        Test that middleware updates TenantContext with DB-verified roles.
        """
        # Placeholder for integration test
        pass
