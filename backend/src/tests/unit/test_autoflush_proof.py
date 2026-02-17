"""
Proof-of-concept: demonstrates the autoflush=False bug and the db.flush() fix.

This test uses a REAL SQLAlchemy session with autoflush=False (matching production)
and SQLite in-memory to prove that:

1. session.add(user) does NOT make the user visible to filter queries
2. sync_tenant_from_org's conditional flush only fires for NEW tenants
3. sync_membership returns None when User is unflushed (THE BUG)
4. Adding db.flush() before sync_membership makes the user visible (THE FIX)

Run:
    cd backend && PYTHONPATH=. python3 -m pytest src/tests/unit/test_autoflush_proof.py -v
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.db_base import Base
from src.models.user import User
from src.models.tenant import Tenant, TenantStatus
from src.models.user_tenant_roles import UserTenantRole
from src.services.clerk_sync_service import ClerkSyncService


# ---------------------------------------------------------------------------
# Fixtures — real SQLite DB, autoflush=False (matches production session.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    """In-memory SQLite engine that lives for the whole test module."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    # Import all models so Base.metadata knows about them
    import src.models.user          # noqa: F401
    import src.models.tenant        # noqa: F401
    import src.models.user_tenant_roles  # noqa: F401
    import src.models.organization  # noqa: F401
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """
    Function-scoped session with autoflush=False — identical to production.
    Each test gets a clean transaction that is rolled back at the end.
    """
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(clerk_user_id: str) -> User:
    return User(
        id=str(uuid.uuid4()),
        clerk_user_id=clerk_user_id,
        email=f"{clerk_user_id}@test.com",
        is_active=True,
        last_synced_at=datetime.now(timezone.utc),
    )


def _make_tenant(clerk_org_id: str) -> Tenant:
    return Tenant(
        id=str(uuid.uuid4()),
        clerk_org_id=clerk_org_id,
        name=f"Tenant for {clerk_org_id}",
        billing_tier="free",
        status=TenantStatus.ACTIVE,
    )


# ===========================================================================
# TEST 1: Prove autoflush=False makes session.add() invisible to queries
# ===========================================================================

class TestAutoflushBehavior:
    """Demonstrate that autoflush=False causes the fundamental visibility issue."""

    def test_added_user_invisible_without_flush(self, db):
        """
        With autoflush=False, a user that was session.add()-ed is NOT
        visible to .filter() queries until flush() is called.

        THIS IS THE ROOT CAUSE of the 403 bug.
        """
        user = _make_user("user_invisible")
        db.add(user)

        # Query by non-PK field (same as sync_membership does)
        found = db.query(User).filter(
            User.clerk_user_id == "user_invisible"
        ).first()

        assert found is None, "User should NOT be found — autoflush=False!"

    def test_added_user_visible_after_flush(self, db):
        """
        After explicit flush(), the same query finds the user.

        THIS IS THE FIX.
        """
        user = _make_user("user_visible")
        db.add(user)

        db.flush()  # <-- THE FIX

        found = db.query(User).filter(
            User.clerk_user_id == "user_visible"
        ).first()

        assert found is not None, "User SHOULD be found after flush!"
        assert found.clerk_user_id == "user_visible"


# ===========================================================================
# TEST 2: Reproduce the exact production bug scenario
# ===========================================================================

