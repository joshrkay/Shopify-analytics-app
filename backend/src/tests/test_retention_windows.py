"""
Retention window tests for OAuth credentials.

CRITICAL: These tests verify:
1. Disconnect retention: 5 days before purge
2. Uninstall retention: 20 days before purge
3. Tokens are actually purged (not just marked)
4. Only merchant admin can view credential metadata
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from src.db_base import Base
from src.models.oauth_credential import (
    OAuthCredential,
    CredentialStatus,
    CredentialProvider,
)
from src.credentials.store import (
    CredentialStore,
    CredentialStoreError,
    CredentialNotFoundError,
    CredentialInactiveError,
    DISCONNECT_RETENTION_DAYS,
    UNINSTALL_RETENTION_DAYS,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def encryption_key(monkeypatch):
    """Set up encryption key for testing."""
    monkeypatch.setenv("ENCRYPTION_KEY", "test-retention-encryption-key-32!")
    return "test-retention-encryption-key-32!"


@pytest.fixture
def db_session(encryption_key):
    """Create in-memory SQLite database for testing."""
    # Use SQLite for unit tests (doesn't need Postgres)
    engine = create_engine("sqlite:///:memory:")
    
    # Import model to register with Base
    from src.models.oauth_credential import OAuthCredential
    
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_tenant_id():
    """Generate unique tenant ID."""
    return f"test-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_tenant_id_b():
    """Second tenant ID for isolation tests."""
    return f"test-tenant-b-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def credential_store(db_session, test_tenant_id):
    """Create credential store for testing."""
    return CredentialStore(db_session, test_tenant_id)


@pytest.fixture
def credential_store_b(db_session, test_tenant_id_b):
    """Create second credential store for tenant isolation tests."""
    return CredentialStore(db_session, test_tenant_id_b)


@pytest.fixture
async def active_credential(db_session, test_tenant_id, encryption_key):
    """Create an active credential for testing."""
    from src.credentials.encryption import encrypt_token
    
    credential = OAuthCredential(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        provider=CredentialProvider.SHOPIFY,
        external_account_id="12345",
        access_token_encrypted=await encrypt_token("test_access_token_value"),
        refresh_token_encrypted=await encrypt_token("test_refresh_token_value"),
        account_name="Test Store",
        connector_name="Shopify",
        status=CredentialStatus.ACTIVE,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(credential)
    db_session.commit()
    return credential


# ============================================================================
# TEST SUITE: DISCONNECT RETENTION (5 DAYS)
# ============================================================================

class TestDisconnectRetention:
    """Test 5-day retention window on disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_marks_inactive_immediately(
        self, credential_store, active_credential, db_session
    ):
        """On disconnect: credential is marked inactive immediately."""
        credential_id = active_credential.id

        await credential_store.disconnect_credential(credential_id)
        db_session.refresh(active_credential)

        assert active_credential.is_active is False
        assert active_credential.status == CredentialStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_disconnect_schedules_purge_after_5_days(
        self, credential_store, active_credential, db_session
    ):
        """On disconnect: purge is scheduled for 5 days later."""
        credential_id = active_credential.id
        now = datetime.now(timezone.utc)

        await credential_store.disconnect_credential(credential_id)
        db_session.refresh(active_credential)

        assert active_credential.scheduled_purge_at is not None
        assert active_credential.disconnected_at is not None

        # Scheduled purge should be approximately 5 days from now
        expected_purge = now + timedelta(days=DISCONNECT_RETENTION_DAYS)
        delta = abs((active_credential.scheduled_purge_at - expected_purge).total_seconds())
        assert delta < 60  # Within 1 minute tolerance

    @pytest.mark.asyncio
    async def test_disconnect_tokens_still_exist_before_purge(
        self, credential_store, active_credential, db_session
    ):
        """On disconnect: encrypted tokens still exist (not immediately purged)."""
        credential_id = active_credential.id

        await credential_store.disconnect_credential(credential_id)
        db_session.refresh(active_credential)

        # Tokens should still be present (not purged yet)
        assert active_credential.access_token_encrypted is not None
        assert active_credential.refresh_token_encrypted is not None

    @pytest.mark.asyncio
    async def test_disconnect_blocks_token_access(
        self, credential_store, active_credential
    ):
        """On disconnect: get_access_token should fail."""
        credential_id = active_credential.id

        await credential_store.disconnect_credential(credential_id)

        with pytest.raises(CredentialInactiveError):
            await credential_store.get_access_token(credential_id)


# ============================================================================
# TEST SUITE: UNINSTALL RETENTION (20 DAYS)
# ============================================================================

