"""
Tests for tenant selection feature.

Tests cover:
- Single-tenant auto-selection
- Multi-tenant requires selection (409 TENANT_SELECTION_REQUIRED)
- Tampered tenant_id rejected
- Setting active tenant
- Audit events on invalid access
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException

from src.services.tenant_selection_service import (
    TenantSelectionService,
    TenantAccessDeniedError,
    TenantNotFoundError,
    NoTenantAccessError,
    TenantSelectionRequiredError,
)
from src.platform.tenant_context import (
    TenantSelectionRequiredException,
    NoTenantAccessException,
    TenantViolationType,
)
from src.models.user import User
from src.models.tenant import Tenant, TenantStatus
from src.models.user_tenant_roles import UserTenantRole
from src.platform.audit import AuditAction


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock(spec=Session)
    session.add = MagicMock()
    session.commit = MagicMock()
    session.flush = MagicMock()
    session.rollback = MagicMock()
    return session


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock(spec=User)
    user.id = "user_internal_123"
    user.clerk_user_id = "clerk_user_abc"
    user.is_active = True
    user.extra_metadata = {}
    return user


@pytest.fixture
def mock_tenant_1():
    """Create a mock tenant."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = "tenant_1"
    tenant.name = "Tenant One"
    tenant.slug = "tenant-one"
    tenant.billing_tier = "free"
    tenant.status = TenantStatus.ACTIVE
    return tenant


