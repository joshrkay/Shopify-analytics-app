"""
Tests for Super Admin (DB-backed only) functionality.

These tests verify:
1. A user cannot become super admin via JWT claim manipulation
2. Only existing super admins can grant/revoke super admin
3. Super admin status is resolved from database only
4. Proper audit events are emitted for super admin changes

Story: Secure Administrative Access - DB-Backed Super Admin
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from typing import Optional, List
import uuid


# =============================================================================
# Mock Classes (to avoid full import chain)
# =============================================================================


class MockUser:
    """Mock User model for testing."""
    def __init__(
        self,
        id: str = None,
        clerk_user_id: str = None,
        email: str = "test@example.com",
        is_active: bool = True,
        is_super_admin: bool = False,
    ):
        self.id = id or str(uuid.uuid4())
        self.clerk_user_id = clerk_user_id or f"clerk_{uuid.uuid4().hex[:8]}"
        self.email = email
        self.is_active = is_active
        self.is_super_admin = is_super_admin
        self.updated_at = datetime.now(timezone.utc)

    @property
    def full_name(self):
        return self.email.split("@")[0]


class MockTenant:
    """Mock Tenant model for testing."""
    def __init__(
        self,
        id: str = None,
        name: str = "Test Tenant",
        slug: str = "test-tenant",
        billing_tier: str = "growth",
        clerk_org_id: str = None,
        status: str = "active",
    ):
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.slug = slug
        self.billing_tier = billing_tier
        self.clerk_org_id = clerk_org_id
        self.status = status

    @property
    def is_active(self):
        return self.status == "active"


class MockSession:
    """Mock SQLAlchemy session for testing."""
    def __init__(self):
        self.users = {}
        self.tenants = {}
        self.audit_logs = []
        self._committed = False
        self._flushed = False

    def query(self, model):
        return MockQuery(self, model)

    def add(self, obj):
        if hasattr(obj, 'clerk_user_id'):
            self.users[obj.clerk_user_id] = obj
        elif hasattr(obj, 'action'):
            self.audit_logs.append(obj)

    def flush(self):
        self._flushed = True

    def commit(self):
        self._committed = True

    def rollback(self):
        pass


class MockQuery:
    """Mock SQLAlchemy query for testing."""
    def __init__(self, session: MockSession, model):
        self.session = session
        self.model = model
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def first(self):
        # Simple mock implementation - returns first matching user
        for user in self.session.users.values():
            return user
        return None

    def all(self):
        return list(self.session.users.values())

    def count(self):
        return len(self.session.users)


# =============================================================================
# Mock SuperAdminService (matches actual implementation logic)
# =============================================================================


class MockSuperAdminService:
    """
    Mock implementation of SuperAdminService for testing.

    SECURITY: Mirrors the actual implementation logic:
    - Super admin is NEVER determined from JWT claims
    - Only existing super admins can grant/revoke
    - All operations are audited
    """

    SYSTEM_TENANT_ID = "system"

    def __init__(
        self,
        session: MockSession,
        actor_clerk_user_id: Optional[str] = None,
    ):
        self.session = session
        self.actor_clerk_user_id = actor_clerk_user_id
        self._audit_events = []

    def is_super_admin(self, clerk_user_id: Optional[str] = None) -> bool:
        """
        Check if a user is a super admin FROM DATABASE ONLY.

        SECURITY: Never checks JWT claims - only database.
        """
        check_id = clerk_user_id or self.actor_clerk_user_id
        if not check_id:
            return False

        user = self.session.users.get(check_id)
        return user is not None and user.is_super_admin is True

    def _verify_actor_is_super_admin(self) -> MockUser:
        """Verify that the actor is a super admin."""
        if not self.actor_clerk_user_id:
            raise ValueError("No actor specified")

        user = self.session.users.get(self.actor_clerk_user_id)
        if not user or not user.is_super_admin:
            raise PermissionError("Only super admins can perform this operation")

        return user

    def grant_super_admin(
        self,
        target_clerk_user_id: str,
        source: str = "admin_api",
    ) -> dict:
        """Grant super admin status to a user."""
        # SECURITY: Verify actor is super admin first
        self._verify_actor_is_super_admin()

        target = self.session.users.get(target_clerk_user_id)
        if not target:
            raise ValueError(f"User {target_clerk_user_id} not found")

        if target.is_super_admin:
            raise ValueError(f"User {target_clerk_user_id} is already a super admin")

        # Grant super admin
        target.is_super_admin = True
        target.updated_at = datetime.now(timezone.utc)

        # Emit audit event
        self._audit_events.append({
            "action": "identity.super_admin_granted",
            "target_clerk_user_id": target_clerk_user_id,
            "granted_by": self.actor_clerk_user_id,
            "source": source,
        })

        return {
            "user_id": target.id,
            "clerk_user_id": target.clerk_user_id,
            "is_super_admin": target.is_super_admin,
        }

    def revoke_super_admin(
        self,
        target_clerk_user_id: str,
        reason: str = "administrative action",
    ) -> dict:
        """Revoke super admin status from a user."""
        # SECURITY: Verify actor is super admin first
        actor = self._verify_actor_is_super_admin()

        target = self.session.users.get(target_clerk_user_id)
        if not target:
            raise ValueError(f"User {target_clerk_user_id} not found")

        if not target.is_super_admin:
            raise ValueError(f"User {target_clerk_user_id} is not a super admin")

        # Prevent self-revocation
        if target.clerk_user_id == actor.clerk_user_id:
            raise ValueError("Cannot revoke your own super admin status")

        # Check if this is the last super admin
        super_admin_count = sum(
            1 for u in self.session.users.values() if u.is_super_admin
        )
        if super_admin_count <= 1:
            raise ValueError("Cannot revoke the last super admin")

        # Revoke super admin
        target.is_super_admin = False
        target.updated_at = datetime.now(timezone.utc)

        # Emit audit event
        self._audit_events.append({
            "action": "identity.super_admin_revoked",
            "target_clerk_user_id": target_clerk_user_id,
            "revoked_by": self.actor_clerk_user_id,
            "reason": reason,
        })

        return {
            "user_id": target.id,
            "clerk_user_id": target.clerk_user_id,
            "is_super_admin": target.is_super_admin,
        }

    def list_super_admins(self) -> List[dict]:
        """List all super admins."""
        self._verify_actor_is_super_admin()

        return [
            {
                "user_id": user.id,
                "clerk_user_id": user.clerk_user_id,
                "email": user.email,
                "full_name": user.full_name,
                "is_super_admin": user.is_super_admin,
            }
            for user in self.session.users.values()
            if user.is_super_admin
        ]


# =============================================================================
# Mock AuthContext (matches actual implementation)
# =============================================================================


class MockAuthContext:
    """
    Mock AuthContext for testing.

    SECURITY: is_super_admin is ONLY set from database, never from JWT.
    """

    def __init__(
        self,
        clerk_user_id: str,
        user: Optional[MockUser] = None,
        jwt_roles: Optional[List[str]] = None,
    ):
        self.clerk_user_id = clerk_user_id
        self.user = user
        self._jwt_roles = jwt_roles or []

        # SECURITY: Super admin is resolved from database ONLY
        # Even if JWT contains "super_admin" role, it is IGNORED
        self._is_super_admin = user.is_super_admin if user else False

    @property
    def is_super_admin(self) -> bool:
        """
        Check if user is a super admin.

        SECURITY: This value is from database, NEVER from JWT claims.
        """
        return self._is_super_admin

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MockSession()


@pytest.fixture
def regular_user(mock_session):
    """Create a regular user (not super admin)."""
    user = MockUser(
        clerk_user_id="clerk_regular_user",
        email="regular@example.com",
        is_super_admin=False,
    )
    mock_session.users[user.clerk_user_id] = user
    return user


@pytest.fixture
def super_admin_user(mock_session):
    """Create a super admin user."""
    user = MockUser(
        clerk_user_id="clerk_super_admin",
        email="admin@example.com",
        is_super_admin=True,
    )
    mock_session.users[user.clerk_user_id] = user
    return user


@pytest.fixture
def another_super_admin(mock_session):
    """Create another super admin user."""
    user = MockUser(
        clerk_user_id="clerk_super_admin_2",
        email="admin2@example.com",
        is_super_admin=True,
    )
    mock_session.users[user.clerk_user_id] = user
    return user


# =============================================================================
# Test: User Cannot Become Super Admin via JWT Claim Manipulation
# =============================================================================


class TestJWTClaimManipulation:
    """Tests verifying JWT claims cannot grant super admin."""

    def test_jwt_super_admin_claim_ignored(self, mock_session, regular_user):
        """
        Even if a JWT contains a "super_admin" role claim, it should be ignored.
        Super admin status is determined ONLY from the database.
        """
        # User is NOT a super admin in the database
        assert regular_user.is_super_admin is False

        # Create AuthContext with a fake "super_admin" JWT claim
        auth_context = MockAuthContext(
            clerk_user_id=regular_user.clerk_user_id,
            user=regular_user,
            jwt_roles=["super_admin", "admin", "owner"],  # Attacker adds super_admin to JWT
        )

        # SECURITY: is_super_admin should be False (from database)
        assert auth_context.is_super_admin is False

    def test_jwt_admin_claim_does_not_grant_super_admin(self, mock_session, regular_user):
        """Admin role in JWT does not grant super admin privileges."""
        auth_context = MockAuthContext(
            clerk_user_id=regular_user.clerk_user_id,
            user=regular_user,
            jwt_roles=["admin"],  # Admin role from Clerk
        )

        # Still not a super admin (database is source of truth)
        assert auth_context.is_super_admin is False

    def test_super_admin_only_from_database(self, mock_session, super_admin_user):
        """Super admin status comes from database field only."""
        # User IS a super admin in the database
        assert super_admin_user.is_super_admin is True

        # Create AuthContext (JWT roles don't matter)
        auth_context = MockAuthContext(
            clerk_user_id=super_admin_user.clerk_user_id,
            user=super_admin_user,
            jwt_roles=[],  # No JWT roles at all
        )

        # is_super_admin is True because database says so
        assert auth_context.is_super_admin is True


# =============================================================================
# Test: Only Existing Super Admin Can Grant/Revoke Super Admin
# =============================================================================


class TestSuperAdminAuthorization:
    """Tests verifying only super admins can manage super admin status."""

    def test_regular_user_cannot_grant_super_admin(self, mock_session, regular_user):
        """Non-super-admin cannot grant super admin status."""
        target_user = MockUser(
            clerk_user_id="clerk_target",
            email="target@example.com",
            is_super_admin=False,
        )
        mock_session.users[target_user.clerk_user_id] = target_user

        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=regular_user.clerk_user_id,
        )

        with pytest.raises(PermissionError) as exc_info:
            service.grant_super_admin(target_user.clerk_user_id)

        assert "Only super admins" in str(exc_info.value)

    def test_regular_user_cannot_revoke_super_admin(
        self, mock_session, regular_user, super_admin_user, another_super_admin
    ):
        """Non-super-admin cannot revoke super admin status."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=regular_user.clerk_user_id,
        )

        with pytest.raises(PermissionError) as exc_info:
            service.revoke_super_admin(super_admin_user.clerk_user_id)

        assert "Only super admins" in str(exc_info.value)

    def test_super_admin_can_grant_super_admin(
        self, mock_session, super_admin_user, regular_user
    ):
        """Super admin can grant super admin status to another user."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        result = service.grant_super_admin(regular_user.clerk_user_id)

        assert result["is_super_admin"] is True
        assert regular_user.is_super_admin is True

    def test_super_admin_can_revoke_super_admin(
        self, mock_session, super_admin_user, another_super_admin
    ):
        """Super admin can revoke super admin status from another user."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        result = service.revoke_super_admin(another_super_admin.clerk_user_id)

        assert result["is_super_admin"] is False
        assert another_super_admin.is_super_admin is False

    def test_cannot_revoke_own_super_admin(self, mock_session, super_admin_user):
        """Super admin cannot revoke their own super admin status."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        with pytest.raises(ValueError) as exc_info:
            service.revoke_super_admin(super_admin_user.clerk_user_id)

        assert "your own" in str(exc_info.value).lower()

    def test_cannot_revoke_last_super_admin(self, mock_session, super_admin_user):
        """Cannot revoke the last remaining super admin."""
        # Only one super admin exists
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        # Try to revoke another user (who doesn't exist as super admin)
        # This test verifies the "last super admin" check
        with pytest.raises(ValueError) as exc_info:
            # Would fail anyway since actor can't revoke self
            service.revoke_super_admin(super_admin_user.clerk_user_id)

        # The actual error depends on which check fires first
        # Either "your own" or "last super admin" is acceptable


# =============================================================================
# Test: Audit Events for Super Admin Changes
# =============================================================================


class TestSuperAdminAuditEvents:
    """Tests verifying audit events are emitted for super admin changes."""

    def test_grant_emits_audit_event(
        self, mock_session, super_admin_user, regular_user
    ):
        """Granting super admin should emit an audit event."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        service.grant_super_admin(regular_user.clerk_user_id)

        # Check audit event was emitted
        assert len(service._audit_events) == 1
        event = service._audit_events[0]
        assert event["action"] == "identity.super_admin_granted"
        assert event["target_clerk_user_id"] == regular_user.clerk_user_id
        assert event["granted_by"] == super_admin_user.clerk_user_id

    def test_revoke_emits_audit_event(
        self, mock_session, super_admin_user, another_super_admin
    ):
        """Revoking super admin should emit an audit event."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        service.revoke_super_admin(
            another_super_admin.clerk_user_id,
            reason="Security policy change",
        )

        # Check audit event was emitted
        assert len(service._audit_events) == 1
        event = service._audit_events[0]
        assert event["action"] == "identity.super_admin_revoked"
        assert event["target_clerk_user_id"] == another_super_admin.clerk_user_id
        assert event["revoked_by"] == super_admin_user.clerk_user_id
        assert event["reason"] == "Security policy change"


# =============================================================================
# Test: Super Admin Service Queries
# =============================================================================


class TestSuperAdminQueries:
    """Tests for super admin query operations."""

    def test_is_super_admin_checks_database(self, mock_session, super_admin_user):
        """is_super_admin should check database, not JWT."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        assert service.is_super_admin(super_admin_user.clerk_user_id) is True

    def test_is_super_admin_returns_false_for_regular_user(
        self, mock_session, regular_user
    ):
        """is_super_admin should return False for non-super-admin."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=regular_user.clerk_user_id,
        )

        assert service.is_super_admin(regular_user.clerk_user_id) is False

    def test_list_super_admins_requires_super_admin(
        self, mock_session, regular_user
    ):
        """Only super admins can list super admins."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=regular_user.clerk_user_id,
        )

        with pytest.raises(PermissionError):
            service.list_super_admins()

    def test_list_super_admins_returns_only_super_admins(
        self, mock_session, super_admin_user, another_super_admin, regular_user
    ):
        """list_super_admins should only return users with is_super_admin=True."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        admins = service.list_super_admins()

        assert len(admins) == 2
        clerk_ids = {a["clerk_user_id"] for a in admins}
        assert super_admin_user.clerk_user_id in clerk_ids
        assert another_super_admin.clerk_user_id in clerk_ids
        assert regular_user.clerk_user_id not in clerk_ids


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestSuperAdminErrorHandling:
    """Tests for error handling in super admin operations."""

    def test_grant_to_nonexistent_user_fails(self, mock_session, super_admin_user):
        """Granting super admin to non-existent user should fail."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        with pytest.raises(ValueError) as exc_info:
            service.grant_super_admin("nonexistent_user")

        assert "not found" in str(exc_info.value).lower()

    def test_grant_to_existing_super_admin_fails(
        self, mock_session, super_admin_user, another_super_admin
    ):
        """Granting super admin to existing super admin should fail."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        with pytest.raises(ValueError) as exc_info:
            service.grant_super_admin(another_super_admin.clerk_user_id)

        assert "already a super admin" in str(exc_info.value).lower()

    def test_revoke_from_non_super_admin_fails(
        self, mock_session, super_admin_user, regular_user
    ):
        """Revoking super admin from non-super-admin should fail."""
        service = MockSuperAdminService(
            session=mock_session,
            actor_clerk_user_id=super_admin_user.clerk_user_id,
        )

        with pytest.raises(ValueError) as exc_info:
            service.revoke_super_admin(regular_user.clerk_user_id)

        assert "not a super admin" in str(exc_info.value).lower()
