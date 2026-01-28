"""
Credential encryption tests.

CRITICAL: These tests verify:
1. Tokens are encrypted at rest
2. Tokens NEVER appear in logs
3. Encryption round-trip works correctly
4. Error handling for misconfigured encryption
"""

import pytest
import logging
import uuid
from io import StringIO
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.credentials.encryption import (
    encrypt_token,
    decrypt_token,
    rotate_encryption,
    validate_encryption_ready,
    CredentialEncryptionError,
)
from src.credentials.redaction import (
    redact_credential_data,
    redact_credential_value,
    is_credential_secret_key,
    CredentialLoggingFilter,
    CredentialAuditLogger,
    AuditEventType,
    REDACTED_VALUE,
)
from src.platform.secrets import validate_encryption_configured


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def encryption_key(monkeypatch):
    """Set up encryption key for testing."""
    monkeypatch.setenv("ENCRYPTION_KEY", "test-credential-encryption-key-32!")
    return "test-credential-encryption-key-32!"


@pytest.fixture
def log_capture():
    """Capture log output for testing token leakage."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)

    # Add credential redaction filter
    handler.addFilter(CredentialLoggingFilter())

    logger = logging.getLogger("test_credentials")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield log_stream

    logger.removeHandler(handler)


@pytest.fixture
def sample_tokens():
    """Sample OAuth tokens for testing.
    
    NOTE: These are intentionally NOT real token patterns to avoid
    triggering GitHub's secret scanning. Use obviously fake values.
    """
    return {
        "shopify_token": "test_shopify_token_not_real_xxxxx",
        "google_token": "test_google_token_not_real_xxxxx",
        "facebook_token": "test_facebook_token_not_real_xxxxx",
        "generic_token": "test_generic_token_not_real_xxxxx",
        "refresh_token": "test_refresh_token_not_real_xxxxx",
    }


# ============================================================================
# TEST SUITE: ENCRYPTION ROUND-TRIP
# ============================================================================

class TestEncryptionRoundTrip:
    """Test encryption and decryption of tokens."""

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, encryption_key):
        """CRITICAL: Encrypted tokens can be decrypted back to original."""
        # NOTE: Using obviously fake token to avoid GitHub secret scanning
        plaintext = "test_token_value_for_encryption_roundtrip"

        encrypted = await encrypt_token(plaintext)
        decrypted = await decrypt_token(encrypted)

        assert decrypted == plaintext
        assert encrypted != plaintext
        # Verify plaintext doesn't appear in encrypted form
        assert plaintext not in encrypted

    @pytest.mark.asyncio
    async def test_encrypted_value_is_different(self, encryption_key):
        """Encrypted value must be different from plaintext."""
        plaintext = "secret-token-value-12345"

        encrypted = await encrypt_token(plaintext)

        assert encrypted != plaintext
        # Token should not be substring of encrypted value
        assert plaintext not in encrypted
        assert "secret" not in encrypted
        assert "token" not in encrypted.lower()

    @pytest.mark.asyncio
    async def test_encrypt_different_tokens(self, encryption_key, sample_tokens):
        """Different tokens produce different encrypted values."""
        encrypted_values = {}

        for name, token in sample_tokens.items():
            encrypted = await encrypt_token(token)
            encrypted_values[name] = encrypted

        # All encrypted values should be unique
        unique_values = set(encrypted_values.values())
        assert len(unique_values) == len(encrypted_values)

    @pytest.mark.asyncio
    async def test_same_token_different_ciphertext(self, encryption_key):
        """
        Same token encrypted twice produces different ciphertext.
        
        This is expected behavior for Fernet encryption (includes timestamp/IV).
        """
        plaintext = "same-token-value"

        encrypted1 = await encrypt_token(plaintext)
        encrypted2 = await encrypt_token(plaintext)

        # Ciphertexts are different (Fernet includes timestamp)
        assert encrypted1 != encrypted2

        # But both decrypt to same value
        assert await decrypt_token(encrypted1) == plaintext
        assert await decrypt_token(encrypted2) == plaintext

    @pytest.mark.asyncio
    async def test_empty_token_raises_error(self, encryption_key):
        """Encrypting empty string raises error."""
        with pytest.raises(ValueError, match="Cannot encrypt empty"):
            await encrypt_token("")

    @pytest.mark.asyncio
    async def test_decrypt_invalid_ciphertext_raises_error(self, encryption_key):
        """Decrypting invalid ciphertext raises error."""
        with pytest.raises(CredentialEncryptionError):
            await decrypt_token("invalid-not-encrypted-data")

    @pytest.mark.asyncio
    async def test_decrypt_empty_raises_error(self, encryption_key):
        """Decrypting empty string raises error."""
        with pytest.raises(ValueError, match="Cannot decrypt empty"):
            await decrypt_token("")


# ============================================================================
# TEST SUITE: ENCRYPTION CONFIGURATION
# ============================================================================

class TestEncryptionConfiguration:
    """Test encryption configuration validation."""

    @pytest.mark.asyncio
    async def test_encryption_without_key_raises_error(self, monkeypatch):
        """CRITICAL: Encryption fails when ENCRYPTION_KEY not set."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

        with pytest.raises(CredentialEncryptionError, match="not configured"):
            await encrypt_token("test-token")

    @pytest.mark.asyncio
    async def test_decryption_without_key_raises_error(self, monkeypatch):
        """CRITICAL: Decryption fails when ENCRYPTION_KEY not set."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

        with pytest.raises(CredentialEncryptionError, match="not configured"):
            await decrypt_token("some-encrypted-value")

    def test_validate_encryption_configured_true(self, encryption_key):
        """validate_encryption_configured returns True when configured."""
        assert validate_encryption_configured() is True

    def test_validate_encryption_configured_false(self, monkeypatch):
        """validate_encryption_configured returns False when not configured."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        assert validate_encryption_configured() is False

    def test_validate_encryption_ready_raises_when_not_configured(self, monkeypatch):
        """validate_encryption_ready raises error when not configured."""
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

        with pytest.raises(CredentialEncryptionError, match="ENCRYPTION_KEY"):
            validate_encryption_ready()