@pytest.fixture
def mock_tenant_2():
    """Create a mock tenant."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = "tenant_2"
    tenant.name = "Tenant Two"
    tenant.slug = "tenant-two"
    tenant.billing_tier = "growth"
    tenant.status = TenantStatus.ACTIVE
    return tenant


@pytest.fixture
def mock_role_1(mock_user, mock_tenant_1):
    """Create a mock user-tenant role."""
    role = MagicMock(spec=UserTenantRole)
    role.id = "role_1"
    role.user_id = mock_user.id
    role.tenant_id = mock_tenant_1.id
    role.role = "MERCHANT_ADMIN"
    role.is_active = True
    role.tenant = mock_tenant_1
    role.is_admin_role = True
    return role


@pytest.fixture
def mock_role_2(mock_user, mock_tenant_2):
    """Create a mock user-tenant role."""
    role = MagicMock(spec=UserTenantRole)
    role.id = "role_2"
    role.user_id = mock_user.id
    role.tenant_id = mock_tenant_2.id
    role.role = "MERCHANT_VIEWER"
    role.is_active = True
    role.tenant = mock_tenant_2
    role.is_admin_role = False
    return role


# =============================================================================
# Test Suite: Single Tenant Auto-Selection
# =============================================================================

class TestSingleTenantAutoSelection:
    """Test auto-selection when user has exactly one tenant."""

    def test_single_tenant_auto_selects(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_role_1,
    ):
        """User with single tenant should auto-select that tenant."""
        # Setup: User has exactly 1 tenant
        # resolve_active_tenant calls _get_user 3 times:
        # 1. In resolve_active_tenant itself
        # 2. In get_user_tenants
        # 3. In get_active_tenant_id
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # resolve_active_tenant._get_user
            mock_user,  # get_user_tenants._get_user
            mock_user,  # get_active_tenant_id._get_user
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            tenant_id, was_auto = service.resolve_active_tenant(
                clerk_user_id="clerk_user_abc",
                jwt_active_tenant_id=None,
            )

        assert tenant_id == "tenant_1"
        assert was_auto is True

    def test_single_tenant_stored_in_metadata(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_role_1,
    ):
        """Auto-selection should store the tenant in user metadata."""
        mock_user.extra_metadata = {}

        # resolve_active_tenant calls _get_user 3 times
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # resolve_active_tenant._get_user
            mock_user,  # get_user_tenants._get_user
            mock_user,  # get_active_tenant_id._get_user
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            service.resolve_active_tenant(
                clerk_user_id="clerk_user_abc",
            )

        # Verify metadata was updated
        assert mock_user.extra_metadata.get("active_tenant_id") == "tenant_1"
        mock_db_session.flush.assert_called()


# =============================================================================
# Test Suite: Multi-Tenant Requires Selection
# =============================================================================

class TestMultiTenantRequiresSelection:
    """Test that multi-tenant users without selection get 409."""

    def test_multi_tenant_no_selection_raises(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_tenant_2,
        mock_role_1,
        mock_role_2,
    ):
        """User with multiple tenants and no selection should raise error."""
        # Setup: User has 2 tenants, no active selection
        mock_user.extra_metadata = {}

        # resolve_active_tenant calls _get_user 3 times
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # resolve_active_tenant._get_user
            mock_user,  # get_user_tenants._get_user
            mock_user,  # get_active_tenant_id._get_user
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1,
            mock_role_2,
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantSelectionRequiredError) as exc_info:
                service.resolve_active_tenant(
                    clerk_user_id="clerk_user_abc",
                )

        assert "2 tenants" in str(exc_info.value)

    def test_multi_tenant_with_stored_selection_succeeds(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_tenant_2,
        mock_role_1,
        mock_role_2,
    ):
        """User with multiple tenants and stored selection should succeed."""
        # Setup: User has 2 tenants with active selection
        mock_user.extra_metadata = {"active_tenant_id": "tenant_2"}

        # resolve_active_tenant calls _get_user 3 times
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # resolve_active_tenant._get_user
            mock_user,  # get_user_tenants._get_user
            mock_user,  # get_active_tenant_id._get_user
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1,
            mock_role_2,
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            tenant_id, was_auto = service.resolve_active_tenant(
                clerk_user_id="clerk_user_abc",
            )

        assert tenant_id == "tenant_2"
        assert was_auto is False

    def test_multi_tenant_with_jwt_selection_succeeds(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_tenant_2,
        mock_role_1,
        mock_role_2,
    ):
        """User with multiple tenants and JWT selection should succeed."""
        mock_user.extra_metadata = {}

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            mock_tenant_1,
            mock_tenant_2,
        ]
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1,
            mock_role_2,
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            tenant_id, was_auto = service.resolve_active_tenant(
                clerk_user_id="clerk_user_abc",
                jwt_active_tenant_id="tenant_1",
            )

        assert tenant_id == "tenant_1"
        assert was_auto is False


# =============================================================================
# Test Suite: Tampered Tenant ID Rejected
# =============================================================================

class TestTamperedTenantIdRejected:
    """Test that tampered/invalid tenant IDs are rejected with audit."""

    def test_invalid_tenant_id_raises_not_found(
        self,
        mock_db_session,
        mock_user,
    ):
        """Setting active tenant with non-existent ID should raise error."""
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # User query
            None,  # Tenant query - not found
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantNotFoundError):
                service.set_active_tenant(
                    clerk_user_id="clerk_user_abc",
                    tenant_id="fake_tenant_id",
                )

            # Verify audit event was emitted
            mock_audit.assert_called_once()
            event = mock_audit.call_args[0][1]
            assert event.action == AuditAction.AUTH_CROSS_TENANT_ACCESS_ATTEMPT
            assert event.outcome.value == "denied"

    def test_unauthorized_tenant_id_raises_access_denied(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_2,
    ):
        """Setting active tenant without access should raise error."""
        # User exists, tenant exists, but no role linking them
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,  # User query
            mock_tenant_2,  # Tenant query
            None,  # UserTenantRole query - no access
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantAccessDeniedError):
                service.set_active_tenant(
                    clerk_user_id="clerk_user_abc",
                    tenant_id="tenant_2",
                )

            # Verify audit event was emitted
            mock_audit.assert_called_once()
            event = mock_audit.call_args[0][1]
            assert event.action == AuditAction.AUTH_CROSS_TENANT_ACCESS_ATTEMPT
            assert event.metadata["reason"] == "no_access"

    def test_inactive_tenant_rejected(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_2,
    ):
        """Setting active tenant that is inactive should raise error."""
        mock_tenant_2.status = TenantStatus.DEACTIVATED

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            mock_tenant_2,
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantAccessDeniedError):
                service.set_active_tenant(
                    clerk_user_id="clerk_user_abc",
                    tenant_id="tenant_2",
                )

            # Verify audit event was emitted with correct reason
            mock_audit.assert_called_once()
            event = mock_audit.call_args[0][1]
            assert event.metadata["reason"] == "tenant_inactive"

    def test_validate_tenant_access_emits_audit_on_failure(
        self,
        mock_db_session,
        mock_user,
    ):
        """Validating access to unauthorized tenant should emit audit."""
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            None,  # No role
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            result = service.validate_tenant_access(
                clerk_user_id="clerk_user_abc",
                tenant_id="unauthorized_tenant",
                ip_address="192.168.1.1",
                user_agent="Test Browser",
            )

        assert result is False
        mock_audit.assert_called_once()
        event = mock_audit.call_args[0][1]
        assert event.action == AuditAction.AUTH_CROSS_TENANT_ACCESS_ATTEMPT
        assert event.ip_address == "192.168.1.1"


# =============================================================================
# Test Suite: Set Active Tenant
# =============================================================================

class TestSetActiveTenant:
    """Test setting active tenant."""

    def test_set_active_tenant_success(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_role_1,
    ):
        """Successfully setting active tenant."""
        mock_user.extra_metadata = {}

        # set_active_tenant calls .first() 4 times:
        # 1. _get_user for user lookup
        # 2. Tenant query
        # 3. UserTenantRole query for access check
        # 4. get_active_tenant_id._get_user for previous tenant
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,     # _get_user
            mock_tenant_1, # Tenant query
            mock_role_1,   # UserTenantRole (has access)
            mock_user,     # get_active_tenant_id._get_user
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            result = service.set_active_tenant(
                clerk_user_id="clerk_user_abc",
                tenant_id="tenant_1",
            )

        assert result["tenant_id"] == "tenant_1"
        assert result["name"] == "Tenant One"
        assert mock_user.extra_metadata["active_tenant_id"] == "tenant_1"

    def test_set_active_tenant_emits_success_audit(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_role_1,
    ):
        """Setting active tenant should emit success audit event."""
        mock_user.extra_metadata = {"active_tenant_id": "old_tenant"}

        # set_active_tenant calls .first() 4 times:
        # 1. _get_user for user lookup
        # 2. Tenant query
        # 3. UserTenantRole query for access check
        # 4. get_active_tenant_id._get_user for previous tenant
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,     # _get_user
            mock_tenant_1, # Tenant query
            mock_role_1,   # UserTenantRole (has access)
            mock_user,     # get_active_tenant_id._get_user
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            service.set_active_tenant(
                clerk_user_id="clerk_user_abc",
                tenant_id="tenant_1",
            )

            # Verify success audit event
            assert mock_audit.call_count == 1
            event = mock_audit.call_args[0][1]
            assert event.action == AuditAction.AUTH_TENANT_SELECTED
            assert event.outcome.value == "success"
            assert event.metadata["previous_tenant_id"] == "old_tenant"


# =============================================================================
# Test Suite: Get User Tenants
# =============================================================================

class TestGetUserTenants:
    """Test getting list of user's tenants."""

    def test_get_user_tenants_returns_all(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_tenant_2,
        mock_role_1,
        mock_role_2,
    ):
        """Get all tenants user has access to."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1,
            mock_role_2,
        ]

        service = TenantSelectionService(mock_db_session)
        tenants = service.get_user_tenants("clerk_user_abc")

        assert len(tenants) == 2
        tenant_ids = [t["id"] for t in tenants]
        assert "tenant_1" in tenant_ids
        assert "tenant_2" in tenant_ids

    def test_get_user_tenants_excludes_inactive(
        self,
        mock_db_session,
        mock_user,
        mock_tenant_1,
        mock_tenant_2,
        mock_role_1,
        mock_role_2,
    ):
        """Inactive tenants should be excluded."""
        mock_tenant_2.status = TenantStatus.DEACTIVATED

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db_session.query.return_value.filter.return_value.all.return_value = [
            mock_role_1,
            mock_role_2,
        ]

        service = TenantSelectionService(mock_db_session)
        tenants = service.get_user_tenants("clerk_user_abc")

        assert len(tenants) == 1
        assert tenants[0]["id"] == "tenant_1"

    def test_get_user_tenants_empty_for_unknown_user(
        self,
        mock_db_session,
    ):
        """Unknown user should return empty list."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        service = TenantSelectionService(mock_db_session)
        tenants = service.get_user_tenants("unknown_user")

        assert tenants == []


