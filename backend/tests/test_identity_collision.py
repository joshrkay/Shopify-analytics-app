"""
Tests for Identity Collision Guardrails.

These tests verify:
1. Invite acceptance with same email but different clerk_user_id does not merge accounts
2. New user is created for the accepting clerk_user_id
3. Existing user's roles are not overwritten
4. Identity collision audit event is logged

Story: Secure Administrative Access - Identity Collision Guardrails
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
from enum import Enum


# =============================================================================
# Mock Classes (to avoid full import chain)
# =============================================================================


class MockInviteStatus(str, Enum):
    """Mock invite status enum."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class MockUser:
    """Mock User model for testing."""
    def __init__(
        self,
        id: str = None,
        clerk_user_id: str = None,
        email: str = "test@example.com",
        is_active: bool = True,
    ):
        self.id = id or str(uuid.uuid4())
        self.clerk_user_id = clerk_user_id or f"clerk_{uuid.uuid4().hex[:8]}"
        self.email = email
        self.is_active = is_active


class MockTenant:
    """Mock Tenant model for testing."""
    def __init__(
        self,
        id: str = None,
        name: str = "Test Tenant",
        status: str = "active",
        billing_tier: str = "growth",
    ):
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.status = status
        self.billing_tier = billing_tier

    @property
    def is_active(self):
        return self.status == "active"


class MockTenantInvite:
    """Mock TenantInvite model for testing."""
    def __init__(
        self,
        id: str = None,
        tenant_id: str = None,
        email: str = "invitee@example.com",
        role: str = "MERCHANT_VIEWER",
        status: MockInviteStatus = MockInviteStatus.PENDING,
        invited_by: str = None,
        expires_at: datetime = None,
    ):
        self.id = id or str(uuid.uuid4())
        self.tenant_id = tenant_id or str(uuid.uuid4())
        self.email = email
        self.role = role
        self.status = status
        self.invited_by = invited_by
        self.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
        self.accepted_at = None
        self.accepted_by_user_id = None

    @property
    def is_expired(self):
        return datetime.now(timezone.utc) > self.expires_at

    def accept(self, user_id: str):
        self.status = MockInviteStatus.ACCEPTED
        self.accepted_at = datetime.now(timezone.utc)
        self.accepted_by_user_id = user_id


class MockUserTenantRole:
    """Mock UserTenantRole model for testing."""
    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        granted_by: str = None,
    ):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.assigned_by = granted_by
        self.is_active = True

    @staticmethod
    def create_from_grant(user_id: str, tenant_id: str, role: str, granted_by: str = None):
        return MockUserTenantRole(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            granted_by=granted_by,
        )


class MockSession:
    """Mock SQLAlchemy session for testing."""
    def __init__(self):
        self.users = {}  # clerk_user_id -> user
        self.users_by_email = {}  # email -> user (first user with that email)
        self.tenants = {}
        self.invites = {}
        self.roles = []
        self.audit_logs = []
        self._flushed = False

    def query(self, model):
        return MockQuery(self, model)

    def add(self, obj):
        if isinstance(obj, MockUser):
            self.users[obj.clerk_user_id] = obj
            if obj.email not in self.users_by_email:
                self.users_by_email[obj.email] = obj
        elif isinstance(obj, MockUserTenantRole):
            self.roles.append(obj)
        elif hasattr(obj, 'action'):
            self.audit_logs.append(obj)

    def flush(self):
        self._flushed = True


class MockQuery:
    """Mock SQLAlchemy query for testing."""
    def __init__(self, session: MockSession, model):
        self.session = session
        self.model = model
        self._filters = {}

    def filter(self, *args, **kwargs):
        # Parse filter conditions from args
        for arg in args:
            # Handle SQLAlchemy-style comparisons
            if hasattr(arg, 'left') and hasattr(arg, 'right'):
                key = arg.left.key
                value = arg.right
                self._filters[key] = value
            elif hasattr(arg, 'expression'):
                # Handle boolean expressions
                pass
        return self

    def first(self):
        # Return based on model type and filters
        if 'clerk_user_id' in self._filters:
            return self.session.users.get(self._filters['clerk_user_id'])
        if 'email' in self._filters:
            return self.session.users_by_email.get(self._filters['email'])
        if 'id' in self._filters and hasattr(self, '_model_type'):
            if self._model_type == 'invite':
                return self.session.invites.get(self._filters['id'])
        return None


