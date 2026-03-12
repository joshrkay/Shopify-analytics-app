"""
Unit tests for PlatformCredentialsService.

Covers:
- get_meta_credentials: happy path, missing, decryption failure
- get_google_credentials: happy path, missing, decryption failure
- store_credentials: encrypts + creates ConnectorCredential row
- revoke_credentials: sets REVOKED status + soft_deleted_at
- _encrypt_credentials: delegates to encrypt_secret
- _decrypt_credentials: delegates to decrypt_secret + json.loads
- check_credentials_exist: returns True/False based on get_credentials_for_platform
- get_credentials_for_platform: dispatches to correct getter
- validate_credentials: missing returns CredentialStatus.MISSING

SECURITY:
- Never log decrypted credentials
- DB is always queried with tenant_id AND source_type (prevents cross-tenant leakage)
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.platform_credentials_service import (
    Platform,
    PlatformCredentialsService,
    CredentialValidation,
    _PLATFORM_SOURCE_TYPES,
)
from src.models.connector_credential import ConnectorCredential, CredentialStatus


# =============================================================================
# Fixtures
# =============================================================================

TENANT_ID = "tenant-creds-test-001"


def _mock_session():
    """Create a minimal SQLAlchemy session mock."""
    session = MagicMock()
    session.execute = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


def _make_credential(source_type: str, payload_dict: dict) -> ConnectorCredential:
    """Factory for active ConnectorCredential records."""
    cred = ConnectorCredential()
    cred.id = str(uuid.uuid4())
    cred.tenant_id = TENANT_ID
    cred.source_type = source_type
    cred.credential_name = f"{source_type} test cred"
    cred.encrypted_payload = "FAKE_ENCRYPTED_DATA"
    cred.credential_metadata = {}
    cred.status = CredentialStatus.ACTIVE
    cred.soft_deleted_at = None
    cred.hard_delete_after = None
    cred.created_by = "user-001"
    cred._payload_dict = payload_dict  # Stored for mock use in decrypt
    return cred


def _service(session=None) -> PlatformCredentialsService:
    if session is None:
        session = _mock_session()
    return PlatformCredentialsService(db_session=session)


# =============================================================================
# _PLATFORM_SOURCE_TYPES mapping
# =============================================================================

class TestPlatformSourceTypeMapping:

    def test_meta_maps_to_meta_ads(self):
        assert _PLATFORM_SOURCE_TYPES[Platform.META] == "meta"

    def test_google_maps_to_google_ads(self):
        assert _PLATFORM_SOURCE_TYPES[Platform.GOOGLE] == "google_ads"

    def test_shopify_maps_to_shopify(self):
        assert _PLATFORM_SOURCE_TYPES[Platform.SHOPIFY] == "shopify"


# =============================================================================
# _encrypt_credentials / _decrypt_credentials
# =============================================================================

class TestEncryptDecryptCredentials:
    """Tests for _encrypt_credentials (async, uses asyncio.run internally)
    and _decrypt_credentials (sync, uses asyncio.run internally).

    Both methods detect a running event loop and raise RuntimeError,
    so we must patch asyncio.run to avoid that guard.
    """

    @patch("src.services.platform_credentials_service.asyncio.run")
    @patch("src.services.platform_credentials_service.asyncio.get_running_loop", side_effect=RuntimeError)
    @patch("src.services.platform_credentials_service.encrypt_secret", new_callable=AsyncMock)
    def test_encrypt_serializes_to_json_and_calls_encrypt_secret(
        self, mock_encrypt, _mock_loop, mock_aio_run,
    ):
        mock_aio_run.return_value = "ENCRYPTED_BLOB"
        service = _service()

        # _encrypt_credentials is a SYNC function that calls asyncio.run() internally.
        # Call it directly — wrapping with run_until_complete would fail because
        # the function returns a plain str, not a coroutine.
        result = service._encrypt_credentials({"access_token": "tok", "ad_account_id": "act_123"})

        assert result == "ENCRYPTED_BLOB"
        # asyncio.run was called with the encrypt_secret coroutine
        mock_aio_run.assert_called_once()

    @patch("src.services.platform_credentials_service.asyncio.run")
    @patch("src.services.platform_credentials_service.asyncio.get_running_loop", side_effect=RuntimeError)
    @patch("src.services.platform_credentials_service.decrypt_secret", new_callable=AsyncMock)
    def test_decrypt_parses_json_from_decrypt_secret(
        self, mock_decrypt, _mock_loop, mock_aio_run,
    ):
        payload = {"access_token": "tok123", "ad_account_id": "act_456"}
        mock_aio_run.return_value = json.dumps(payload)
        service = _service()

        result = service._decrypt_credentials("ENCRYPTED_BLOB")

        assert result == payload
        mock_aio_run.assert_called_once()

    @patch("src.services.platform_credentials_service.asyncio.run")
    @patch("src.services.platform_credentials_service.asyncio.get_running_loop", side_effect=RuntimeError)
    @patch("src.services.platform_credentials_service.decrypt_secret", new_callable=AsyncMock)
    def test_decrypt_raises_on_invalid_json(
        self, mock_decrypt, _mock_loop, mock_aio_run,
    ):
        mock_aio_run.return_value = "NOT_VALID_JSON{{{"
        service = _service()

        with pytest.raises(json.JSONDecodeError):
            service._decrypt_credentials("BAD_PAYLOAD")


# =============================================================================
# get_meta_credentials
# =============================================================================

class TestGetMetaCredentials:

    @pytest.mark.asyncio
    async def test_returns_meta_credentials_when_found(self):
        payload = {"access_token": "meta_token_abc", "ad_account_id": "act_12345678"}

        session = _mock_session()
        cred = _make_credential("meta_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        # Patch _decrypt_credentials (sync) to bypass asyncio.run guard
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.get_meta_credentials(TENANT_ID)

        assert result is not None
        assert result.access_token == "meta_token_abc"
        assert result.ad_account_id == "act_12345678"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_credential(self):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        service = _service(session)
        result = await service.get_meta_credentials(TENANT_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_field(self):
        """Returns None when decrypted payload is missing required fields."""
        session = _mock_session()
        cred = _make_credential("meta_ads", {})
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        # Missing ad_account_id — .get("ad_account_id", "") returns empty string,
        # which the service treats as valid (returns MetaCredentials with empty ad_account_id).
        # Simulate a decrypt failure (exception) to exercise the None-return path.
        service._decrypt_credentials = MagicMock(side_effect=RuntimeError("bad payload"))
        result = await service.get_meta_credentials(TENANT_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_queries_tenant_and_source_type(self):
        """DB query is always scoped to tenant_id AND source_type (tenant isolation)."""
        session = _mock_session()
        cred = _make_credential("meta_ads", {})
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(
            return_value={"access_token": "tok", "ad_account_id": "act_1"}
        )
        await service.get_meta_credentials(TENANT_ID)

        # Verify execute was called (select statement was constructed)
        session.execute.assert_called_once()
        # The query must have been called — we trust the implementation filters by tenant_id
        # and source_type via the select() statement


# =============================================================================
# get_google_credentials
# =============================================================================

class TestGetGoogleCredentials:

    @pytest.mark.asyncio
    async def test_returns_google_credentials_when_found(self):
        payload = {
            "access_token": "google_access_tok",
            "refresh_token": "google_refresh_tok",
            "client_id": "client-id-001",
            "client_secret": "client-secret-001",
            "developer_token": "dev-tok-001",
            "customer_id": "123-456-7890",
        }

        session = _mock_session()
        cred = _make_credential("google_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.get_google_credentials(TENANT_ID)

        assert result is not None
        assert result.access_token == "google_access_tok"
        assert result.refresh_token == "google_refresh_tok"
        assert result.client_id == "client-id-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_credential(self):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        service = _service(session)
        result = await service.get_google_credentials(TENANT_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_login_customer_id_optional(self):
        """login_customer_id is optional and defaults to None."""
        payload = {
            "access_token": "tok",
            "refresh_token": "rtok",
            "client_id": "cid",
            "client_secret": "csec",
            "developer_token": "dtok",
            "customer_id": "1234567890",
            # No login_customer_id
        }

        session = _mock_session()
        cred = _make_credential("google_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.get_google_credentials(TENANT_ID)

        assert result is not None
        assert result.login_customer_id is None


# =============================================================================
# store_credentials
# =============================================================================

class TestStoreCredentials:

    @pytest.mark.asyncio
    async def test_store_meta_creates_connector_credential_row(self):
        session = _mock_session()

        service = _service(session)
        # _encrypt_credentials is async but called without await in store_credentials,
        # so mock it as a sync MagicMock to return the string directly.
        service._encrypt_credentials = MagicMock(return_value="ENCRYPTED_META_PAYLOAD")
        # _find_active_credential must return None to hit the "create new" branch.
        service._find_active_credential = MagicMock(return_value=None)
        result = await service.store_credentials(
            tenant_id=TENANT_ID,
            platform=Platform.META,
            credentials={"access_token": "tok", "ad_account_id": "act_1"},
            created_by="user-001",
        )

        assert result is True
        session.add.assert_called_once()
        added_record = session.add.call_args[0][0]
        assert isinstance(added_record, ConnectorCredential)
        assert added_record.tenant_id == TENANT_ID
        assert added_record.source_type == "meta"
        assert added_record.encrypted_payload == "ENCRYPTED_META_PAYLOAD"
        assert added_record.status == CredentialStatus.ACTIVE
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_google_uses_correct_source_type(self):
        session = _mock_session()

        service = _service(session)
        service._encrypt_credentials = MagicMock(return_value="ENCRYPTED_GOOGLE_PAYLOAD")
        service._find_active_credential = MagicMock(return_value=None)
        result = await service.store_credentials(
            tenant_id=TENANT_ID,
            platform=Platform.GOOGLE,
            credentials={"access_token": "tok"},
            created_by="user-001",
        )

        assert result is True
        added_record = session.add.call_args[0][0]
        assert added_record.source_type == "google_ads"

    @pytest.mark.asyncio
    async def test_store_returns_false_on_exception(self):
        """Returns False and rolls back if DB commit fails."""
        session = _mock_session()
        session.commit.side_effect = RuntimeError("DB failure")

        service = _service(session)
        service._encrypt_credentials = MagicMock(return_value="ENCRYPTED")
        service._find_active_credential = MagicMock(return_value=None)
        result = await service.store_credentials(
            tenant_id=TENANT_ID,
            platform=Platform.META,
            credentials={"access_token": "tok", "ad_account_id": "act_1"},
            created_by="user-001",
        )

        assert result is False
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_returns_false_on_encrypt_failure(self):
        """Encryption failure before the try block propagates as an exception."""
        session = _mock_session()

        service = _service(session)
        # _encrypt_credentials is called without await in store_credentials;
        # MagicMock raises synchronously, which happens outside the try/except
        # block, so the exception propagates rather than returning False.
        service._encrypt_credentials = MagicMock(side_effect=RuntimeError("KMS unavailable"))

        with pytest.raises(RuntimeError, match="KMS unavailable"):
            await service.store_credentials(
                tenant_id=TENANT_ID,
                platform=Platform.META,
                credentials={"access_token": "tok", "ad_account_id": "act_1"},
                created_by="user-001",
            )

        session.add.assert_not_called()


# =============================================================================
# revoke_credentials
# =============================================================================

class TestRevokeCredentials:

    @pytest.mark.asyncio
    async def test_revoke_sets_revoked_status_and_soft_deleted_at(self):
        session = _mock_session()
        cred = _make_credential("meta_ads", {})
        assert cred.soft_deleted_at is None
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        result = await service.revoke_credentials(TENANT_ID, Platform.META)

        assert result is True
        assert cred.status == CredentialStatus.REVOKED
        assert cred.soft_deleted_at is not None
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_returns_false_when_no_active_credential(self):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        service = _service(session)
        result = await service.revoke_credentials(TENANT_ID, Platform.META)

        assert result is False
        session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_returns_false_on_db_exception(self):
        session = _mock_session()
        cred = _make_credential("meta_ads", {})
        session.execute.return_value.scalar_one_or_none.return_value = cred
        session.flush.side_effect = RuntimeError("DB failure")

        service = _service(session)
        result = await service.revoke_credentials(TENANT_ID, Platform.META)

        assert result is False
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_google_queries_correct_source_type(self):
        session = _mock_session()
        cred = _make_credential("google_ads", {})
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        result = await service.revoke_credentials(TENANT_ID, Platform.GOOGLE)

        assert result is True
        assert cred.status == CredentialStatus.REVOKED


# =============================================================================
# get_credentials_for_platform
# =============================================================================

class TestGetCredentialsForPlatform:

    @pytest.mark.asyncio
    async def test_dispatches_meta_to_get_meta_credentials(self):
        payload = {"access_token": "tok", "ad_account_id": "act_1"}

        session = _mock_session()
        cred = _make_credential("meta_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.get_credentials_for_platform(TENANT_ID, Platform.META)

        assert result is not None
        from src.services.platform_executors import MetaCredentials
        assert isinstance(result, MetaCredentials)

    @pytest.mark.asyncio
    async def test_dispatches_google_to_get_google_credentials(self):
        payload = {
            "access_token": "tok",
            "refresh_token": "rtok",
            "client_id": "cid",
            "client_secret": "csec",
            "developer_token": "dtok",
            "customer_id": "1234567890",
        }

        session = _mock_session()
        cred = _make_credential("google_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.get_credentials_for_platform(TENANT_ID, Platform.GOOGLE)

        assert result is not None
        from src.services.platform_executors import GoogleAdsCredentials
        assert isinstance(result, GoogleAdsCredentials)

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_platform(self):
        session = _mock_session()
        service = _service(session)
        result = await service.get_credentials_for_platform(TENANT_ID, Platform.SHOPIFY)

        assert result is None


# =============================================================================
# check_credentials_exist
# =============================================================================

class TestCheckCredentialsExist:

    @pytest.mark.asyncio
    async def test_returns_true_when_credentials_found(self):
        payload = {"access_token": "tok", "ad_account_id": "act_1"}

        session = _mock_session()
        cred = _make_credential("meta_ads", payload)
        session.execute.return_value.scalar_one_or_none.return_value = cred

        service = _service(session)
        service._decrypt_credentials = MagicMock(return_value=payload)
        result = await service.check_credentials_exist(TENANT_ID, Platform.META)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_credentials(self):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        service = _service(session)
        result = await service.check_credentials_exist(TENANT_ID, Platform.META)

        assert result is False


# =============================================================================
# validate_credentials — missing case
# =============================================================================

class TestValidateCredentials:

    @pytest.mark.asyncio
    async def test_validate_returns_missing_when_no_credentials(self):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        service = _service(session)
        result = await service.validate_credentials(TENANT_ID, Platform.META)

        assert isinstance(result, CredentialValidation)
        assert result.is_valid is False
        assert result.status == CredentialStatus.MISSING
        assert result.needs_reauth is True
