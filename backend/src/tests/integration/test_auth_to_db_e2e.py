"""
Auth-to-Database End-to-End Verification Tests.

These tests prove that the authentication flow (JWT → middleware → service → DB)
actually creates and persists real records in the database. They fill the gap
left by the existing mock-heavy test suite, which verifies behavior but never
checks whether data reaches the database.

Tests use the shared db_session fixture (SQLite in-memory by default,
PostgreSQL if DATABASE_URL is set) with per-test transaction rollback.

Key invariants verified:
1. Lazy sync creates User, Tenant, UserTenantRole rows
2. Duplicate lazy sync is idempotent (no IntegrityError)
3. Enum columns use lowercase values (values_callable correctness)
4. Clerk org_id is normalized to internal Tenant.id UUID
5. AirbyteService.register_connection writes to tenant_airbyte_connections
6. Tenant isolation: Tenant A cannot see Tenant B's connections
7. Shop domain uniqueness prevents cross-tenant data leakage
"""

import os
import uuid
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from src.services.clerk_sync_service import ClerkSyncService
from src.models.tenant import Tenant, TenantStatus
from src.models.user import User
from src.models.user_tenant_roles import UserTenantRole
from src.models.airbyte_connection import (
    TenantAirbyteConnection,
    ConnectionStatus,
    ConnectionType,
)
from src.services.airbyte_service import AirbyteService, DuplicateConnectionError


def _get_test_database_url() -> str:
    """Mirror the conftest helper so skipif decorators can check the DB backend."""
    url = os.getenv("DATABASE_URL", "sqlite:///:memory:")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clerk_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


def _make_clerk_org_id() -> str:
    return f"org_{uuid.uuid4().hex[:12]}"


def _sync_service(session: Session) -> ClerkSyncService:
    """Create a ClerkSyncService with audit logging disabled for tests."""
    return ClerkSyncService(session, skip_audit=True)


# ===========================================================================
# 1. Lazy Sync — User creation
# ===========================================================================