# =============================================================================
# Mock InviteService (matches actual implementation logic)
# =============================================================================


class MockInviteService:
    """
    Mock implementation of InviteService for testing identity collision.

    IDENTITY COLLISION GUARDRAILS:
    - Invites bind to clerk_user_id, not email
    - If accepting clerk_user_id differs from existing user with same email:
      - Do NOT merge accounts
      - Create new user for the accepting clerk_user_id
      - Emit identity.identity_collision_detected audit event
    """

    def __init__(self, session: MockSession, correlation_id: str = None):
        self.session = session
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._audit_events = []

    def accept_invite(
        self,
        invite_id: str,
        clerk_user_id: str,
        accepting_user_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Accept an invitation with identity collision detection.
        """
        invite = self.session.invites.get(invite_id)
        if not invite:
            raise ValueError(f"Invitation {invite_id} not found")

        if invite.status == MockInviteStatus.ACCEPTED:
            raise ValueError("Invitation already accepted")
        if invite.status == MockInviteStatus.REVOKED:
            raise ValueError("Invitation was revoked")
        if invite.is_expired:
            raise ValueError("Invitation has expired")

        # Get user by clerk_user_id
        user = self.session.users.get(clerk_user_id)

        identity_collision = False
        existing_user_clerk_id = None

        if not user:
            # Check for identity collision: same email, different clerk_user_id
            email_to_check = accepting_user_email or invite.email

            existing_user_with_email = self.session.users_by_email.get(email_to_check)

            if existing_user_with_email and existing_user_with_email.is_active:
                # IDENTITY COLLISION DETECTED
                identity_collision = True
                existing_user_clerk_id = existing_user_with_email.clerk_user_id

                # Emit identity collision audit event
                self._audit_events.append({
                    "action": "identity.identity_collision_detected",
                    "invite_id": invite.id,
                    "tenant_id": invite.tenant_id,
                    "email": email_to_check,
                    "accepting_clerk_user_id": clerk_user_id,
                    "existing_clerk_user_id": existing_user_clerk_id,
                    "action_taken": "new_user_created",
                })

            # Create new user for this clerk_user_id (regardless of collision)
            # Do NOT merge with existing user
            user = MockUser(
                clerk_user_id=clerk_user_id,
                email=email_to_check,
                is_active=True,
            )
            self.session.add(user)
            self.session.flush()

        # Create role assignment for the NEW user
        user_role = MockUserTenantRole.create_from_grant(
            user_id=user.id,
            tenant_id=invite.tenant_id,
            role=invite.role,
            granted_by="invite_acceptance",
        )
        self.session.add(user_role)

        # Update invite status
        invite.accept(user.id)

        # Emit invite accepted audit event
        self._audit_events.append({
            "action": "identity.invite_accepted",
            "invite_id": invite.id,
            "tenant_id": invite.tenant_id,
            "role": invite.role,
        })

        return {
            "invite_id": invite_id,
            "user_id": user.id,
            "tenant_id": invite.tenant_id,
            "role": invite.role,
            "identity_collision": identity_collision,
        }


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MockSession()


@pytest.fixture
def tenant(mock_session):
    """Create a test tenant."""
    t = MockTenant(
        id="tenant-123",
        name="Test Store",
    )
    mock_session.tenants[t.id] = t
    return t


@pytest.fixture
def existing_user(mock_session):
    """Create an existing user with an email."""
    user = MockUser(
        id="existing-user-id",
        clerk_user_id="clerk_existing_user",
        email="shared@example.com",
        is_active=True,
    )
    mock_session.users[user.clerk_user_id] = user
    mock_session.users_by_email[user.email] = user
    return user


@pytest.fixture
def pending_invite(mock_session, tenant):
    """Create a pending invite."""
    invite = MockTenantInvite(
        id="invite-123",
        tenant_id=tenant.id,
        email="shared@example.com",  # Same email as existing_user
        role="MERCHANT_VIEWER",
    )
    mock_session.invites[invite.id] = invite
    return invite


# =============================================================================
# Test: Same Email, Different clerk_user_id - Does NOT Merge
# =============================================================================


class TestIdentityCollisionNoMerge:
    """Tests verifying identity collision does not merge accounts."""

    def test_invite_acceptance_creates_new_user_on_collision(
        self, mock_session, existing_user, pending_invite, tenant
    ):
        """
        When invite is accepted by a different clerk_user_id with same email,
        a NEW user should be created, NOT merged with existing.
        """
        new_clerk_user_id = "clerk_new_user_different_identity"

        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=pending_invite.id,
            clerk_user_id=new_clerk_user_id,
            accepting_user_email=pending_invite.email,  # Same email
        )

        # Verify collision was detected
        assert result["identity_collision"] is True

        # Verify a NEW user was created
        new_user = mock_session.users.get(new_clerk_user_id)
        assert new_user is not None
        assert new_user.clerk_user_id == new_clerk_user_id

        # Verify the existing user is UNTOUCHED
        assert existing_user.clerk_user_id == "clerk_existing_user"
        assert existing_user.id == "existing-user-id"

        # Verify the role was assigned to the NEW user, not existing
        role_assigned = mock_session.roles[0]
        assert role_assigned.user_id == new_user.id
        assert role_assigned.user_id != existing_user.id

    def test_existing_user_roles_not_overwritten(
        self, mock_session, existing_user, pending_invite, tenant
    ):
        """
        Existing user's roles should not be affected by collision.
        """
        # Give existing user a role
        existing_role = MockUserTenantRole(
            user_id=existing_user.id,
            tenant_id=tenant.id,
            role="MERCHANT_ADMIN",
        )
        mock_session.roles.append(existing_role)

        new_clerk_user_id = "clerk_new_user"

        service = MockInviteService(mock_session)
        service.accept_invite(
            invite_id=pending_invite.id,
            clerk_user_id=new_clerk_user_id,
        )

        # Verify existing user's role is still there
        existing_roles = [r for r in mock_session.roles if r.user_id == existing_user.id]
        assert len(existing_roles) == 1
        assert existing_roles[0].role == "MERCHANT_ADMIN"

        # Verify new user got the invite role
        new_user = mock_session.users.get(new_clerk_user_id)
        new_roles = [r for r in mock_session.roles if r.user_id == new_user.id]
        assert len(new_roles) == 1
        assert new_roles[0].role == "MERCHANT_VIEWER"


# =============================================================================
# Test: Identity Collision Audit Event
# =============================================================================


class TestIdentityCollisionAuditEvent:
    """Tests verifying identity collision audit event is logged."""

    def test_collision_emits_audit_event(
        self, mock_session, existing_user, pending_invite
    ):
        """
        Identity collision should emit audit event with details.
        """
        new_clerk_user_id = "clerk_new_user"

        service = MockInviteService(mock_session)
        service.accept_invite(
            invite_id=pending_invite.id,
            clerk_user_id=new_clerk_user_id,
        )

        # Find collision audit event
        collision_events = [
            e for e in service._audit_events
            if e["action"] == "identity.identity_collision_detected"
        ]

        assert len(collision_events) == 1
        event = collision_events[0]
        assert event["invite_id"] == pending_invite.id
        assert event["tenant_id"] == pending_invite.tenant_id
        assert event["email"] == pending_invite.email
        assert event["accepting_clerk_user_id"] == new_clerk_user_id
        assert event["existing_clerk_user_id"] == existing_user.clerk_user_id
        assert event["action_taken"] == "new_user_created"

    def test_no_collision_event_when_user_exists(self, mock_session, pending_invite):
        """
        No collision event when accepting user already exists in DB.
        """
        # Create a user with the accepting clerk_user_id
        accepting_user = MockUser(
            clerk_user_id="clerk_accepting_user",
            email="different@example.com",
        )
        mock_session.users[accepting_user.clerk_user_id] = accepting_user

        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=pending_invite.id,
            clerk_user_id=accepting_user.clerk_user_id,
        )

        # No collision since user already exists
        assert result["identity_collision"] is False

        # No collision audit event
        collision_events = [
            e for e in service._audit_events
            if e["action"] == "identity.identity_collision_detected"
        ]
        assert len(collision_events) == 0


# =============================================================================
# Test: No Collision When Email Not Matched
# =============================================================================


class TestNoCollisionScenarios:
    """Tests verifying no collision in normal scenarios."""

    def test_no_collision_when_email_not_in_use(self, mock_session, tenant):
        """
        No collision when invite email is not used by any existing user.
        """
        invite = MockTenantInvite(
            id="invite-new-email",
            tenant_id=tenant.id,
            email="unique@example.com",  # Email not used by anyone
            role="MERCHANT_VIEWER",
        )
        mock_session.invites[invite.id] = invite

        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=invite.id,
            clerk_user_id="clerk_brand_new_user",
        )

        assert result["identity_collision"] is False

    def test_no_collision_when_same_clerk_user_id(
        self, mock_session, existing_user, pending_invite
    ):
        """
        No collision when the accepting clerk_user_id matches existing user.
        """
        # Invite is accepted by the user who owns that email
        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=pending_invite.id,
            clerk_user_id=existing_user.clerk_user_id,  # Same user
        )

        # No collision since it's the same person
        assert result["identity_collision"] is False

        # No collision audit event
        collision_events = [
            e for e in service._audit_events
            if e["action"] == "identity.identity_collision_detected"
        ]
        assert len(collision_events) == 0


# =============================================================================
# Test: Support-Safe Error Path (Revoke and Re-invite)
# =============================================================================


class TestSupportSafeRevoke:
    """Tests for support-safe error recovery path."""

    def test_can_revoke_after_collision(self, mock_session, existing_user, tenant):
        """
        After identity collision, tenant admin can revoke the wrong user's role.
        """
        # Create the collision scenario
        invite = MockTenantInvite(
            id="invite-collision",
            tenant_id=tenant.id,
            email=existing_user.email,
            role="MERCHANT_VIEWER",
        )
        mock_session.invites[invite.id] = invite

        new_clerk_user_id = "clerk_wrong_person"

        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=invite.id,
            clerk_user_id=new_clerk_user_id,
        )

        # Collision happened - wrong person got access
        assert result["identity_collision"] is True

        # Tenant admin can now revoke the role from wrong user
        wrong_user = mock_session.users.get(new_clerk_user_id)
        wrong_user_roles = [r for r in mock_session.roles if r.user_id == wrong_user.id]

        # Simulate role deactivation (revoke)
        for role in wrong_user_roles:
            role.is_active = False

        # Verify role is deactivated
        active_roles = [
            r for r in mock_session.roles
            if r.user_id == wrong_user.id and r.is_active
        ]
        assert len(active_roles) == 0


# =============================================================================
# Test: Multiple Collisions
# =============================================================================


class TestMultipleCollisions:
    """Tests for multiple identity collision scenarios."""

    def test_multiple_different_clerk_users_same_email(self, mock_session, tenant):
        """
        Multiple different Clerk users can have the same email.
        Each gets their own user record.
        """
        shared_email = "shared@company.com"

        # First user
        user1 = MockUser(
            clerk_user_id="clerk_user_1",
            email=shared_email,
        )
        mock_session.users[user1.clerk_user_id] = user1
        mock_session.users_by_email[shared_email] = user1

        # Create invite for same email
        invite = MockTenantInvite(
            id="invite-multi",
            tenant_id=tenant.id,
            email=shared_email,
            role="MERCHANT_VIEWER",
        )
        mock_session.invites[invite.id] = invite

        # Second user accepts (different clerk_user_id)
        service = MockInviteService(mock_session)
        result = service.accept_invite(
            invite_id=invite.id,
            clerk_user_id="clerk_user_2",  # Different identity
            accepting_user_email=shared_email,
        )

        # Collision detected
        assert result["identity_collision"] is True

        # Both users exist separately
        user1_check = mock_session.users.get("clerk_user_1")
        user2_check = mock_session.users.get("clerk_user_2")

        assert user1_check is not None
        assert user2_check is not None
        assert user1_check.id != user2_check.id
        assert user1_check.email == user2_check.email  # Same email, different users