class TestProvisioningBug:
    """
    Reproduce the exact scenario that causes the persistent 403:
    1. Tenant already exists (created by Clerk webhook)
    2. User is new (first request)
    3. sync_membership can't find the user → returns None
    """

    def test_bug_reproduced_sync_membership_returns_none(self, db):
        """
        When a Tenant was pre-created by webhook and User is new,
        sync_membership returns None because the User was only
        session.add()-ed but never flushed.

        This is the EXACT production failure path.
        """
        clerk_org_id = "org_webhook_created"
        clerk_user_id = "user_first_request"

        # Step 1: Simulate Clerk webhook pre-creating the tenant
        pre_existing_tenant = _make_tenant(clerk_org_id)
        db.add(pre_existing_tenant)
        db.commit()  # Webhook handler commits

        # Step 2: User's first authenticated request hits lazy sync
        sync = ClerkSyncService(db, skip_audit=True)

        # 2a: get_or_create_user — adds User to session (no flush)
        new_user = sync.get_or_create_user(clerk_user_id=clerk_user_id)
        assert new_user is not None, "get_or_create_user should return a User object"

        # 2b: sync_tenant_from_org — finds EXISTING tenant, skips flush
        tenant = sync.sync_tenant_from_org(
            clerk_org_id=clerk_org_id,
            name="Updated name",
            source="lazy_sync",
        )
        assert tenant.id == pre_existing_tenant.id, "Should find existing tenant"

        # 2c: sync_membership — queries for User by clerk_id → NOT FOUND
        #     THIS IS THE BUG — no flush happened since tenant existed
        membership = sync.sync_membership(
            clerk_user_id=clerk_user_id,
            clerk_org_id=clerk_org_id,
            role="org:admin",
            source="lazy_sync",
            assigned_by="system",
        )

        assert membership is None, (
            "BUG REPRODUCED: sync_membership returns None because "
            "the User was session.add()-ed but never flushed!"
        )

    def test_fix_flush_before_sync_membership(self, db):
        """
        THE FIX: Adding db.flush() before sync_membership() makes the
        User visible and allows membership creation to succeed.
        """
        clerk_org_id = "org_webhook_fixed"
        clerk_user_id = "user_fixed_request"

        # Step 1: Pre-existing tenant (from Clerk webhook)
        pre_existing_tenant = _make_tenant(clerk_org_id)
        db.add(pre_existing_tenant)
        db.commit()

        # Step 2: Lazy sync flow WITH the fix
        sync = ClerkSyncService(db, skip_audit=True)

        # 2a: Create user (in memory only)
        new_user = sync.get_or_create_user(clerk_user_id=clerk_user_id)

        # 2b: sync_tenant_from_org finds existing → no flush
        sync.sync_tenant_from_org(
            clerk_org_id=clerk_org_id,
            name="Updated name",
            source="lazy_sync",
        )

        # 2c: THE FIX — explicit flush before sync_membership
        db.flush()

        # 2d: Now sync_membership can find the User!
        membership = sync.sync_membership(
            clerk_user_id=clerk_user_id,
            clerk_org_id=clerk_org_id,
            role="org:admin",
            source="lazy_sync",
            assigned_by="system",
        )

        assert membership is not None, (
            "FIX VERIFIED: sync_membership succeeds after flush!"
        )
        assert membership.user_id == new_user.id
        assert membership.tenant_id == pre_existing_tenant.id
        assert membership.role == "MERCHANT_ADMIN"

    def test_new_tenant_works_without_explicit_flush(self, db):
        """
        When both User AND Tenant are new, sync_tenant_from_org calls
        session.flush() internally (line 413) to get the tenant.id.
        This incidentally flushes the User too, masking the bug.

        This explains why the bug ONLY affects webhook-created orgs.
        """
        clerk_org_id = "org_brand_new"
        clerk_user_id = "user_brand_new"

        # No pre-existing tenant — both are new
        sync = ClerkSyncService(db, skip_audit=True)

        # Create user (in memory)
        sync.get_or_create_user(clerk_user_id=clerk_user_id)

        # Create NEW tenant — this calls session.flush() internally!
        sync.sync_tenant_from_org(
            clerk_org_id=clerk_org_id,
            name="Brand New Tenant",
            source="lazy_sync",
        )

        # sync_membership succeeds WITHOUT explicit flush because
        # sync_tenant_from_org already flushed everything
        membership = sync.sync_membership(
            clerk_user_id=clerk_user_id,
            clerk_org_id=clerk_org_id,
            role="org:admin",
            source="lazy_sync",
            assigned_by="system",
        )

        assert membership is not None, (
            "New tenant path works because sync_tenant_from_org flushes. "
            "This is why the bug only shows for EXISTING (webhook-created) tenants."
        )