# ============================================================================
# TEST SUITE: TOKENS NEVER IN LOGS
# ============================================================================

class TestTokensNeverInLogs:
    """CRITICAL: Verify tokens never appear in any log output."""

    def test_tokens_redacted_from_dict(self, sample_tokens):
        """Tokens in dictionary values are redacted."""
        data = {
            "access_token": sample_tokens["shopify_token"],
            "refresh_token": sample_tokens["refresh_token"],
            "user_name": "John",
        }

        result = redact_credential_data(data)

        assert result["access_token"] == REDACTED_VALUE
        assert result["refresh_token"] == REDACTED_VALUE
        assert result["user_name"] == "John"  # Non-secret preserved
        # Original token should not appear anywhere
        assert sample_tokens["shopify_token"] not in str(result)
        assert sample_tokens["refresh_token"] not in str(result)

    def test_tokens_redacted_from_nested_dict(self, sample_tokens):
        """Tokens in nested dictionaries are redacted."""
        data = {
            "credentials": {
                "oauth": {
                    "access_token": sample_tokens["google_token"],
                    "refresh_token": sample_tokens["refresh_token"],
                }
            },
            "metadata": {
                "account_name": "Test Account",  # Should NOT be redacted
            }
        }

        result = redact_credential_data(data)

        assert result["credentials"]["oauth"]["access_token"] == REDACTED_VALUE
        assert result["credentials"]["oauth"]["refresh_token"] == REDACTED_VALUE
        assert result["metadata"]["account_name"] == "Test Account"

    def test_token_patterns_in_strings_redacted(self, sample_tokens):
        """Token patterns in plain strings are redacted."""
        for name, token in sample_tokens.items():
            message = f"Using token: {token}"
            redacted = redact_credential_value(message)

            # Token should be redacted
            assert token not in redacted
            if token in message:  # If pattern matches
                assert REDACTED_VALUE in redacted

    def test_shopify_token_pattern_redacted(self):
        """Shopify access token pattern is redacted.
        
        NOTE: We test with a shorter pattern to avoid GitHub secret scanning
        while still verifying the redaction logic works.
        """
        # Test that access_token key triggers redaction
        data = {"access_token": "any_token_value_here"}
        result = redact_credential_data(data)
        assert result["access_token"] == REDACTED_VALUE

    def test_google_token_pattern_redacted(self):
        """Google OAuth token pattern is redacted."""
        value = "Bearer ya29.a0AfH6SMBx_FAKE_VALUE"
        result = redact_credential_value(value)

        assert "ya29." not in result

    def test_logging_filter_redacts_tokens(self, log_capture, sample_tokens):
        """CRITICAL: Logging filter prevents tokens in logs."""
        logger = logging.getLogger("test_credentials")

        # Log a message containing a token
        logger.info(f"Token value: {sample_tokens['shopify_token']}")

        log_output = log_capture.getvalue()

        # Token should NOT appear in logs
        assert sample_tokens["shopify_token"] not in log_output
        assert "shpat_" not in log_output

    def test_logging_filter_preserves_safe_data(self, log_capture):
        """Logging filter preserves non-secret data."""
        logger = logging.getLogger("test_credentials")

        # Log safe data
        logger.info("Processing for account: Test Store")

        log_output = log_capture.getvalue()

        assert "Test Store" in log_output

    def test_account_name_not_redacted(self):
        """account_name is allowed in logs per PII policy."""
        data = {
            "access_token": "secret-token-value",
            "account_name": "My Shopify Store",
            "connector_name": "Shopify Connector",
        }

        result = redact_credential_data(data)

        assert result["account_name"] == "My Shopify Store"
        assert result["connector_name"] == "Shopify Connector"
        assert result["access_token"] == REDACTED_VALUE