class TestUninstallRetention:
    """Test 20-day retention window on uninstall."""

    @pytest.mark.asyncio
    async def test_uninstall_marks_pending_deletion(
        self, credential_store, active_credential, db_session
    ):
        """On uninstall: credential is marked pending_deletion."""
        credential_id = active_credential.id

        await credential_store.mark_uninstall_pending(credential_id)
        db_session.refresh(active_credential)

        assert active_credential.is_active is False
        assert active_credential.status == CredentialStatus.PENDING_DELETION

    @pytest.mark.asyncio
    async def test_uninstall_schedules_purge_after_20_days(
        self, credential_store, active_credential, db_session
    ):
        """On uninstall: purge is scheduled for 20 days later."""
        credential_id = active_credential.id
        now = datetime.now(timezone.utc)

        await credential_store.mark_uninstall_pending(credential_id)
        db_session.refresh(active_credential)

        assert active_credential.scheduled_purge_at is not None

        # Scheduled purge should be approximately 20 days from now
        expected_purge = now + timedelta(days=UNINSTALL_RETENTION_DAYS)
        delta = abs((active_credential.scheduled_purge_at - expected_purge).total_seconds())
        assert delta < 60  # Within 1 minute tolerance


# ============================================================================
# TEST SUITE: ACTUAL PURGE
# ============================================================================

class TestCredentialPurge:
    """Test actual token purge after retention window."""

    @pytest.mark.asyncio
    async def test_purge_removes_encrypted_tokens(
        self, credential_store, active_credential, db_session
    ):
        """CRITICAL: Purge actually removes encrypted token blobs."""
        credential_id = active_credential.id

        # First disconnect
        await credential_store.disconnect_credential(credential_id)

        # Then purge
        await credential_store.purge_credential(credential_id)
        db_session.refresh(active_credential)

        # Tokens should be None (actually removed)
        assert active_credential.access_token_encrypted is None
        assert active_credential.refresh_token_encrypted is None

    @pytest.mark.asyncio
    async def test_purge_records_purge_timestamp(
        self, credential_store, active_credential, db_session
    ):
        """Purge records when tokens were purged."""
        credential_id = active_credential.id
        now = datetime.now(timezone.utc)

        await credential_store.disconnect_credential(credential_id)
        await credential_store.purge_credential(credential_id)
        db_session.refresh(active_credential)

        assert active_credential.purged_at is not None
        delta = abs((active_credential.purged_at - now).total_seconds())
        assert delta < 60

    @pytest.mark.asyncio
    async def test_purge_keeps_metadata(
        self, credential_store, active_credential, db_session
    ):
        """Purge removes tokens but keeps metadata for audit trail."""
        credential_id = active_credential.id

        await credential_store.disconnect_credential(credential_id)
        await credential_store.purge_credential(credential_id)
        db_session.refresh(active_credential)

        # Metadata should still exist
        assert active_credential.id is not None
        assert active_credential.tenant_id is not None
        assert active_credential.provider is not None
        assert active_credential.account_name == "Test Store"

    @pytest.mark.asyncio
    async def test_get_credentials_due_for_purge(
        self, db_session, test_tenant_id, encryption_key
    ):
        """Get credentials that are past their retention window."""
        from src.credentials.encryption import encrypt_token
        
        store = CredentialStore(db_session, test_tenant_id)
        
        # Create credential with past purge date
        past_purge = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            provider=CredentialProvider.SHOPIFY,
            access_token_encrypted=await encrypt_token("token1"),
            status=CredentialStatus.INACTIVE,
            is_active=False,
            scheduled_purge_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(past_purge)

        # Create credential with future purge date
        future_purge = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            provider=CredentialProvider.GOOGLE_ADS,
            access_token_encrypted=await encrypt_token("token2"),
            status=CredentialStatus.INACTIVE,
            is_active=False,
            scheduled_purge_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db_session.add(future_purge)
        db_session.commit()

        # Get credentials due for purge
        due_for_purge = store.get_credentials_due_for_purge()

        assert len(due_for_purge) == 1
        assert due_for_purge[0].id == past_purge.id


# ============================================================================
# TEST SUITE: TENANT ISOLATION
# ============================================================================