# =============================================================================
# Test Suite: No Tenant Access
# =============================================================================

class TestNoTenantAccess:
    """Test handling of users with no tenant access."""

    def test_resolve_raises_no_access(
        self,
        mock_db_session,
        mock_user,
    ):
        """User with no tenant roles should raise NoTenantAccessError."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        with patch('src.services.tenant_selection_service.write_audit_log_sync'):
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(NoTenantAccessError):
                service.resolve_active_tenant(
                    clerk_user_id="clerk_user_abc",
                )


# =============================================================================
# Test Suite: Middleware Exceptions
# =============================================================================

class TestMiddlewareExceptions:
    """Test the custom exceptions used by middleware."""

    def test_tenant_selection_required_exception(self):
        """TenantSelectionRequiredException should have tenant_count."""
        exc = TenantSelectionRequiredException(
            "User has 3 tenants",
            tenant_count=3,
        )

        assert exc.tenant_count == 3
        assert "3 tenants" in str(exc)

    def test_no_tenant_access_exception(self):
        """NoTenantAccessException basic test."""
        exc = NoTenantAccessException("No access")
        assert str(exc) == "No access"


# =============================================================================
# Test Suite: Audit Event Metadata
# =============================================================================

class TestAuditEventMetadata:
    """Test that audit events have correct metadata."""

    def test_cross_tenant_attempt_includes_ip(
        self,
        mock_db_session,
        mock_user,
    ):
        """Cross-tenant attempt audit should include IP address."""
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            None,  # Tenant not found
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantNotFoundError):
                service.set_active_tenant(
                    clerk_user_id="clerk_user_abc",
                    tenant_id="bad_tenant",
                    ip_address="10.0.0.1",
                    user_agent="Mozilla/5.0",
                )

            event = mock_audit.call_args[0][1]
            assert event.ip_address == "10.0.0.1"
            assert event.user_agent == "Mozilla/5.0"
            assert event.correlation_id is not None

    def test_audit_never_includes_pii(
        self,
        mock_db_session,
        mock_user,
    ):
        """Audit events should never include PII like email."""
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_user,
            None,
        ]

        with patch('src.services.tenant_selection_service.write_audit_log_sync') as mock_audit:
            service = TenantSelectionService(mock_db_session)

            with pytest.raises(TenantNotFoundError):
                service.set_active_tenant(
                    clerk_user_id="clerk_user_abc",
                    tenant_id="bad_tenant",
                )

            event = mock_audit.call_args[0][1]
            metadata = event.metadata

            # Check no PII fields
            pii_fields = ["email", "phone", "name", "password"]
            for field in pii_fields:
                assert field not in metadata

            # Check clerk_user_id is present (not PII)
            assert "clerk_user_id" in metadata