# ============================================================================
# TEST SUITE: SECRET KEY DETECTION
# ============================================================================

class TestSecretKeyDetection:
    """Test detection of secret-containing keys."""

    @pytest.mark.parametrize("key", [
        "access_token",
        "refresh_token",
        "oauth_token",
        "bearer_token",
        "api_key",
        "apiKey",
        "secret_key",
        "password",
        "credentials",
        "auth_token",
        "client_secret",
    ])
    def test_secret_keys_detected(self, key):
        """CRITICAL: All secret key patterns are detected."""
        assert is_credential_secret_key(key), f"Failed to detect: {key}"

    @pytest.mark.parametrize("key", [
        "account_name",
        "connector_name",
        "shop_name",
        "user_name",
        "email",
        "created_at",
        "status",
        "provider",
    ])
    def test_non_secret_keys_not_detected(self, key):
        """Non-secret keys are not flagged."""
        # Note: account_name, connector_name are explicitly allowed
        assert not is_credential_secret_key(key), f"Incorrectly flagged: {key}"


# ============================================================================
# TEST SUITE: AUDIT LOGGING
# ============================================================================

class TestAuditLogging:
    """Test credential audit logging."""

    def test_audit_logger_logs_events(self, log_capture):
        """Audit logger records credential events."""
        audit = CredentialAuditLogger(tenant_id="test-tenant")

        audit.log(
            event_type=AuditEventType.CREDENTIAL_STORED,
            credential_id="cred-123",
            provider="shopify",
            account_name="Test Store",
        )

        log_output = log_capture.getvalue()
        assert "credential.stored" in log_output

    def test_audit_logger_redacts_tokens_in_metadata(self, log_capture):
        """Audit logger redacts any tokens in metadata."""
        audit = CredentialAuditLogger(tenant_id="test-tenant")

        # Accidentally pass a token in metadata (should be redacted)
        audit.log(
            event_type=AuditEventType.CREDENTIAL_STORED,
            credential_id="cred-123",
            provider="shopify",
            metadata={"access_token": "secret_test_value_for_audit"}
        )

        log_output = log_capture.getvalue()
        assert "secret_test_value_for_audit" not in log_output


# ============================================================================
# TEST SUITE: ENCRYPTION KEY ROTATION
# ============================================================================

class TestKeyRotation:
    """Test encryption key rotation."""

    @pytest.mark.asyncio
    async def test_rotate_encryption(self, encryption_key):
        """Encryption rotation re-encrypts token."""
        original_token = "original-secret-token-value"

        # Encrypt with current key
        encrypted1 = await encrypt_token(original_token)

        # Rotate (re-encrypt with same key in this test)
        encrypted2 = await rotate_encryption(encrypted1)

        # New ciphertext is different
        assert encrypted2 != encrypted1

        # But decrypts to same value
        decrypted = await decrypt_token(encrypted2)
        assert decrypted == original_token


# ============================================================================
# TEST SUITE: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_unicode_tokens(self, encryption_key):
        """Unicode characters in tokens are handled correctly."""
        unicode_token = "token_with_émojis_🔐_and_中文"

        encrypted = await encrypt_token(unicode_token)
        decrypted = await decrypt_token(encrypted)

        assert decrypted == unicode_token

    @pytest.mark.asyncio
    async def test_long_tokens(self, encryption_key):
        """Long tokens are handled correctly."""
        long_token = "x" * 10000  # 10KB token

        encrypted = await encrypt_token(long_token)
        decrypted = await decrypt_token(encrypted)

        assert decrypted == long_token

    @pytest.mark.asyncio
    async def test_special_characters(self, encryption_key):
        """Tokens with special characters are handled correctly."""
        special_token = "token!@#$%^&*()_+-=[]{}|;':\",./<>?"

        encrypted = await encrypt_token(special_token)
        decrypted = await decrypt_token(encrypted)

        assert decrypted == special_token

    def test_redact_handles_none_values(self):
        """Redaction handles None values gracefully."""
        data = {
            "access_token": None,
            "name": None,
        }

        result = redact_credential_data(data)

        # access_token should be redacted even if None
        assert result["access_token"] == REDACTED_VALUE
        assert result["name"] is None

    def test_redact_handles_non_string_values(self):
        """Redaction handles non-string values."""
        data = {
            "count": 42,
            "enabled": True,
            "items": [1, 2, 3],
            "access_token": "secret",
        }

        result = redact_credential_data(data)

        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["items"] == [1, 2, 3]
        assert result["access_token"] == REDACTED_VALUE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
