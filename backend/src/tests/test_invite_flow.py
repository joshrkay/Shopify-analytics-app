"""
Tests for invite flow (InviteService).

Tests cover:
- Invite creation and validation
- Invite acceptance with role assignment
- Invite revocation
- Invite expiration
- Audit event emission
- Edge cases (duplicate invites, existing members, expired invites)

Following patterns from:
- test_identity_audit_events.py (unit tests with mocked DB)
- test_tenant_members.py (integration tests with real DB)
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
from src.services.invite_service import (
    InviteService,
    TenantNotFoundError,
    TenantNotActiveError,
    InviteNotFoundError,
    InviteExpiredError,
    InviteRevokedError,
    InviteAlreadyAcceptedError,
    DuplicateInviteError,
    UserAlreadyMemberError,
    InvalidStateError,
    UserNotFoundError,
)
from src.platform.audit import AuditAction, AuditLog, AuditOutcome


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session for unit tests."""
    session = MagicMock(spec=Session)
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.flush = MagicMock()
    return session


@pytest.fixture
def correlation_id():
    """Fixed correlation ID for testing."""
    return "test-invite-corr-12345"


@pytest.fixture
def invite_service_mocked(mock_db_session, correlation_id):
    """Create InviteService with mocked audit emission."""
    with patch('src.services.invite_service.write_audit_log_sync') as mock_write:
        mock_write.return_value = MagicMock(spec=AuditLog)
        service = InviteService(
            session=mock_db_session,
            correlation_id=correlation_id,
        )
        service._mock_write = mock_write
        yield service


@pytest.fixture
def db_session(test_db_session):
    """Use the test database session for integration tests."""
    return test_db_session


@pytest.fixture
def service(db_session):
    """Create InviteService with real database session."""
    return InviteService(db_session)