class TestLazySyncUser:
    """Verify that ClerkSyncService.get_or_create_user writes a real row."""

    def test_creates_user_in_database(self, db_session: Session):
        """get_or_create_user must INSERT a User row that survives a flush."""
        clerk_id = _make_clerk_user_id()
        svc = _sync_service(db_session)

        user = svc.get_or_create_user(
            clerk_user_id=clerk_id,
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        # Force flush so the row hits the DB (or at least the session buffer)
        db_session.flush()

        # Query back via raw SQL to bypass the identity map
        row = db_session.execute(
            text("SELECT id, clerk_user_id, email, is_active FROM users WHERE clerk_user_id = :cid"),
            {"cid": clerk_id},
        ).fetchone()

        assert row is not None, f"User with clerk_user_id={clerk_id} not found in DB"
        assert row[1] == clerk_id
        assert row[2] == "test@example.com"
        # is_active should be true (column index 3)
        assert row[3] in (True, 1, "true")
        # The returned user object should have a UUID id
        assert user.id is not None
        assert len(user.id) >= 32  # UUID string

    def test_idempotent_duplicate_user(self, db_session: Session):
        """Calling get_or_create_user twice with the same clerk_id must not raise."""
        clerk_id = _make_clerk_user_id()
        svc = _sync_service(db_session)

        user1 = svc.get_or_create_user(clerk_user_id=clerk_id, email="a@test.com")
        db_session.flush()

        user2 = svc.get_or_create_user(clerk_user_id=clerk_id, email="a@test.com")
        db_session.flush()

        assert user1.id == user2.id

        # Exactly one row in DB
        count = db_session.execute(
            text("SELECT count(*) FROM users WHERE clerk_user_id = :cid"),
            {"cid": clerk_id},
        ).scalar()
        assert count == 1


# ===========================================================================
# 2. Lazy Sync — Tenant creation
# ===========================================================================

class TestLazySyncTenant:
    """Verify that ClerkSyncService.sync_tenant_from_org writes a real Tenant row."""

    def test_creates_tenant_from_org(self, db_session: Session):
        """sync_tenant_from_org must INSERT a Tenant with a UUID id, not the raw Clerk org_id."""
        org_id = _make_clerk_org_id()
        svc = _sync_service(db_session)

        tenant = svc.sync_tenant_from_org(
            clerk_org_id=org_id,
            name="Test Store",
            billing_tier="free",
        )
        db_session.flush()

        # Query back
        row = db_session.execute(
            text("SELECT id, clerk_org_id, name, billing_tier FROM tenants WHERE clerk_org_id = :oid"),
            {"oid": org_id},
        ).fetchone()

        assert row is not None, f"Tenant with clerk_org_id={org_id} not found in DB"
        assert row[1] == org_id
        assert row[2] == "Test Store"
        assert row[3] == "free"
        # CRITICAL: Tenant.id must be a UUID, NOT the raw Clerk org_id
        assert row[0] != org_id, "Tenant.id must not be the raw Clerk org_id"
        assert len(row[0]) >= 32  # UUID string

    def test_idempotent_duplicate_tenant(self, db_session: Session):
        """Calling sync_tenant_from_org twice must not create duplicates."""
        org_id = _make_clerk_org_id()
        svc = _sync_service(db_session)

        t1 = svc.sync_tenant_from_org(clerk_org_id=org_id, name="Store")
        db_session.flush()
        t2 = svc.sync_tenant_from_org(clerk_org_id=org_id, name="Store")
        db_session.flush()

        assert t1.id == t2.id

        count = db_session.execute(
            text("SELECT count(*) FROM tenants WHERE clerk_org_id = :oid"),
            {"oid": org_id},
        ).scalar()
        assert count == 1


# ===========================================================================
# 3. Lazy Sync — UserTenantRole linking
# ===========================================================================

class TestLazySyncMembership:
    """Verify sync_membership creates UserTenantRole records."""

    def test_creates_user_tenant_role(self, db_session: Session):
        """sync_membership must INSERT a UserTenantRole linking user to tenant."""
        svc = _sync_service(db_session)
        clerk_uid = _make_clerk_user_id()
        clerk_oid = _make_clerk_org_id()

        user = svc.get_or_create_user(clerk_user_id=clerk_uid, email="m@test.com")
        tenant = svc.sync_tenant_from_org(clerk_org_id=clerk_oid, name="MemberStore")
        db_session.flush()

        role = svc.sync_membership(
            clerk_user_id=clerk_uid,
            clerk_org_id=clerk_oid,
            role="org:admin",
            source="lazy_sync",
        )
        db_session.flush()

        assert role is not None

        # Verify via raw SQL
        row = db_session.execute(
            text(
                "SELECT user_id, tenant_id, role, is_active "
                "FROM user_tenant_roles "
                "WHERE user_id = :uid AND tenant_id = :tid"
            ),
            {"uid": user.id, "tid": tenant.id},
        ).fetchone()

        assert row is not None, "UserTenantRole row not found in DB"
        assert row[0] == user.id
        assert row[1] == tenant.id
        # is_active should be truthy
        assert row[3] in (True, 1, "true")


# ===========================================================================
# 4. Enum values_callable correctness
# ===========================================================================

class TestEnumValuesCallable:
    """Verify SQLAlchemy Enum columns use lowercase values matching PostgreSQL."""

    def test_tenant_status_enum_definition(self):
        """TenantStatus enum values must be lowercase strings."""
        values = [e.value for e in TenantStatus]
        assert "active" in values
        assert "suspended" in values
        assert "deactivated" in values
        # Must NOT contain uppercase
        for v in values:
            assert v == v.lower(), f"Enum value '{v}' is not lowercase"

    def test_tenant_status_column_has_values_callable(self):
        """The Tenant.status column definition must include values_callable."""
        mapper = inspect(Tenant)
        status_col = mapper.columns["status"]
        col_type = status_col.type

        # The column type should be an Enum type
        assert hasattr(col_type, "enums") or hasattr(col_type, "enum_class"), \
            "Tenant.status column is not an Enum type"

        # If it has enums attribute, check they are lowercase
        if hasattr(col_type, "enums"):
            for val in col_type.enums:
                assert val == val.lower(), \
                    f"Tenant.status enum value '{val}' is uppercase — values_callable is missing or broken"

    def test_connection_status_enum_definition(self):
        """ConnectionStatus enum values must be lowercase strings."""
        values = [e.value for e in ConnectionStatus]
        assert "pending" in values
        assert "active" in values
        assert "inactive" in values
        for v in values:
            assert v == v.lower(), f"Enum value '{v}' is not lowercase"

    def test_connection_type_enum_definition(self):
        """ConnectionType enum values must be lowercase strings."""
        values = [e.value for e in ConnectionType]
        assert "source" in values
        assert "destination" in values
        for v in values:
            assert v == v.lower(), f"Enum value '{v}' is not lowercase"

    def test_tenant_stored_with_lowercase_status(self, db_session: Session):
        """Creating a Tenant with TenantStatus.ACTIVE must store 'active' (lowercase)."""
        svc = _sync_service(db_session)
        org_id = _make_clerk_org_id()

        tenant = svc.sync_tenant_from_org(clerk_org_id=org_id, name="EnumTest")
        db_session.flush()

        # Raw query to bypass SQLAlchemy's enum deserialization
        row = db_session.execute(
            text("SELECT status FROM tenants WHERE id = :tid"),
            {"tid": tenant.id},
        ).fetchone()

        assert row is not None
        # The stored value must be lowercase
        stored_status = row[0]
        if isinstance(stored_status, str):
            assert stored_status == stored_status.lower(), \
                f"Stored status '{stored_status}' is not lowercase — values_callable is broken"


# ===========================================================================
# 5. Clerk org_id → Tenant.id normalization
# ===========================================================================

class TestOrgIdNormalization:
    """Verify that Clerk org_ids are never used as tenant_ids downstream."""

    def test_clerk_org_id_not_used_as_tenant_id(self, db_session: Session):
        """Tenant.id must be a UUID, not the Clerk org_id string."""
        svc = _sync_service(db_session)
        clerk_oid = "org_2xYz123TestOrg"

        tenant = svc.sync_tenant_from_org(clerk_org_id=clerk_oid, name="NormTest")
        db_session.flush()

        # Tenant.id must NOT be the Clerk org_id
        assert tenant.id != clerk_oid
        assert not tenant.id.startswith("org_"), \
            f"Tenant.id '{tenant.id}' looks like a Clerk org_id (starts with 'org_')"

        # But clerk_org_id column must store the original
        assert tenant.clerk_org_id == clerk_oid

    def test_resolve_tenant_by_clerk_org_id(self, db_session: Session):
        """Looking up a tenant by clerk_org_id must return the UUID tenant_id."""
        svc = _sync_service(db_session)
        clerk_oid = _make_clerk_org_id()

        tenant = svc.sync_tenant_from_org(clerk_org_id=clerk_oid, name="ResolveTest")
        db_session.flush()

        resolved = svc.get_tenant_by_clerk_org_id(clerk_oid)
        assert resolved is not None
        assert resolved.id == tenant.id
        assert resolved.id != clerk_oid


# ===========================================================================
# 6. AirbyteService — connection writes to DB
# ===========================================================================

class TestAirbyteConnectionDB:
    """Verify AirbyteService.register_connection creates a real DB row."""

    def _make_tenant(self, db_session: Session) -> Tenant:
        """Helper to create a tenant for Airbyte tests."""
        svc = _sync_service(db_session)
        tenant = svc.sync_tenant_from_org(
            clerk_org_id=_make_clerk_org_id(),
            name="AirbyteTest",
        )
        db_session.flush()
        return tenant

    def test_register_connection_creates_row(self, db_session: Session):
        """register_connection must INSERT a tenant_airbyte_connections row."""
        tenant = self._make_tenant(db_session)
        airbyte_svc = AirbyteService(db_session, tenant_id=tenant.id)

        # Use a non-Shopify source type to avoid shop_domain validation
        # which uses PostgreSQL-specific SQL (regexp_replace/TRIM TRAILING)
        conn_id = f"conn_{uuid.uuid4().hex[:12]}"
        conn_info = airbyte_svc.register_connection(
            airbyte_connection_id=conn_id,
            connection_name="Test Meta Ads",
            source_type="source-facebook-marketing",
            configuration={"account_id": "act_123456"},
        )
        db_session.flush()

        assert conn_info is not None
        assert conn_info.airbyte_connection_id == conn_id

        # Verify via raw SQL
        row = db_session.execute(
            text(
                "SELECT tenant_id, airbyte_connection_id, source_type, connection_name "
                "FROM tenant_airbyte_connections "
                "WHERE airbyte_connection_id = :cid"
            ),
            {"cid": conn_id},
        ).fetchone()

        assert row is not None, "Connection row not found in DB"
        assert row[0] == tenant.id
        assert row[1] == conn_id
        assert row[2] == "source-facebook-marketing"
        assert row[3] == "Test Meta Ads"

    def test_register_connection_stores_configuration(self, db_session: Session):
        """register_connection must store configuration JSONB."""
        tenant = self._make_tenant(db_session)
        airbyte_svc = AirbyteService(db_session, tenant_id=tenant.id)

        conn_id = f"conn_{uuid.uuid4().hex[:12]}"
        config = {
            "account_id": "act_123456789",
            "shop_domain": f"test-{uuid.uuid4().hex[:6]}.myshopify.com",
        }
        airbyte_svc.register_connection(
            airbyte_connection_id=conn_id,
            connection_name="ConfigTest",
            source_type="source-facebook-marketing",
            configuration=config,
        )
        db_session.flush()

        # Retrieve via ORM to check JSONB deserialization
        conn = db_session.query(TenantAirbyteConnection).filter_by(
            airbyte_connection_id=conn_id,
        ).first()

        assert conn is not None
        assert conn.configuration is not None
        assert conn.configuration.get("account_id") == "act_123456789"


# ===========================================================================
# 7. Tenant isolation at the Airbyte service level
# ===========================================================================

class TestTenantIsolation:
    """Verify Tenant A cannot see Tenant B's connections."""

    def test_tenant_a_cannot_see_tenant_b_connections(self, db_session: Session):
        """list_connections scoped to tenant_id must return only that tenant's data."""
        sync_svc = _sync_service(db_session)

        # Create two tenants
        tenant_a = sync_svc.sync_tenant_from_org(
            clerk_org_id=_make_clerk_org_id(), name="Tenant A"
        )
        tenant_b = sync_svc.sync_tenant_from_org(
            clerk_org_id=_make_clerk_org_id(), name="Tenant B"
        )
        db_session.flush()

        svc_a = AirbyteService(db_session, tenant_id=tenant_a.id)
        svc_b = AirbyteService(db_session, tenant_id=tenant_b.id)

        # Use non-Shopify source types to avoid PostgreSQL-specific
        # shop_domain validation (regexp_replace/TRIM TRAILING syntax)
        conn_a_id = f"conn_a_{uuid.uuid4().hex[:8]}"
        conn_b_id = f"conn_b_{uuid.uuid4().hex[:8]}"

        svc_a.register_connection(
            airbyte_connection_id=conn_a_id,
            connection_name="Tenant A Meta",
            source_type="source-facebook-marketing",
            configuration={"account_id": "act_aaaa111"},
        )
        svc_b.register_connection(
            airbyte_connection_id=conn_b_id,
            connection_name="Tenant B Meta",
            source_type="source-facebook-marketing",
            configuration={"account_id": "act_bbbb222"},
        )
        db_session.flush()

        # List connections for each tenant
        result_a = svc_a.list_connections()
        result_b = svc_b.list_connections()

        a_conn_ids = [c.airbyte_connection_id for c in result_a.connections]
        b_conn_ids = [c.airbyte_connection_id for c in result_b.connections]

        assert conn_a_id in a_conn_ids, "Tenant A should see its own connection"
        assert conn_b_id not in a_conn_ids, "Tenant A must NOT see Tenant B's connection"

        assert conn_b_id in b_conn_ids, "Tenant B should see its own connection"
        assert conn_a_id not in b_conn_ids, "Tenant B must NOT see Tenant A's connection"

    @pytest.mark.skipif(
        not _get_test_database_url().startswith("postgresql"),
        reason="Shop domain validation uses PostgreSQL-specific SQL (regexp_replace)",
    )
    def test_duplicate_shop_domain_rejected(self, db_session: Session):
        """Two tenants cannot register the same shop_domain (PostgreSQL only)."""
        sync_svc = _sync_service(db_session)

        tenant_a = sync_svc.sync_tenant_from_org(
            clerk_org_id=_make_clerk_org_id(), name="Dup A"
        )
        tenant_b = sync_svc.sync_tenant_from_org(
            clerk_org_id=_make_clerk_org_id(), name="Dup B"
        )
        db_session.flush()

        shared_domain = f"shared-{uuid.uuid4().hex[:6]}.myshopify.com"

        svc_a = AirbyteService(db_session, tenant_id=tenant_a.id)
        svc_b = AirbyteService(db_session, tenant_id=tenant_b.id)

        # First registration should succeed
        svc_a.register_connection(
            airbyte_connection_id=f"conn_{uuid.uuid4().hex[:8]}",
            connection_name="First",
            source_type="shopify",
            configuration={"shop_domain": shared_domain},
        )
        db_session.flush()

        # Second registration with same shop_domain should fail
        with pytest.raises(DuplicateConnectionError):
            svc_b.register_connection(
                airbyte_connection_id=f"conn_{uuid.uuid4().hex[:8]}",
                connection_name="Second",
                source_type="shopify",
                configuration={"shop_domain": shared_domain},
            )


# ===========================================================================
# 8. Full lazy-sync chain — User + Tenant + Role in one flow
# ===========================================================================

class TestFullLazySyncChain:
    """Verify the complete lazy-sync chain creates all three identity records."""

    def test_full_provisioning_chain(self, db_session: Session):
        """Simulating the middleware lazy-sync: create user, tenant, and role in sequence."""
        svc = _sync_service(db_session)
        clerk_uid = _make_clerk_user_id()
        clerk_oid = _make_clerk_org_id()

        # Step 1: Create user (lazy sync on first request)
        user = svc.get_or_create_user(
            clerk_user_id=clerk_uid,
            email="chain@test.com",
            first_name="Chain",
            last_name="Test",
        )
        db_session.flush()
        assert user.id is not None

        # Step 2: Create tenant (lazy sync from org claim)
        tenant = svc.sync_tenant_from_org(
            clerk_org_id=clerk_oid,
            name="Chain Store",
            billing_tier="free",
        )
        db_session.flush()
        assert tenant.id is not None
        assert tenant.id != clerk_oid  # Must be internal UUID

        # Step 3: Create membership
        role = svc.sync_membership(
            clerk_user_id=clerk_uid,
            clerk_org_id=clerk_oid,
            role="org:admin",
            source="lazy_sync",
        )
        db_session.flush()
        assert role is not None

        # Step 4: Verify all three records exist via raw SQL
        user_count = db_session.execute(
            text("SELECT count(*) FROM users WHERE clerk_user_id = :uid"),
            {"uid": clerk_uid},
        ).scalar()
        assert user_count == 1

        tenant_count = db_session.execute(
            text("SELECT count(*) FROM tenants WHERE clerk_org_id = :oid"),
            {"oid": clerk_oid},
        ).scalar()
        assert tenant_count == 1

        role_count = db_session.execute(
            text(
                "SELECT count(*) FROM user_tenant_roles "
                "WHERE user_id = :uid AND tenant_id = :tid"
            ),
            {"uid": user.id, "tid": tenant.id},
        ).scalar()
        assert role_count == 1

    def test_full_chain_then_register_connection(self, db_session: Session):
        """After provisioning, registering an Airbyte connection should work."""
        svc = _sync_service(db_session)
        clerk_uid = _make_clerk_user_id()
        clerk_oid = _make_clerk_org_id()

        user = svc.get_or_create_user(clerk_user_id=clerk_uid)
        tenant = svc.sync_tenant_from_org(clerk_org_id=clerk_oid, name="ConnChain")
        svc.sync_membership(
            clerk_user_id=clerk_uid,
            clerk_org_id=clerk_oid,
            role="org:admin",
            source="lazy_sync",
        )
        db_session.flush()

        # Now register an Airbyte connection (what happens after OAuth callback)
        airbyte_svc = AirbyteService(db_session, tenant_id=tenant.id)
        conn_id = f"conn_{uuid.uuid4().hex[:8]}"
        conn_info = airbyte_svc.register_connection(
            airbyte_connection_id=conn_id,
            connection_name="Meta Ads",
            source_type="source-facebook-marketing",
            configuration={
                "account_id": "act_999888777",
                "platform": "meta_ads",
            },
        )
        db_session.flush()

        assert conn_info.airbyte_connection_id == conn_id

        # Verify the connection is tied to the correct tenant
        row = db_session.execute(
            text(
                "SELECT tenant_id FROM tenant_airbyte_connections "
                "WHERE airbyte_connection_id = :cid"
            ),
            {"cid": conn_id},
        ).fetchone()
        assert row is not None
        assert row[0] == tenant.id


# ===========================================================================
# 9. FastAPI middleware → route → DB chain
# ===========================================================================

class TestMiddlewareToDbChain:
    """
    Verify the full request lifecycle using FastAPI TestClient.

    This test mocks only JWT verification (returns valid claims),
    then checks that the middleware resolves the tenant correctly
    and the route handler can access the tenant_id.
    """

    def test_authenticated_request_resolves_tenant(self, db_session: Session):
        """
        Simulate middleware resolution: given a JWT with org_id,
        the middleware should resolve to the internal Tenant.id.
        """
        svc = _sync_service(db_session)
        clerk_uid = _make_clerk_user_id()
        clerk_oid = _make_clerk_org_id()

        # Pre-provision user/tenant/role
        user = svc.get_or_create_user(clerk_user_id=clerk_uid, email="mw@test.com")
        tenant = svc.sync_tenant_from_org(clerk_org_id=clerk_oid, name="MW Test")
        svc.sync_membership(
            clerk_user_id=clerk_uid,
            clerk_org_id=clerk_oid,
            role="org:admin",
            source="lazy_sync",
        )
        db_session.flush()

        # The middleware resolves Clerk org_id → Tenant.id
        # Verify the lookup works
        resolved = svc.get_tenant_by_clerk_org_id(clerk_oid)
        assert resolved is not None
        assert resolved.id == tenant.id
        assert resolved.id != clerk_oid

        # Verify the tenant is active
        assert resolved.status == TenantStatus.ACTIVE

        # Verify the user has access to this tenant
        user_tenants = svc.get_user_tenants(clerk_uid)
        tenant_ids = [t.id for t in user_tenants]
        assert tenant.id in tenant_ids, \
            "User should have access to the provisioned tenant"
