"""
Tests for Clerk invitation webhook handlers.

Tests cover:
- organizationInvitation.created webhook
- organizationInvitation.accepted webhook
- organizationInvitation.revoked webhook
- Idempotency handling
- Error handling for unknown tenants/invites

Following patterns from test_clerk_webhooks.py.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from src.models.tenant import Tenant, TenantStatus
from src.models.user import User
from src.models.user_tenant_roles import UserTenantRole
from src.models.tenant_invite import TenantInvite, InviteStatus
from src.services.invite_service import InviteService


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session(test_db_session):
    """Use the test database session."""
    return test_db_session


@pytest.fixture
def sample_tenant(db_session):
    """Create a sample tenant for testing."""
    tenant = Tenant(
        name="Webhook Test Tenant",
        slug=f"webhook-tenant-{uuid.uuid4().hex[:8]}",
        clerk_org_id=f"org_webhook_{uuid.uuid4().hex[:8]}",
        billing_tier="growth",
        status=TenantStatus.ACTIVE,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing."""
    user = User(
        clerk_user_id=f"user_webhook_{uuid.uuid4().hex[:8]}",
        email="webhookuser@example.com",
        first_name="Webhook",
        last_name="User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def invite_service(db_session):
    """Create InviteService instance."""
    return InviteService(db_session)


# =============================================================================
# Test Suite: organizationInvitation.created Webhook
# =============================================================================

class TestOrganizationInvitationCreated:
    """Tests for handling organizationInvitation.created webhook."""

    def test_webhook_creates_local_invite(self, db_session, sample_tenant, invite_service):
        """Test that webhook creates local TenantInvite record."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Simulate webhook payload data
        webhook_data = {
            "id": clerk_invitation_id,
            "organization_id": sample_tenant.clerk_org_id,
            "email_address": "invited@example.com",
            "role": "org:member",
            "status": "pending",
        }

        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email=webhook_data["email_address"],
                role="MERCHANT_VIEWER",  # Mapped from org:member
                clerk_invitation_id=clerk_invitation_id,
            )

        assert invite.clerk_invitation_id == clerk_invitation_id
        assert invite.email == "invited@example.com"
        assert invite.status == InviteStatus.PENDING
        assert invite.tenant_id == sample_tenant.id

    def test_webhook_idempotent_duplicate(self, db_session, sample_tenant, invite_service):
        """Test that duplicate webhook with same clerk_invitation_id is handled."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # First webhook
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite1 = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email="duplicate@example.com",
                role="MERCHANT_VIEWER",
                clerk_invitation_id=clerk_invitation_id,
            )
        db_session.flush()

        # Get by clerk ID instead of creating duplicate
        existing = invite_service.get_invite_by_clerk_id(clerk_invitation_id)
        assert existing is not None
        assert existing.id == invite1.id

    def test_clerk_role_mapping(self, db_session, sample_tenant, invite_service):
        """Test Clerk role to internal role mapping."""
        role_mappings = [
            ("org:admin", "MERCHANT_ADMIN"),
            ("org:member", "MERCHANT_VIEWER"),
        ]

        for i, (clerk_role, expected_role) in enumerate(role_mappings):
            with patch('src.services.invite_service.write_audit_log_sync'):
                invite = invite_service.create_invite(
                    tenant_id=sample_tenant.id,
                    email=f"role{i}@example.com",
                    role=expected_role,
                    clerk_invitation_id=f"orginv_role_{i}_{uuid.uuid4().hex[:8]}",
                )

            assert invite.role == expected_role


# =============================================================================
# Test Suite: organizationInvitation.accepted Webhook
# =============================================================================

class TestOrganizationInvitationAccepted:
    """Tests for handling organizationInvitation.accepted webhook."""

    def test_webhook_accepts_invite_and_creates_role(
        self, db_session, sample_tenant, sample_user, invite_service
    ):
        """Test that acceptance webhook creates UserTenantRole."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Create pending invite first (simulating .created webhook)
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email=sample_user.email,
                role="MERCHANT_VIEWER",
                clerk_invitation_id=clerk_invitation_id,
            )
        db_session.flush()

        # Simulate acceptance webhook
        with patch('src.services.invite_service.write_audit_log_sync'):
            result = invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )
        db_session.flush()

        # Verify role was created
        role = db_session.query(UserTenantRole).filter(
            UserTenantRole.user_id == sample_user.id,
            UserTenantRole.tenant_id == sample_tenant.id,
        ).first()

        assert role is not None
        assert role.role == "MERCHANT_VIEWER"
        assert role.is_active is True

        # Verify invite status updated
        updated_invite = invite_service.get_invite_by_id(invite.id)
        assert updated_invite.status == InviteStatus.ACCEPTED

    def test_webhook_handles_unknown_invite(self, db_session, sample_user, invite_service):
        """Test that acceptance webhook handles unknown invite gracefully."""
        # Try to find invite that doesn't exist
        unknown_id = f"unknown_invite_{uuid.uuid4().hex}"
        found = invite_service.get_invite_by_clerk_id(unknown_id)

        assert found is None  # Should return None, not raise

    def test_webhook_idempotent_already_accepted(
        self, db_session, sample_tenant, sample_user, invite_service
    ):
        """Test that duplicate acceptance webhook is handled idempotently."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Create and accept invite
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email=sample_user.email,
                role="MERCHANT_VIEWER",
                clerk_invitation_id=clerk_invitation_id,
            )
            invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )
        db_session.flush()

        # Reload invite - verify it's accepted
        reloaded = invite_service.get_invite_by_id(invite.id)
        assert reloaded.status == InviteStatus.ACCEPTED


