"""
End-to-end tests for invite flow.

Tests cover:
- Complete invite lifecycle: invite -> accept -> role granted
- Expired invite rejection
- Audit event trail verification
- Multi-tenant scenarios

Following patterns from e2e/conftest.py.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from src.models.tenant import Tenant, TenantStatus
from src.models.user import User
from src.models.user_tenant_roles import UserTenantRole
from src.models.tenant_invite import TenantInvite, InviteStatus
from src.services.invite_service import (
    InviteService,
    InviteExpiredError,
)
from src.platform.audit import AuditAction, AuditLog


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def e2e_tenant(db_session):
    """Create tenant for E2E tests."""
    tenant = Tenant(
        name="E2E Invite Tenant",
        slug=f"e2e-invite-{uuid.uuid4().hex[:8]}",
        clerk_org_id=f"org_e2e_{uuid.uuid4().hex[:8]}",
        billing_tier="growth",
        status=TenantStatus.ACTIVE,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def e2e_admin_user(db_session):
    """Create admin user for E2E tests."""
    user = User(
        clerk_user_id=f"user_e2e_admin_{uuid.uuid4().hex[:8]}",
        email="e2e-admin@example.com",
        first_name="E2E",
        last_name="Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def e2e_invitee_user(db_session):
    """Create invitee user for E2E tests."""
    user = User(
        clerk_user_id=f"user_e2e_invitee_{uuid.uuid4().hex[:8]}",
        email="e2e-invitee@example.com",
        first_name="E2E",
        last_name="Invitee",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def invite_service(db_session):
    """Create InviteService for E2E tests."""
    return InviteService(db_session)


@pytest.fixture
def audit_collector():
    """Collector to track audit events in E2E tests."""
    class AuditCollector:
        def __init__(self):
            self.events = []

        def collect(self, session, event):
            self.events.append(event)
            return MagicMock(spec=AuditLog)

        def get_events_by_action(self, action):
            return [e for e in self.events if e.action == action]

        def get_all_actions(self):
            return [e.action for e in self.events]

        def clear(self):
            self.events = []

    return AuditCollector()


# =============================================================================
# Test Suite: Complete Invite Lifecycle
# =============================================================================

@pytest.mark.e2e
class TestCompleteInviteLifecycle:
    """End-to-end tests for complete invite lifecycle."""

    def test_invite_accept_role_granted(
        self, db_session, e2e_tenant, e2e_admin_user, e2e_invitee_user, invite_service, audit_collector
    ):
        """
        E2E: Complete flow - invite -> accept -> role granted.

        Steps:
        1. Admin creates invite for new user
        2. User accepts invite (simulating Clerk webhook)
        3. Verify UserTenantRole created
        4. Verify audit trail
        """
        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_collector.collect
        ):
            # Step 1: Admin creates invite
            invite = invite_service.create_invite(
                tenant_id=e2e_tenant.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_VIEWER",
                invited_by=e2e_admin_user.clerk_user_id,
            )
            db_session.flush()

            assert invite.status == InviteStatus.PENDING

            # Step 2: User accepts invite
            result = invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            db_session.flush()

        # Step 3: Verify role was created
        role = db_session.query(UserTenantRole).filter(
            UserTenantRole.user_id == e2e_invitee_user.id,
            UserTenantRole.tenant_id == e2e_tenant.id,
            UserTenantRole.is_active == True,
        ).first()

        assert role is not None
        assert role.role == "MERCHANT_VIEWER"

        # Step 4: Verify audit trail
        all_actions = audit_collector.get_all_actions()
        assert AuditAction.IDENTITY_INVITE_SENT in all_actions
        assert AuditAction.IDENTITY_INVITE_ACCEPTED in all_actions

    def test_expired_invite_rejected(
        self, db_session, e2e_tenant, e2e_invitee_user, invite_service
    ):
        """
        E2E: Expired invite cannot be accepted.

        Steps:
        1. Create invite that's already expired
        2. Try to accept -> should fail
        """
        # Create expired invite
        invite = TenantInvite(
            tenant_id=e2e_tenant.id,
            email=e2e_invitee_user.email,
            role="MERCHANT_VIEWER",
            status=InviteStatus.PENDING,
            invited_at=datetime.now(timezone.utc) - timedelta(days=31),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(invite)
        db_session.flush()

        # Try to accept - should raise
        with pytest.raises(InviteExpiredError):
            invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )

    def test_audit_events_emitted_correctly(
        self, db_session, e2e_tenant, e2e_admin_user, e2e_invitee_user, invite_service, audit_collector
    ):
        """
        E2E: Verify all audit events are emitted with correct data.

        Tests:
        - identity.invite_sent on creation
        - identity.invite_accepted on acceptance
        - No PII in metadata
        - Correlation ID propagated
        """
        correlation_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
        service = InviteService(db_session, correlation_id=correlation_id)

        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_collector.collect
        ):
            # Create invite
            invite = service.create_invite(
                tenant_id=e2e_tenant.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_ADMIN",
                invited_by=e2e_admin_user.clerk_user_id,
            )
            db_session.flush()

            # Accept invite
            service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            db_session.flush()

        # Verify sent event
        sent_events = audit_collector.get_events_by_action(AuditAction.IDENTITY_INVITE_SENT)
        assert len(sent_events) == 1
        sent_event = sent_events[0]
        assert sent_event.correlation_id == correlation_id
        assert sent_event.metadata["role"] == "MERCHANT_ADMIN"
        assert sent_event.metadata["invited_by"] == e2e_admin_user.clerk_user_id
        assert "email" not in sent_event.metadata  # No PII

        # Verify accepted event
        accepted_events = audit_collector.get_events_by_action(AuditAction.IDENTITY_INVITE_ACCEPTED)
        assert len(accepted_events) == 1
        accepted_event = accepted_events[0]
        assert accepted_event.correlation_id == correlation_id
        assert "email" not in accepted_event.metadata  # No PII


# =============================================================================
# Test Suite: Multi-Tenant E2E
# =============================================================================

@pytest.mark.e2e
class TestMultiTenantE2E:
    """End-to-end tests for multi-tenant scenarios."""

    def test_same_user_invited_to_multiple_tenants(
        self, db_session, e2e_invitee_user, invite_service
    ):
        """
        E2E: User can be invited to and join multiple tenants.

        Steps:
        1. Create two tenants
        2. Invite user to both
        3. Accept both
        4. Verify user has roles in both tenants
        """
        # Create two tenants
        tenant1 = Tenant(
            name="E2E Tenant 1",
            slug=f"e2e-t1-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_t1_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        tenant2 = Tenant(
            name="E2E Tenant 2",
            slug=f"e2e-t2-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_t2_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        db_session.add_all([tenant1, tenant2])
        db_session.flush()

        with patch('src.services.invite_service.write_audit_log_sync'):
            # Invite to both tenants
            invite1 = invite_service.create_invite(
                tenant_id=tenant1.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_VIEWER",
            )
            invite2 = invite_service.create_invite(
                tenant_id=tenant2.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_ADMIN",
            )
            db_session.flush()

            # Accept both
            invite_service.accept_invite(
                invite_id=invite1.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            invite_service.accept_invite(
                invite_id=invite2.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            db_session.flush()

        # Verify roles in both tenants
        roles = db_session.query(UserTenantRole).filter(
            UserTenantRole.user_id == e2e_invitee_user.id,
            UserTenantRole.is_active == True,
        ).all()

        assert len(roles) == 2

        role_tenant_ids = {r.tenant_id for r in roles}
        assert tenant1.id in role_tenant_ids
        assert tenant2.id in role_tenant_ids

    def test_tenant_isolation(
        self, db_session, e2e_tenant, e2e_admin_user, invite_service
    ):
        """
        E2E: Invites are isolated to their tenant.

        Verifies that listing invites only returns invites for that tenant.
        """
        # Create another tenant
        other_tenant = Tenant(
            name="Other Tenant",
            slug=f"other-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_other_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        db_session.add(other_tenant)
        db_session.flush()

        with patch('src.services.invite_service.write_audit_log_sync'):
            # Create invites in both tenants
            invite1 = invite_service.create_invite(
                tenant_id=e2e_tenant.id,
                email="tenant1user@example.com",
                role="MERCHANT_VIEWER",
            )
            invite2 = invite_service.create_invite(
                tenant_id=other_tenant.id,
                email="tenant2user@example.com",
                role="MERCHANT_VIEWER",
            )
            db_session.flush()

        # List invites for first tenant - should only see its own
        invites_t1 = invite_service.list_invites(e2e_tenant.id)
        assert len(invites_t1) == 1
        assert invites_t1[0].id == invite1.id

        # List invites for second tenant
        invites_t2 = invite_service.list_invites(other_tenant.id)
        assert len(invites_t2) == 1
        assert invites_t2[0].id == invite2.id


# =============================================================================
# Test Suite: Edge Cases
# =============================================================================

@pytest.mark.e2e
class TestEdgeCases:
    """End-to-end tests for edge cases."""

    def test_revoke_then_reinvite(
        self, db_session, e2e_tenant, invite_service
    ):
        """
        E2E: After revoking, user can be re-invited.

        Steps:
        1. Create invite
        2. Revoke invite
        3. Create new invite for same email -> should succeed
        """
        email = "revoke-reinvite@example.com"

        with patch('src.services.invite_service.write_audit_log_sync'):
            # Create and revoke
            invite1 = invite_service.create_invite(
                tenant_id=e2e_tenant.id,
                email=email,
                role="MERCHANT_VIEWER",
            )
            db_session.flush()

            invite_service.revoke_invite(
                invite_id=invite1.id,
                revoked_by="admin",
            )
            db_session.flush()

            # Should be able to re-invite
            invite2 = invite_service.create_invite(
                tenant_id=e2e_tenant.id,
                email=email,
                role="MERCHANT_ADMIN",
            )
            db_session.flush()

        assert invite2.id != invite1.id
        assert invite2.status == InviteStatus.PENDING
        assert invite2.role == "MERCHANT_ADMIN"

    def test_expiration_job_only_affects_pending(
        self, db_session, e2e_tenant, e2e_invitee_user, invite_service
    ):
        """
        E2E: Expiration job only marks pending invites as expired.

        Steps:
        1. Create multiple invites with different statuses
        2. Run expiration job
        3. Verify only pending invites with past expiration are expired
        """
        now = datetime.now(timezone.utc)

        # Create various invites
        pending_expired = TenantInvite(
            tenant_id=e2e_tenant.id,
            email="pending-expired@example.com",
            role="MERCHANT_VIEWER",
            status=InviteStatus.PENDING,
            invited_at=now - timedelta(days=31),
            expires_at=now - timedelta(days=1),
        )

        pending_valid = TenantInvite(
            tenant_id=e2e_tenant.id,
            email="pending-valid@example.com",
            role="MERCHANT_VIEWER",
            status=InviteStatus.PENDING,
            invited_at=now,
            expires_at=now + timedelta(days=30),
        )

        accepted = TenantInvite(
            tenant_id=e2e_tenant.id,
            email="accepted@example.com",
            role="MERCHANT_VIEWER",
            status=InviteStatus.ACCEPTED,
            invited_at=now - timedelta(days=31),
            expires_at=now - timedelta(days=1),  # Expired time but already accepted
            accepted_at=now - timedelta(days=15),
            accepted_by_user_id=e2e_invitee_user.id,
        )

        db_session.add_all([pending_expired, pending_valid, accepted])
        db_session.flush()

        # Run expiration job
        with patch('src.services.invite_service.write_audit_log_sync'):
            count = invite_service.expire_stale_invites()

        assert count == 1  # Only pending_expired should be affected

        # Verify statuses
        db_session.refresh(pending_expired)
        db_session.refresh(pending_valid)
        db_session.refresh(accepted)

        assert pending_expired.status == InviteStatus.EXPIRED
        assert pending_valid.status == InviteStatus.PENDING
        assert accepted.status == InviteStatus.ACCEPTED  # Unchanged


# =============================================================================
# Test Suite: Security
# =============================================================================

@pytest.mark.e2e
@pytest.mark.security
class TestSecurityE2E:
    """End-to-end security tests."""

    def test_no_pii_in_any_audit_event(
        self, db_session, e2e_tenant, e2e_admin_user, e2e_invitee_user, invite_service, audit_collector
    ):
        """
        SECURITY: No PII should appear in any audit event metadata.

        PII fields: email, phone, name, first_name, last_name, address
        """
        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_collector.collect
        ):
            # Full lifecycle
            invite = invite_service.create_invite(
                tenant_id=e2e_tenant.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_VIEWER",
                invited_by=e2e_admin_user.clerk_user_id,
            )
            db_session.flush()

            invite_service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            db_session.flush()

        # Check all events
        pii_fields = ["email", "phone", "name", "first_name", "last_name", "address"]

        for event in audit_collector.events:
            for field in pii_fields:
                assert field not in event.metadata, \
                    f"PII field '{field}' found in {event.action} event metadata"

    def test_correlation_id_consistent_across_flow(
        self, db_session, e2e_tenant, e2e_invitee_user, audit_collector
    ):
        """
        SECURITY: Correlation ID should be consistent across related events.
        """
        correlation_id = f"security-test-{uuid.uuid4().hex}"
        service = InviteService(db_session, correlation_id=correlation_id)

        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_collector.collect
        ):
            invite = service.create_invite(
                tenant_id=e2e_tenant.id,
                email=e2e_invitee_user.email,
                role="MERCHANT_VIEWER",
            )
            db_session.flush()

            service.accept_invite(
                invite_id=invite.id,
                clerk_user_id=e2e_invitee_user.clerk_user_id,
            )
            db_session.flush()

        # All events should have same correlation ID
        for event in audit_collector.events:
            assert event.correlation_id == correlation_id, \
                f"Event {event.action} has wrong correlation_id"