@pytest.fixture
def sample_tenant(db_session):
    """Create a sample tenant for testing."""
    tenant = Tenant(
        name="Test Tenant",
        slug=f"test-tenant-{uuid.uuid4().hex[:8]}",
        clerk_org_id=f"org_test_{uuid.uuid4().hex[:8]}",
        billing_tier="growth",
        status=TenantStatus.ACTIVE,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def inactive_tenant(db_session):
    """Create an inactive tenant for testing."""
    tenant = Tenant(
        name="Inactive Tenant",
        slug=f"inactive-tenant-{uuid.uuid4().hex[:8]}",
        clerk_org_id=f"org_inactive_{uuid.uuid4().hex[:8]}",
        billing_tier="free",
        status=TenantStatus.DEACTIVATED,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing."""
    user = User(
        clerk_user_id=f"user_test_{uuid.uuid4().hex[:8]}",
        email="testuser@example.com",
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    user = User(
        clerk_user_id=f"user_admin_{uuid.uuid4().hex[:8]}",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def sample_invite(db_session, sample_tenant, admin_user):
    """Create a sample pending invite."""
    invite = TenantInvite.create_invite(
        tenant_id=sample_tenant.id,
        email="invitee@example.com",
        role="MERCHANT_VIEWER",
        invited_by=admin_user.clerk_user_id,
        expires_in_days=30,
    )
    db_session.add(invite)
    db_session.flush()
    return invite


@pytest.fixture
def expired_invite(db_session, sample_tenant, admin_user):
    """Create an expired invite."""
    invite = TenantInvite(
        tenant_id=sample_tenant.id,
        email="expired@example.com",
        role="MERCHANT_VIEWER",
        status=InviteStatus.PENDING,
        invited_by=admin_user.clerk_user_id,
        invited_at=datetime.now(timezone.utc) - timedelta(days=31),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(invite)
    db_session.flush()
    return invite


@pytest.fixture
def tenant_with_member(db_session, sample_tenant, sample_user):
    """Create a tenant with an existing member."""
    role = UserTenantRole.create_from_clerk(
        user_id=sample_user.id,
        tenant_id=sample_tenant.id,
        role="MERCHANT_VIEWER",
    )
    db_session.add(role)
    db_session.flush()
    return sample_tenant


# =============================================================================
# Test Suite: Invite Creation (Unit Tests)
# =============================================================================

class TestCreateInviteUnit:
    """Unit tests for invite creation with mocked database."""

    def test_create_invite_validates_email(self, invite_service_mocked):
        """Test that invalid email is rejected."""
        # Setup mock to return tenant
        mock_tenant = MagicMock()
        mock_tenant.is_active = True
        invite_service_mocked._get_tenant = MagicMock(return_value=mock_tenant)

        with pytest.raises(ValueError, match="Invalid email"):
            invite_service_mocked.create_invite(
                tenant_id="tenant_123",
                email="invalid-email",
                role="MERCHANT_VIEWER",
            )

    def test_create_invite_validates_role(self, invite_service_mocked):
        """Test that invalid role is rejected."""
        mock_tenant = MagicMock()
        mock_tenant.is_active = True
        invite_service_mocked._get_tenant = MagicMock(return_value=mock_tenant)

        with pytest.raises(ValueError, match="Invalid role"):
            invite_service_mocked.create_invite(
                tenant_id="tenant_123",
                email="valid@example.com",
                role="INVALID_ROLE",
            )

    def test_create_invite_emits_audit_event(self, invite_service_mocked, correlation_id):
        """Test that creating invite emits identity.invite_sent event."""
        mock_tenant = MagicMock()
        mock_tenant.id = "tenant_123"
        mock_tenant.is_active = True
        invite_service_mocked._get_tenant = MagicMock(return_value=mock_tenant)
        invite_service_mocked._get_pending_invite_by_email = MagicMock(return_value=None)

        # Mock query for existing user check
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        invite_service_mocked.session.query.return_value = mock_query

        invite_service_mocked.create_invite(
            tenant_id="tenant_123",
            email="newuser@example.com",
            role="MERCHANT_VIEWER",
            invited_by="admin_user_123",
        )

        # Verify audit event was emitted
        invite_service_mocked._mock_write.assert_called_once()
        call_args = invite_service_mocked._mock_write.call_args
        event = call_args[1]["event"]

        assert event.action == AuditAction.IDENTITY_INVITE_SENT
        assert event.correlation_id == correlation_id
        assert event.metadata["role"] == "MERCHANT_VIEWER"
        assert event.metadata["invited_by"] == "admin_user_123"
        # SECURITY: No email in metadata
        assert "email" not in event.metadata


# =============================================================================
# Test Suite: Invite Creation (Integration Tests)
# =============================================================================

class TestCreateInviteIntegration:
    """Integration tests for invite creation with real database."""

    def test_create_invite_success(self, service, db_session, sample_tenant, admin_user):
        """Test successfully creating an invitation."""
        invite = service.create_invite(
            tenant_id=sample_tenant.id,
            email="newuser@example.com",
            role="MERCHANT_VIEWER",
            invited_by=admin_user.clerk_user_id,
        )
        db_session.flush()

        assert invite.id is not None
        assert invite.email == "newuser@example.com"
        assert invite.role == "MERCHANT_VIEWER"
        assert invite.status == InviteStatus.PENDING
        assert invite.tenant_id == sample_tenant.id
        assert invite.invited_by == admin_user.clerk_user_id
        assert invite.expires_at > datetime.now(timezone.utc)

    def test_create_invite_tenant_not_found(self, service):
        """Test creating invite for non-existent tenant."""
        with pytest.raises(TenantNotFoundError):
            service.create_invite(
                tenant_id="nonexistent_tenant_id",
                email="user@example.com",
                role="MERCHANT_VIEWER",
            )

    def test_create_invite_inactive_tenant(self, service, inactive_tenant):
        """Test creating invite for inactive tenant."""
        with pytest.raises(TenantNotActiveError):
            service.create_invite(
                tenant_id=inactive_tenant.id,
                email="user@example.com",
                role="MERCHANT_VIEWER",
            )

    def test_create_invite_duplicate_pending(self, service, sample_tenant, sample_invite):
        """Test that duplicate pending invite is rejected."""
        with pytest.raises(DuplicateInviteError):
            service.create_invite(
                tenant_id=sample_tenant.id,
                email=sample_invite.email,  # Same email
                role="MERCHANT_ADMIN",
            )

    def test_create_invite_user_already_member(
        self, service, tenant_with_member, sample_user
    ):
        """Test that inviting existing member is rejected."""
        with pytest.raises(UserAlreadyMemberError):
            service.create_invite(
                tenant_id=tenant_with_member.id,
                email=sample_user.email,  # Already a member
                role="MERCHANT_ADMIN",
            )

    def test_create_invite_custom_expiration(self, service, sample_tenant):
        """Test creating invite with custom expiration."""
        invite = service.create_invite(
            tenant_id=sample_tenant.id,
            email="custom@example.com",
            role="MERCHANT_VIEWER",
            expires_in_days=7,
        )

        expected_expiry = datetime.now(timezone.utc) + timedelta(days=7)
        # Allow 1 minute tolerance
        assert abs((invite.expires_at - expected_expiry).total_seconds()) < 60

    def test_create_invite_with_clerk_invitation_id(self, service, sample_tenant):
        """Test creating invite with Clerk invitation ID (from webhook)."""
        clerk_id = "inv_clerk_12345"
        invite = service.create_invite(
            tenant_id=sample_tenant.id,
            email="clerkuser@example.com",
            role="MERCHANT_VIEWER",
            clerk_invitation_id=clerk_id,
        )

        assert invite.clerk_invitation_id == clerk_id


# =============================================================================
# Test Suite: Invite Acceptance
# =============================================================================

class TestAcceptInvite:
    """Tests for invite acceptance."""

    def test_accept_invite_creates_role(
        self, service, db_session, sample_tenant, sample_invite, sample_user
    ):
        """Test that accepting invite creates UserTenantRole."""
        # Update invite email to match sample_user
        sample_invite.email = sample_user.email
        db_session.flush()

        result = service.accept_invite(
            invite_id=sample_invite.id,
            clerk_user_id=sample_user.clerk_user_id,
        )
        db_session.flush()

        assert result["user_id"] == sample_user.id
        assert result["tenant_id"] == sample_tenant.id
        assert result["role"] == sample_invite.role

        # Verify UserTenantRole was created
        role = db_session.query(UserTenantRole).filter(
            UserTenantRole.user_id == sample_user.id,
            UserTenantRole.tenant_id == sample_tenant.id,
        ).first()
        assert role is not None
        assert role.role == sample_invite.role
        assert role.is_active is True

    def test_accept_invite_updates_status(
        self, service, db_session, sample_invite, sample_user
    ):
        """Test that accepting invite updates status to accepted."""
        sample_invite.email = sample_user.email
        db_session.flush()

        service.accept_invite(
            invite_id=sample_invite.id,
            clerk_user_id=sample_user.clerk_user_id,
        )
        db_session.flush()

        # Reload invite
        updated_invite = service.get_invite_by_id(sample_invite.id)
        assert updated_invite.status == InviteStatus.ACCEPTED
        assert updated_invite.accepted_at is not None
        assert updated_invite.accepted_by_user_id == sample_user.id

    def test_accept_invite_not_found(self, service):
        """Test accepting non-existent invite."""
        with pytest.raises(InviteNotFoundError):
            service.accept_invite(
                invite_id="nonexistent_invite_id",
                clerk_user_id="user_123",
            )

    def test_accept_expired_invite(self, service, expired_invite, sample_user):
        """Test accepting expired invite is rejected."""
        with pytest.raises(InviteExpiredError):
            service.accept_invite(
                invite_id=expired_invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )

    def test_accept_revoked_invite(self, service, db_session, sample_invite, sample_user):
        """Test accepting revoked invite is rejected."""
        sample_invite.revoke()
        db_session.flush()

        with pytest.raises(InviteRevokedError):
            service.accept_invite(
                invite_id=sample_invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )

    def test_accept_already_accepted_invite(
        self, service, db_session, sample_invite, sample_user
    ):
        """Test accepting already accepted invite is rejected."""
        sample_invite.accept(sample_user.id)
        db_session.flush()

        with pytest.raises(InviteAlreadyAcceptedError):
            service.accept_invite(
                invite_id=sample_invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )

    def test_accept_invite_user_not_found(self, service, sample_invite):
        """Test accepting invite with non-existent user."""
        with pytest.raises(UserNotFoundError):
            service.accept_invite(
                invite_id=sample_invite.id,
                clerk_user_id="nonexistent_user_id",
            )


# =============================================================================
# Test Suite: Invite Revocation
# =============================================================================

class TestRevokeInvite:
    """Tests for invite revocation."""

    def test_revoke_invite_success(self, service, db_session, sample_invite, admin_user):
        """Test successfully revoking an invitation."""
        result = service.revoke_invite(
            invite_id=sample_invite.id,
            revoked_by=admin_user.clerk_user_id,
        )

        assert result.status == InviteStatus.REVOKED

    def test_revoke_invite_not_found(self, service):
        """Test revoking non-existent invite."""
        with pytest.raises(InviteNotFoundError):
            service.revoke_invite(
                invite_id="nonexistent_invite_id",
                revoked_by="admin_user",
            )

    def test_revoke_already_accepted(self, service, db_session, sample_invite, sample_user):
        """Test that revoking accepted invite is rejected."""
        sample_invite.accept(sample_user.id)
        db_session.flush()

        with pytest.raises(InvalidStateError):
            service.revoke_invite(
                invite_id=sample_invite.id,
                revoked_by="admin_user",
            )

    def test_revoke_already_expired(self, service, db_session, sample_invite):
        """Test that revoking expired invite is rejected."""
        sample_invite.mark_expired()
        db_session.flush()

        with pytest.raises(InvalidStateError):
            service.revoke_invite(
                invite_id=sample_invite.id,
                revoked_by="admin_user",
            )


# =============================================================================
# Test Suite: Invite Expiration
# =============================================================================

class TestInviteExpiration:
    """Tests for invite expiration."""

    def test_is_expired_property_true(self, expired_invite):
        """Test is_expired returns True for expired invite."""
        assert expired_invite.is_expired is True

    def test_is_expired_property_false(self, sample_invite):
        """Test is_expired returns False for valid invite."""
        assert sample_invite.is_expired is False

    def test_is_actionable_true(self, sample_invite):
        """Test is_actionable returns True for pending non-expired invite."""
        assert sample_invite.is_actionable is True

    def test_is_actionable_false_expired(self, expired_invite):
        """Test is_actionable returns False for expired invite."""
        assert expired_invite.is_actionable is False

    def test_is_actionable_false_accepted(self, db_session, sample_invite, sample_user):
        """Test is_actionable returns False for accepted invite."""
        sample_invite.accept(sample_user.id)
        assert sample_invite.is_actionable is False

    def test_expire_stale_invites(self, service, db_session, sample_tenant, admin_user):
        """Test bulk expiration of stale invites."""
        # Create several expired invites
        now = datetime.now(timezone.utc)
        for i in range(3):
            invite = TenantInvite(
                tenant_id=sample_tenant.id,
                email=f"stale{i}@example.com",
                role="MERCHANT_VIEWER",
                status=InviteStatus.PENDING,
                invited_by=admin_user.clerk_user_id,
                invited_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
            db_session.add(invite)

        # Create one valid invite (should not be expired)
        valid_invite = TenantInvite.create_invite(
            tenant_id=sample_tenant.id,
            email="valid@example.com",
            role="MERCHANT_VIEWER",
            invited_by=admin_user.clerk_user_id,
        )
        db_session.add(valid_invite)
        db_session.flush()

        # Run expiration job
        with patch('src.services.invite_service.write_audit_log_sync'):
            count = service.expire_stale_invites()

        assert count == 3

        # Verify expired invites have correct status
        expired_invites = db_session.query(TenantInvite).filter(
            TenantInvite.tenant_id == sample_tenant.id,
            TenantInvite.status == InviteStatus.EXPIRED,
        ).all()
        assert len(expired_invites) == 3

        # Verify valid invite was not expired
        reloaded_valid = service.get_invite_by_id(valid_invite.id)
        assert reloaded_valid.status == InviteStatus.PENDING


# =============================================================================
# Test Suite: Invite Queries
# =============================================================================

class TestInviteQueries:
    """Tests for invite query methods."""

    def test_list_invites_by_tenant(self, service, db_session, sample_tenant, admin_user):
        """Test listing invites for a tenant."""
        # Create several invites
        for i in range(3):
            invite = TenantInvite.create_invite(
                tenant_id=sample_tenant.id,
                email=f"user{i}@example.com",
                role="MERCHANT_VIEWER",
                invited_by=admin_user.clerk_user_id,
            )
            db_session.add(invite)
        db_session.flush()

        invites = service.list_invites(sample_tenant.id)
        assert len(invites) == 3

    def test_list_invites_filters_by_status(
        self, service, db_session, sample_tenant, admin_user, sample_user
    ):
        """Test filtering invites by status."""
        # Create pending invite
        pending = TenantInvite.create_invite(
            tenant_id=sample_tenant.id,
            email="pending@example.com",
            role="MERCHANT_VIEWER",
        )
        db_session.add(pending)

        # Create accepted invite
        accepted = TenantInvite.create_invite(
            tenant_id=sample_tenant.id,
            email="accepted@example.com",
            role="MERCHANT_VIEWER",
        )
        accepted.accept(sample_user.id)
        db_session.add(accepted)
        db_session.flush()

        # Filter by status
        pending_only = service.list_invites(sample_tenant.id, status="pending")
        assert len(pending_only) == 1
        assert pending_only[0].email == "pending@example.com"

    def test_get_invite_by_clerk_id(self, service, db_session, sample_tenant):
        """Test finding invite by Clerk invitation ID."""
        clerk_id = "inv_clerk_test_123"
        invite = TenantInvite.create_invite(
            tenant_id=sample_tenant.id,
            email="clerkuser@example.com",
            role="MERCHANT_VIEWER",
            clerk_invitation_id=clerk_id,
        )
        db_session.add(invite)
        db_session.flush()

        found = service.get_invite_by_clerk_id(clerk_id)
        assert found is not None
        assert found.id == invite.id


# =============================================================================
# Test Suite: Audit Events
# =============================================================================

class TestInviteAuditEvents:
    """Test audit event emission for invite lifecycle."""

    @pytest.fixture
    def audit_event_collector(self):
        """Collector to track audit events."""
        class EventCollector:
            def __init__(self):
                self.events = []

            def collect(self, session, event):
                self.events.append(event)
                return MagicMock(spec=AuditLog)

            def get_events_by_action(self, action):
                return [e for e in self.events if e.action == action]

            def get_all_actions(self):
                return [e.action for e in self.events]

        return EventCollector()

    def test_invite_sent_emits_event(self, service, db_session, sample_tenant, admin_user, audit_event_collector):
        """Test that creating invite emits identity.invite_sent event."""
        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_event_collector.collect
        ):
            service.create_invite(
                tenant_id=sample_tenant.id,
                email="newuser@example.com",
                role="MERCHANT_VIEWER",
                invited_by=admin_user.clerk_user_id,
            )

        sent_events = audit_event_collector.get_events_by_action(
            AuditAction.IDENTITY_INVITE_SENT
        )
        assert len(sent_events) == 1
        event = sent_events[0]
        assert event.metadata["role"] == "MERCHANT_VIEWER"
        assert event.metadata["invited_by"] == admin_user.clerk_user_id

    def test_invite_accepted_emits_event(
        self, service, db_session, sample_invite, sample_user, audit_event_collector
    ):
        """Test that accepting invite emits identity.invite_accepted event."""
        sample_invite.email = sample_user.email
        db_session.flush()

        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_event_collector.collect
        ):
            service.accept_invite(
                invite_id=sample_invite.id,
                clerk_user_id=sample_user.clerk_user_id,
            )

        accepted_events = audit_event_collector.get_events_by_action(
            AuditAction.IDENTITY_INVITE_ACCEPTED
        )
        assert len(accepted_events) == 1

    def test_invite_expired_emits_event(
        self, service, db_session, sample_tenant, admin_user, audit_event_collector
    ):
        """Test that expiring invite emits identity.invite_expired event."""
        # Create expired invite
        invite = TenantInvite(
            tenant_id=sample_tenant.id,
            email="expired@example.com",
            role="MERCHANT_VIEWER",
            status=InviteStatus.PENDING,
            invited_by=admin_user.clerk_user_id,
            invited_at=datetime.now(timezone.utc) - timedelta(days=31),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(invite)
        db_session.flush()

        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_event_collector.collect
        ):
            service.expire_stale_invites()

        expired_events = audit_event_collector.get_events_by_action(
            AuditAction.IDENTITY_INVITE_EXPIRED
        )
        assert len(expired_events) == 1

    def test_no_pii_in_audit_events(
        self, service, db_session, sample_tenant, admin_user, audit_event_collector
    ):
        """SECURITY: No PII should appear in audit event metadata."""
        with patch(
            'src.services.invite_service.write_audit_log_sync',
            side_effect=audit_event_collector.collect
        ):
            service.create_invite(
                tenant_id=sample_tenant.id,
                email="testpii@example.com",
                role="MERCHANT_VIEWER",
                invited_by=admin_user.clerk_user_id,
            )

        for event in audit_event_collector.events:
            pii_fields = ["email", "phone", "name", "first_name", "last_name"]
            for field in pii_fields:
                assert field not in event.metadata, \
                    f"PII field '{field}' found in audit event metadata"


# =============================================================================
# Test Suite: Multi-Tenant Scenarios
# =============================================================================

class TestMultiTenantInvites:
    """Tests for multi-tenant invite scenarios."""

    def test_same_email_multiple_tenants(self, service, db_session, admin_user):
        """Test that same email can be invited to multiple tenants."""
        # Create two tenants
        tenant1 = Tenant(
            name="Tenant 1",
            slug=f"tenant-1-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_1_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        tenant2 = Tenant(
            name="Tenant 2",
            slug=f"tenant-2-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_2_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        db_session.add_all([tenant1, tenant2])
        db_session.flush()

        email = "multiinvite@example.com"

        # Invite to both tenants
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite1 = service.create_invite(
                tenant_id=tenant1.id,
                email=email,
                role="MERCHANT_VIEWER",
            )
            invite2 = service.create_invite(
                tenant_id=tenant2.id,
                email=email,
                role="MERCHANT_ADMIN",
            )

        assert invite1.id != invite2.id
        assert invite1.tenant_id == tenant1.id
        assert invite2.tenant_id == tenant2.id

    def test_accept_one_doesnt_affect_other(self, service, db_session, admin_user):
        """Test accepting invite to one tenant doesn't affect other invites."""
        # Create two tenants
        tenant1 = Tenant(
            name="Tenant A",
            slug=f"tenant-a-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_a_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        tenant2 = Tenant(
            name="Tenant B",
            slug=f"tenant-b-{uuid.uuid4().hex[:8]}",
            clerk_org_id=f"org_b_{uuid.uuid4().hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        db_session.add_all([tenant1, tenant2])
        db_session.flush()

        # Create user
        user = User(
            clerk_user_id=f"user_multi_{uuid.uuid4().hex[:8]}",
            email="multiuser@example.com",
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()

        # Create invites for both tenants
        with patch('src.services.invite_service.write_audit_log_sync'):
            invite1 = service.create_invite(
                tenant_id=tenant1.id,
                email=user.email,
                role="MERCHANT_VIEWER",
            )
            invite2 = service.create_invite(
                tenant_id=tenant2.id,
                email=user.email,
                role="MERCHANT_ADMIN",
            )
        db_session.flush()

        # Accept first invite only
        with patch('src.services.invite_service.write_audit_log_sync'):
            service.accept_invite(
                invite_id=invite1.id,
                clerk_user_id=user.clerk_user_id,
            )
        db_session.flush()

        # Reload invites
        reloaded1 = service.get_invite_by_id(invite1.id)
        reloaded2 = service.get_invite_by_id(invite2.id)

        # First should be accepted, second should still be pending
        assert reloaded1.status == InviteStatus.ACCEPTED
        assert reloaded2.status == InviteStatus.PENDING