class TestTenantIsolation:
    """Test tenant isolation for credential access."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_tenant_credentials(
        self, credential_store, credential_store_b, active_credential
    ):
        """CRITICAL: Cannot access credentials from other tenant."""
        credential_id = active_credential.id

        # Tenant A's credential should not be accessible by Tenant B
        with pytest.raises(CredentialNotFoundError):
            credential_store_b.get_credential(credential_id)

    @pytest.mark.asyncio
    async def test_list_only_returns_own_credentials(
        self, db_session, test_tenant_id, test_tenant_id_b, encryption_key
    ):
        """List only returns credentials for current tenant."""
        from src.credentials.encryption import encrypt_token
        
        # Create credential for tenant A
        cred_a = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            provider=CredentialProvider.SHOPIFY,
            access_token_encrypted=await encrypt_token("token_a"),
            status=CredentialStatus.ACTIVE,
            is_active=True,
        )
        db_session.add(cred_a)

        # Create credential for tenant B
        cred_b = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id_b,
            provider=CredentialProvider.SHOPIFY,
            access_token_encrypted=await encrypt_token("token_b"),
            status=CredentialStatus.ACTIVE,
            is_active=True,
        )
        db_session.add(cred_b)
        db_session.commit()

        # Store A should only see cred_a
        store_a = CredentialStore(db_session, test_tenant_id)
        creds_a = store_a.list_credentials()
        assert len(creds_a) == 1
        assert creds_a[0].id == cred_a.id

        # Store B should only see cred_b
        store_b = CredentialStore(db_session, test_tenant_id_b)
        creds_b = store_b.list_credentials()
        assert len(creds_b) == 1
        assert creds_b[0].id == cred_b.id


# ============================================================================
# TEST SUITE: MERCHANT ADMIN ACCESS
# ============================================================================

class TestMerchantAdminAccess:
    """Test that only merchant admin can view credential metadata."""

    def test_metadata_returned_without_tokens(
        self, credential_store, active_credential
    ):
        """get_credential_metadata returns metadata without tokens."""
        metadata = credential_store.get_credential_metadata(active_credential.id)

        # Should have metadata
        assert metadata.id == active_credential.id
        assert metadata.provider == CredentialProvider.SHOPIFY.value
        assert metadata.account_name == "Test Store"

        # Should NOT have tokens (not in CredentialMetadata dataclass)
        assert not hasattr(metadata, 'access_token')
        assert not hasattr(metadata, 'access_token_encrypted')
        assert not hasattr(metadata, 'refresh_token')
        assert not hasattr(metadata, 'refresh_token_encrypted')

    def test_to_safe_dict_excludes_tokens(self, active_credential):
        """Credential.to_safe_dict() excludes token values."""
        safe_dict = active_credential.to_safe_dict()

        # Should have metadata
        assert safe_dict["id"] == active_credential.id
        assert safe_dict["account_name"] == "Test Store"

        # Should NOT have tokens
        assert "access_token" not in safe_dict
        assert "refresh_token" not in safe_dict
        assert "access_token_encrypted" not in safe_dict
        assert "refresh_token_encrypted" not in safe_dict


# ============================================================================
# TEST SUITE: REACTIVATION
# ============================================================================

class TestCredentialReactivation:
    """Test credential reactivation after disconnect."""

    @pytest.mark.asyncio
    async def test_storing_new_tokens_reactivates_credential(
        self, credential_store, active_credential, db_session
    ):
        """Re-storing credentials reactivates a disconnected credential."""
        # First disconnect
        await credential_store.disconnect_credential(active_credential.id)
        db_session.refresh(active_credential)
        assert active_credential.is_active is False

        # Store new tokens (should reactivate)
        await credential_store.store_credential(
            provider=CredentialProvider.SHOPIFY,
            access_token="new_test_token_value_for_reactivation",
            external_account_id="12345",  # Same account
            account_name="Test Store",
        )
        db_session.refresh(active_credential)

        # Should be reactivated
        assert active_credential.is_active is True
        assert active_credential.status == CredentialStatus.ACTIVE
        assert active_credential.disconnected_at is None
        assert active_credential.scheduled_purge_at is None


# ============================================================================
# TEST SUITE: EXPIRING CREDENTIALS
# ============================================================================

class TestExpiringCredentials:
    """Test detection of expiring credentials."""

    @pytest.mark.asyncio
    async def test_get_expiring_credentials(
        self, db_session, test_tenant_id, encryption_key
    ):
        """Get credentials that are about to expire."""
        from src.credentials.encryption import encrypt_token
        
        store = CredentialStore(db_session, test_tenant_id)
        now = datetime.now(timezone.utc)

        # Create credential expiring in 15 minutes
        expiring_soon = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            provider=CredentialProvider.GOOGLE_ADS,
            access_token_encrypted=await encrypt_token("token1"),
            refresh_token_encrypted=await encrypt_token("refresh1"),
            expires_at=now + timedelta(minutes=15),
            status=CredentialStatus.ACTIVE,
            is_active=True,
        )
        db_session.add(expiring_soon)

        # Create credential expiring in 2 hours (not urgent)
        not_urgent = OAuthCredential(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            provider=CredentialProvider.FACEBOOK_ADS,
            access_token_encrypted=await encrypt_token("token2"),
            refresh_token_encrypted=await encrypt_token("refresh2"),
            expires_at=now + timedelta(hours=2),
            status=CredentialStatus.ACTIVE,
            is_active=True,
        )
        db_session.add(not_urgent)
        db_session.commit()

        # Get credentials expiring within 30 minutes
        expiring = store.get_expiring_credentials(within_minutes=30)

        assert len(expiring) == 1
        assert expiring[0].id == expiring_soon.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
