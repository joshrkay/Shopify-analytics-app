"""
Tests for Platform Credentials Service.

Tests credential storage, retrieval, encryption, and validation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db_base import Base
from src.models.platform_credential import (
    PlatformCredential,
    PlatformType,
    CredentialStatus as DBCredentialStatus,
)
from src.services.platform_credentials_service import (
    PlatformCredentialsService,
    Platform,
    CredentialStatusAPI,
    CredentialValidation,
    get_platform_credentials_service,
)
from src.utils.encryption import (
    CredentialEncryptor,
    InvalidKeyError,
)


class TestPlatformCredentialsService:
    """Tests for PlatformCredentialsService."""

    @pytest.fixture
    def encryption_key(self) -> bytes:
        """Generate a valid encryption key."""
        return CredentialEncryptor.generate_key()

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database session."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @pytest.fixture
    def service(self, db_session, encryption_key: bytes) -> PlatformCredentialsService:
        """Create a credentials service instance."""
        return PlatformCredentialsService(
            db_session=db_session,
            encryption_key=encryption_key,
        )

    @pytest.fixture
    def meta_credentials(self) -> dict:
        """Sample Meta credentials."""
        return {
            "access_token": "EAABc123xyz456",
            "ad_account_id": "act_987654321",
        }

    @pytest.fixture
    def google_credentials(self) -> dict:
        """Sample Google Ads credentials."""
        return {
            "access_token": "ya29.a0AfB_byC...",
            "refresh_token": "1//0dXYZ...",
            "client_id": "123456789.apps.googleusercontent.com",
            "client_secret": "GOCSPX-abc123",
            "developer_token": "aBcDeFgHiJkLmNoP",
            "customer_id": "1234567890",
            "login_customer_id": "9876543210",
        }

    @pytest.fixture
    def shopify_credentials(self) -> dict:
        """Sample Shopify credentials."""
        return {
            "access_token": "shpat_abc123xyz789",
            "shop_domain": "my-store.myshopify.com",
        }

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_init_with_encryption_key(self, db_session, encryption_key: bytes):
        """Test service initializes with provided encryption key."""
        service = PlatformCredentialsService(
            db_session=db_session,
            encryption_key=encryption_key,
        )
        assert service._encryptor is not None

    def test_init_without_key_sets_none_encryptor(self, db_session):
        """Test service initializes with None encryptor when no key provided."""
        with patch.dict("os.environ", {}, clear=True):
            service = PlatformCredentialsService(db_session=db_session)
            assert service._encryptor is None

    def test_ensure_encryptor_raises_without_key(self, db_session):
        """Test _ensure_encryptor raises when no key configured."""
        with patch.dict("os.environ", {}, clear=True):
            service = PlatformCredentialsService(db_session=db_session)
            with pytest.raises(InvalidKeyError, match="not configured"):
                service._ensure_encryptor()

    # =========================================================================
    # Store Credentials Tests
    # =========================================================================

    def test_store_meta_credentials(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test storing Meta credentials."""
        tenant_id = "tenant_123"

        result = service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
            label="Production Meta Account",
        )

        assert result is True

        # Verify record was created
        record = service._get_credential_record(tenant_id, Platform.META)
        assert record is not None
        assert record.tenant_id == tenant_id
        assert record.platform == PlatformType.META
        assert record.status == DBCredentialStatus.PENDING
        assert record.label == "Production Meta Account"

    def test_store_google_credentials(
        self,
        service: PlatformCredentialsService,
        google_credentials: dict,
    ):
        """Test storing Google Ads credentials."""
        tenant_id = "tenant_456"

        result = service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.GOOGLE,
            credentials=google_credentials,
        )

        assert result is True

        record = service._get_credential_record(tenant_id, Platform.GOOGLE)
        assert record is not None
        assert record.platform == PlatformType.GOOGLE

    def test_store_credentials_with_expiration(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test storing credentials with expiration time."""
        tenant_id = "tenant_789"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        result = service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
            expires_at=expires_at,
        )

        assert result is True

        record = service._get_credential_record(tenant_id, Platform.META)
        assert record.expires_at is not None

    def test_update_existing_credentials(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test updating existing credentials."""
        tenant_id = "tenant_update"

        # Store initial credentials
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
            label="Initial",
        )

        # Update with new credentials
        new_credentials = {
            "access_token": "new_token_xyz",
            "ad_account_id": "act_new_123",
        }
        result = service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=new_credentials,
            label="Updated",
        )

        assert result is True

        # Verify only one record exists
        record = service._get_credential_record(tenant_id, Platform.META)
        assert record.label == "Updated"

        # Verify new credentials can be retrieved
        creds = service.get_meta_credentials(tenant_id)
        # Note: credentials are in PENDING state, so this returns None
        assert creds is None  # Need to mark active first

    # =========================================================================
    # Retrieve Credentials Tests
    # =========================================================================

    def test_get_meta_credentials_when_active(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test retrieving Meta credentials when active."""
        tenant_id = "tenant_get_meta"

        # Store and activate credentials
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )
        record = service._get_credential_record(tenant_id, Platform.META)
        record.mark_active()
        service.db.commit()

        # Retrieve credentials
        creds = service.get_meta_credentials(tenant_id)

        assert creds is not None
        assert creds.access_token == meta_credentials["access_token"]
        assert creds.ad_account_id.startswith("act_")

    def test_get_google_credentials_when_active(
        self,
        service: PlatformCredentialsService,
        google_credentials: dict,
    ):
        """Test retrieving Google credentials when active."""
        tenant_id = "tenant_get_google"

        # Store and activate credentials
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.GOOGLE,
            credentials=google_credentials,
        )
        record = service._get_credential_record(tenant_id, Platform.GOOGLE)
        record.mark_active()
        service.db.commit()

        # Retrieve credentials
        creds = service.get_google_credentials(tenant_id)

        assert creds is not None
        assert creds.access_token == google_credentials["access_token"]
        assert creds.developer_token == google_credentials["developer_token"]
        assert creds.customer_id == google_credentials["customer_id"].replace("-", "")

    def test_get_shopify_credentials_when_active(
        self,
        service: PlatformCredentialsService,
        shopify_credentials: dict,
    ):
        """Test retrieving Shopify credentials when active."""
        tenant_id = "tenant_get_shopify"

        # Store and activate credentials
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.SHOPIFY,
            credentials=shopify_credentials,
        )
        record = service._get_credential_record(tenant_id, Platform.SHOPIFY)
        record.mark_active()
        service.db.commit()

        # Retrieve credentials
        creds = service.get_shopify_credentials(tenant_id)

        assert creds is not None
        assert creds.access_token == shopify_credentials["access_token"]
        assert "myshopify.com" in creds.shop_domain

    def test_get_credentials_returns_none_when_not_found(
        self,
        service: PlatformCredentialsService,
    ):
        """Test that get_credentials returns None when not found."""
        creds = service.get_meta_credentials("nonexistent_tenant")
        assert creds is None

    def test_get_credentials_returns_none_when_revoked(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test that get_credentials returns None when revoked."""
        tenant_id = "tenant_revoked"

        # Store and revoke credentials
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )
        record = service._get_credential_record(tenant_id, Platform.META)
        record.mark_revoked()
        service.db.commit()

        creds = service.get_meta_credentials(tenant_id)
        assert creds is None

    # =========================================================================
    # Revoke Credentials Tests
    # =========================================================================

    def test_revoke_credentials(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test revoking credentials."""
        tenant_id = "tenant_revoke"

        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )

        result = service.revoke_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            user_id="user_admin",
        )

        assert result is True

        record = service._get_credential_record(tenant_id, Platform.META)
        assert record.status == DBCredentialStatus.REVOKED
        assert record.revoked_by == "user_admin"
        assert record.revoked_at is not None

    def test_revoke_nonexistent_credentials_returns_false(
        self,
        service: PlatformCredentialsService,
    ):
        """Test revoking nonexistent credentials returns False."""
        result = service.revoke_credentials(
            tenant_id="nonexistent",
            platform=Platform.META,
        )
        assert result is False

    # =========================================================================
    # Delete Credentials Tests
    # =========================================================================

    def test_delete_credentials(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test deleting credentials."""
        tenant_id = "tenant_delete"

        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )

        result = service.delete_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
        )

        assert result is True

        record = service._get_credential_record(tenant_id, Platform.META)
        assert record is None

    # =========================================================================
    # Credential Status Tests
    # =========================================================================

    def test_get_credential_status_when_exists(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test getting credential status when exists."""
        tenant_id = "tenant_status"

        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
            label="Test Account",
        )

        status = service.get_credential_status(tenant_id, Platform.META)

        assert status["exists"] is True
        assert status["status"] == "pending"
        assert status["platform"] == "meta"
        assert status["label"] == "Test Account"

    def test_get_credential_status_when_missing(
        self,
        service: PlatformCredentialsService,
    ):
        """Test getting credential status when missing."""
        status = service.get_credential_status("nonexistent", Platform.META)

        assert status["exists"] is False
        assert status["status"] == "missing"
        assert status["platform"] == "meta"

    def test_check_credentials_exist(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test check_credentials_exist method."""
        tenant_id = "tenant_check"

        # Before storing
        assert service.check_credentials_exist(tenant_id, Platform.META) is False

        # Store and activate
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )
        record = service._get_credential_record(tenant_id, Platform.META)
        record.mark_active()
        service.db.commit()

        # After storing
        assert service.check_credentials_exist(tenant_id, Platform.META) is True

    # =========================================================================
    # Tenant Isolation Tests
    # =========================================================================

    def test_credentials_are_tenant_isolated(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
    ):
        """Test that credentials are isolated per tenant."""
        tenant_1 = "tenant_isolation_1"
        tenant_2 = "tenant_isolation_2"

        # Store credentials for tenant 1
        service.store_credentials(
            tenant_id=tenant_1,
            platform=Platform.META,
            credentials=meta_credentials,
        )
        record = service._get_credential_record(tenant_1, Platform.META)
        record.mark_active()
        service.db.commit()

        # Tenant 2 should not see tenant 1's credentials
        assert service.get_meta_credentials(tenant_2) is None
        assert service.check_credentials_exist(tenant_2, Platform.META) is False

        # Tenant 1 should see their credentials
        assert service.get_meta_credentials(tenant_1) is not None

    def test_multiple_platforms_per_tenant(
        self,
        service: PlatformCredentialsService,
        meta_credentials: dict,
        google_credentials: dict,
        shopify_credentials: dict,
    ):
        """Test storing credentials for multiple platforms per tenant."""
        tenant_id = "tenant_multi_platform"

        # Store credentials for all platforms
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.META,
            credentials=meta_credentials,
        )
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.GOOGLE,
            credentials=google_credentials,
        )
        service.store_credentials(
            tenant_id=tenant_id,
            platform=Platform.SHOPIFY,
            credentials=shopify_credentials,
        )

        # Activate all
        for platform in [Platform.META, Platform.GOOGLE, Platform.SHOPIFY]:
            record = service._get_credential_record(tenant_id, platform)
            record.mark_active()
        service.db.commit()

        # All should be retrievable
        assert service.get_meta_credentials(tenant_id) is not None
        assert service.get_google_credentials(tenant_id) is not None
        assert service.get_shopify_credentials(tenant_id) is not None


class TestFactoryFunction:
    """Tests for the factory function."""

    def test_get_platform_credentials_service(self):
        """Test factory function creates service."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        key = CredentialEncryptor.generate_key()
        service = get_platform_credentials_service(session, key)

        assert isinstance(service, PlatformCredentialsService)
        session.close()
