import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models.connector_credential import ConnectorCredential, CredentialStatus
from src.services.token_manager import RefreshResult, TokenManager

TENANT_ID = "tenant-token-unit-001"
USER_ID = "clerk_user_token_abc"


def _mock_session():
    session = MagicMock()
    session.execute = MagicMock()
    session.flush = MagicMock()
    return session


def _make_credential(**overrides) -> ConnectorCredential:
    defaults = {
        "id": "cred-1",
        "tenant_id": TENANT_ID,
        "credential_name": "Test Credential",
        "source_type": "google_ads",
        "encrypted_payload": "encrypted_payload",
        "credential_metadata": {
            "token_expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()
        },
        "status": CredentialStatus.ACTIVE,
        "created_by": USER_ID,
        "soft_deleted_at": None,
        "hard_delete_after": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    cred = ConnectorCredential()
    for key, value in defaults.items():
        setattr(cred, key, value)
    return cred


def _mock_async_client(method_name: str, response_or_exc):
    http_client = MagicMock()
    if isinstance(response_or_exc, Exception):
        setattr(http_client, method_name, AsyncMock(side_effect=response_or_exc))
    else:
        setattr(http_client, method_name, AsyncMock(return_value=response_or_exc))
    async_client_cm = MagicMock()
    async_client_cm.__aenter__ = AsyncMock(return_value=http_client)
    async_client_cm.__aexit__ = AsyncMock(return_value=None)
    return async_client_cm


@pytest.mark.asyncio
@patch("src.platform.audit.log_system_audit_event_sync")
@patch("src.services.token_manager.encrypt_secret", new_callable=AsyncMock)
@patch("src.services.token_manager.decrypt_secret", new_callable=AsyncMock)
async def test_proactive_refresh_meta_updates_payload_and_metadata(
    mock_decrypt, mock_encrypt, _mock_audit, monkeypatch
):
    monkeypatch.setenv("META_APP_ID", "meta-app-id")
    monkeypatch.setenv("META_APP_SECRET", "meta-app-secret")

    expiring = _make_credential(
        id="cred-meta",
        source_type="meta",
        credential_metadata={
            "token_expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ).isoformat()
        },
    )

    mock_decrypt.return_value = json.dumps(
        {"access_token": "old_access", "refresh_token": "old_refresh"}
    )
    mock_encrypt.return_value = "new_encrypted_payload"

    session = _mock_session()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [expiring]
    session.execute.return_value = result

    manager = TokenManager(db_session=session, tenant_id=TENANT_ID)

    meta_response = httpx.Response(
        200,
        json={
            "access_token": "new_meta_access",
            "expires_in": 7200,
            "token_type": "bearer",
        },
    )
    with patch(
        "src.services.token_manager.httpx.AsyncClient",
        return_value=_mock_async_client("get", meta_response),
    ):
        stats = await manager.refresh_expiring_credentials()

    assert stats.refreshed == 1
    assert expiring.encrypted_payload == "new_encrypted_payload"
    assert expiring.credential_metadata["refresh_error_count"] == 0
    assert "last_refresh_at" in expiring.credential_metadata
    assert "token_expires_at" in expiring.credential_metadata


@pytest.mark.asyncio
@patch("src.platform.audit.log_system_audit_event_sync")
@patch("src.services.token_manager.encrypt_secret", new_callable=AsyncMock)
@patch("src.services.token_manager.decrypt_secret", new_callable=AsyncMock)
async def test_reactive_refresh_google_success_normalizes_expiry(
    mock_decrypt, mock_encrypt, _mock_audit, monkeypatch
):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")

    credential = _make_credential(id="cred-google", source_type="google_ads")
    mock_decrypt.return_value = json.dumps(
        {"access_token": "old_access", "refresh_token": "google_refresh"}
    )
    mock_encrypt.return_value = "new_google_encrypted"

    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = credential
    session.execute.return_value = result

    manager = TokenManager(db_session=session, tenant_id=TENANT_ID)

    google_response = httpx.Response(
        200,
        json={
            "access_token": "new_google_access",
            "expires_in": "3600",
            "token_type": "Bearer",
        },
    )
    with patch(
        "src.services.token_manager.httpx.AsyncClient",
        return_value=_mock_async_client("post", google_response),
    ):
        outcome = await manager.reactive_refresh("cred-google")

    assert outcome.result == RefreshResult.SUCCESS
    assert credential.credential_metadata["refresh_error_count"] == 0
    parsed_expiry = datetime.fromisoformat(
        credential.credential_metadata["token_expires_at"]
    )
    assert parsed_expiry > datetime.now(timezone.utc)


@pytest.mark.asyncio
@patch("src.platform.audit.log_system_audit_event_sync")
@patch("src.services.token_manager.decrypt_secret", new_callable=AsyncMock)
async def test_reactive_refresh_google_invalid_grant_is_permanent(
    mock_decrypt, _mock_audit, monkeypatch
):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")

    credential = _make_credential(id="cred-google-invalid", source_type="google_ads")
    mock_decrypt.return_value = json.dumps(
        {"access_token": "old_access", "refresh_token": "google_refresh"}
    )

    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = credential
    session.execute.return_value = result

    manager = TokenManager(db_session=session, tenant_id=TENANT_ID)

    google_response = httpx.Response(400, json={"error": "invalid_grant"})
    with patch(
        "src.services.token_manager.httpx.AsyncClient",
        return_value=_mock_async_client("post", google_response),
    ):
        outcome = await manager.reactive_refresh("cred-google-invalid")

    assert outcome.result == RefreshResult.FAILED_PERMANENT
    assert credential.status == CredentialStatus.EXPIRED
    assert credential.credential_metadata["refresh_error_count"] == 1


@pytest.mark.asyncio
@patch("src.platform.audit.log_system_audit_event_sync")
@patch("src.services.token_manager.decrypt_secret", new_callable=AsyncMock)
async def test_reactive_refresh_meta_network_error_is_retryable(
    mock_decrypt, _mock_audit, monkeypatch
):
    monkeypatch.setenv("META_APP_ID", "meta-app-id")
    monkeypatch.setenv("META_APP_SECRET", "meta-app-secret")

    credential = _make_credential(id="cred-meta-network", source_type="meta")
    mock_decrypt.return_value = json.dumps(
        {"access_token": "old_access", "refresh_token": "old_refresh"}
    )

    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = credential
    session.execute.return_value = result

    manager = TokenManager(db_session=session, tenant_id=TENANT_ID)

    request = httpx.Request(
        "GET", "https://graph.facebook.com/v19.0/oauth/access_token"
    )
    with patch(
        "src.services.token_manager.httpx.AsyncClient",
        return_value=_mock_async_client(
            "get", httpx.ConnectError("no route", request=request)
        ),
    ):
        outcome = await manager.reactive_refresh("cred-meta-network")

    assert outcome.result == RefreshResult.FAILED_RETRYABLE
    assert credential.status == CredentialStatus.ACTIVE
    assert credential.credential_metadata["refresh_error_count"] == 1
    assert "last_refresh_attempt_at" in credential.credential_metadata