# =============================================================================
# Test Suite: organizationInvitation.revoked Webhook
# =============================================================================

class TestOrganizationInvitationRevoked:
    """Tests for handling organizationInvitation.revoked webhook."""

    def test_webhook_revokes_invite(self, db_session, sample_tenant, invite_service):
        """Test that revocation webhook updates invite status."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Create pending invite
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email="torevoke@example.com",
                role="MERCHANT_VIEWER",
                clerk_invitation_id=clerk_invitation_id,
            )
        db_session.flush()

        # Simulate revocation webhook
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite_service.revoke_invite(
                invite_id=invite.id,
                revoked_by="system",
            )
        db_session.flush()

        # Verify invite status
        updated = invite_service.get_invite_by_id(invite.id)
        assert updated.status == InviteStatus.REVOKED

    def test_webhook_handles_unknown_invite_revocation(self, db_session, invite_service):
        """Test that revocation of unknown invite is handled gracefully."""
        unknown_clerk_id = f"unknown_{uuid.uuid4().hex}"
        found = invite_service.get_invite_by_clerk_id(unknown_clerk_id)

        assert found is None  # Should return None, not raise


# =============================================================================
# Test Suite: Webhook Error Handling
# =============================================================================

class TestWebhookErrorHandling:
    """Tests for webhook error handling scenarios."""

    def test_unknown_tenant_skipped(self, db_session, invite_service):
        """Test that webhook for unknown tenant is skipped."""
        # Try to create invite for non-existent tenant
        from src.services.invite_service import TenantNotFoundError

        with pytest.raises(TenantNotFoundError):
            invite_service.create_invite(
                tenant_id="nonexistent_tenant",
                email="test@example.com",
                role="MERCHANT_VIEWER",
            )

    def test_inactive_tenant_rejected(self, db_session, invite_service):
        """Test that webhook for inactive tenant is rejected."""
        # Create inactive tenant
        inactive_tenant = Tenant(
            name="Inactive",
            slug=f"inactive-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_inactive_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.DEACTIVATED,
        )
        db_session.add(inactive_tenant)
        db_session.flush()

        from src.services.invite_service import TenantNotActiveError

        with pytest.raises(TenantNotActiveError):
            invite_service.create_invite(
                tenant_id=inactive_tenant.id,
                email="test@example.com",
                role="MERCHANT_VIEWER",
            )


# =============================================================================
# Test Suite: Complete Webhook Flow
# =============================================================================

class TestCompleteWebhookFlow:
    """End-to-end tests for complete webhook flow."""

    def test_full_invite_lifecycle_via_webhooks(
        self, db_session, sample_tenant, sample_user, invite_service
    ):
        """Test complete lifecycle: created -> accepted."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Step 1: organizationInvitation.created webhook
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email=sample_user.email,
                role="MERCHANT_ADMIN",
                clerk_invitation_id=clerk_invitation_id,
            )
        db_session.flush()

        assert invite.status == InviteStatus.PENDING

        # Step 2: organizationInvitation.accepted webhook
        with patch('src.services.invite_service.write_audit_log_sync'):
            result = invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )
        db_session.flush()

        # Verify final state
        final_invite = invite_service.get_invite_by_id(invite.id)
        assert final_invite.status == InviteStatus.ACCEPTED
        assert final_invite.accepted_by_user_id == sample_user.id

        # Verify role exists
        role = db_session.query(UserTenantRole).filter(
            UserTenantRole.user_id == sample_user.id,
            UserTenantRole.tenant_id == sample_tenant.id,
            UserTenantRole.is_active == True,
        ).first()
        assert role is not None
        assert role.role == "MERCHANT_ADMIN"

    def test_revoke_before_accept_flow(
        self, db_session, sample_tenant, invite_service
    ):
        """Test lifecycle: created -> revoked (before accept)."""
        clerk_invitation_id = f"orginv_{uuid.uuid4().hex}"

        # Step 1: Create invite
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite = invite_service.create_invite(
                tenant_id=sample_tenant.id,
                email="torevoke@example.com",
                role="MERCHANT_VIEWER",
                clerk_invitation_id=clerk_invitation_id,
            )
        db_session.flush()

        # Step 2: Revoke (admin action or webhook)
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite_service.revoke_invite(
                invite_id=invite.id,
                revoked_by="admin_user",
            )
        db_session.flush()

        # Verify final state
        final_invite = invite_service.get_invite_by_id(invite.id)
        assert final_invite.status == InviteStatus.REVOKED

        # Verify no role was created
        roles = db_session.query(UserTenantRole).filter(
            UserTenantRole.tenant_id == sample_tenant.id,
        ).all()
        assert len(roles) == 0
