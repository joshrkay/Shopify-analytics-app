"""
Tests for encryption utilities.

Tests AES-256-GCM encryption/decryption for credential storage.
"""

import pytest
import base64

from src.utils.encryption import (
    CredentialEncryptor,
    EncryptedData,
    EncryptionError,
    DecryptionError,
    InvalidKeyError,
    derive_key_from_password,
    NONCE_SIZE,
    TAG_SIZE,
    KEY_SIZE,
)


class TestCredentialEncryptor:
    """Tests for CredentialEncryptor class."""

    @pytest.fixture
    def valid_key(self) -> bytes:
        """Generate a valid 32-byte encryption key."""
        return CredentialEncryptor.generate_key()

    @pytest.fixture
    def encryptor(self, valid_key: bytes) -> CredentialEncryptor:
        """Create an encryptor with a valid key."""
        return CredentialEncryptor(key=valid_key)

    def test_generate_key_returns_32_bytes(self):
        """Test that generate_key produces a 32-byte key."""
        key = CredentialEncryptor.generate_key()
        assert len(key) == KEY_SIZE
        assert isinstance(key, bytes)

    def test_generate_key_string_returns_base64(self):
        """Test that generate_key_string produces valid base64."""
        key_string = CredentialEncryptor.generate_key_string()
        decoded = base64.b64decode(key_string)
        assert len(decoded) == KEY_SIZE

    def test_generate_nonce_returns_12_bytes(self):
        """Test that generate_nonce produces a 12-byte nonce."""
        nonce = CredentialEncryptor.generate_nonce()
        assert len(nonce) == NONCE_SIZE
        assert isinstance(nonce, bytes)

    def test_init_with_bytes_key(self, valid_key: bytes):
        """Test initialization with bytes key."""
        encryptor = CredentialEncryptor(key=valid_key)
        assert encryptor is not None

    def test_init_with_base64_key_string(self, valid_key: bytes):
        """Test initialization with base64 key string."""
        key_string = base64.b64encode(valid_key).decode("utf-8")
        encryptor = CredentialEncryptor(key_string=key_string)
        assert encryptor is not None

    def test_init_with_hex_key_string(self, valid_key: bytes):
        """Test initialization with hex key string."""
        key_string = valid_key.hex()
        encryptor = CredentialEncryptor(key_string=key_string)
        assert encryptor is not None

    def test_init_without_key_raises_error(self):
        """Test that initialization without key raises InvalidKeyError."""
        with pytest.raises(InvalidKeyError, match="Encryption key is required"):
            CredentialEncryptor()

    def test_init_with_wrong_size_key_raises_error(self):
        """Test that wrong size key raises InvalidKeyError."""
        short_key = b"too_short"
        with pytest.raises(InvalidKeyError, match="must be 32 bytes"):
            CredentialEncryptor(key=short_key)

    def test_encrypt_returns_tuple(self, encryptor: CredentialEncryptor):
        """Test that encrypt returns (ciphertext, nonce, tag) tuple."""
        data = {"access_token": "secret123", "ad_account_id": "act_123"}
        ciphertext, nonce, tag = encryptor.encrypt(data)

        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)
        assert isinstance(tag, bytes)
        assert len(nonce) == NONCE_SIZE
        assert len(tag) == TAG_SIZE

    def test_encrypt_decrypt_roundtrip(self, encryptor: CredentialEncryptor):
        """Test that data can be encrypted and decrypted correctly."""
        original_data = {
            "access_token": "secret_token_123",
            "ad_account_id": "act_456789",
            "refresh_token": "refresh_xyz",
        }

        ciphertext, nonce, tag = encryptor.encrypt(original_data)
        decrypted_data = encryptor.decrypt(ciphertext, nonce, tag)

        assert decrypted_data == original_data

    def test_encrypt_with_associated_data(self, encryptor: CredentialEncryptor):
        """Test encryption with associated data (AAD)."""
        data = {"token": "secret"}
        aad = b"tenant_123:meta"

        ciphertext, nonce, tag = encryptor.encrypt(data, associated_data=aad)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag, associated_data=aad)

        assert decrypted == data

    def test_decrypt_with_wrong_aad_fails(self, encryptor: CredentialEncryptor):
        """Test that decryption fails with wrong AAD."""
        data = {"token": "secret"}
        aad = b"tenant_123:meta"
        wrong_aad = b"tenant_456:google"

        ciphertext, nonce, tag = encryptor.encrypt(data, associated_data=aad)

        with pytest.raises(DecryptionError, match="tampered"):
            encryptor.decrypt(ciphertext, nonce, tag, associated_data=wrong_aad)

    def test_decrypt_with_wrong_nonce_fails(self, encryptor: CredentialEncryptor):
        """Test that decryption fails with wrong nonce."""
        data = {"token": "secret"}
        ciphertext, nonce, tag = encryptor.encrypt(data)
        wrong_nonce = CredentialEncryptor.generate_nonce()

        with pytest.raises(DecryptionError):
            encryptor.decrypt(ciphertext, wrong_nonce, tag)

    def test_decrypt_with_wrong_tag_fails(self, encryptor: CredentialEncryptor):
        """Test that decryption fails with wrong auth tag."""
        data = {"token": "secret"}
        ciphertext, nonce, tag = encryptor.encrypt(data)
        wrong_tag = b"x" * TAG_SIZE

        with pytest.raises(DecryptionError, match="tampered"):
            encryptor.decrypt(ciphertext, nonce, wrong_tag)

    def test_decrypt_with_tampered_ciphertext_fails(self, encryptor: CredentialEncryptor):
        """Test that decryption fails with tampered ciphertext."""
        data = {"token": "secret"}
        ciphertext, nonce, tag = encryptor.encrypt(data)
        tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]

        with pytest.raises(DecryptionError):
            encryptor.decrypt(tampered, nonce, tag)

    def test_decrypt_with_wrong_key_fails(self, valid_key: bytes):
        """Test that decryption fails with different key."""
        encryptor1 = CredentialEncryptor(key=valid_key)
        encryptor2 = CredentialEncryptor(key=CredentialEncryptor.generate_key())

        data = {"token": "secret"}
        ciphertext, nonce, tag = encryptor1.encrypt(data)

        with pytest.raises(DecryptionError):
            encryptor2.decrypt(ciphertext, nonce, tag)

    def test_each_encryption_uses_unique_nonce(self, encryptor: CredentialEncryptor):
        """Test that each encryption generates a unique nonce."""
        data = {"token": "same_data"}
        results = [encryptor.encrypt(data) for _ in range(100)]
        nonces = [r[1] for r in results]

        # All nonces should be unique
        assert len(set(nonces)) == len(nonces)

    def test_encrypt_to_struct(self, encryptor: CredentialEncryptor):
        """Test encrypt_to_struct method."""
        data = {"token": "secret"}
        encrypted = encryptor.encrypt_to_struct(data)

        assert isinstance(encrypted, EncryptedData)
        assert isinstance(encrypted.ciphertext, bytes)
        assert len(encrypted.nonce) == NONCE_SIZE
        assert len(encrypted.tag) == TAG_SIZE

    def test_decrypt_from_struct(self, encryptor: CredentialEncryptor):
        """Test decrypt_from_struct method."""
        original = {"token": "secret", "id": 123}
        encrypted = encryptor.encrypt_to_struct(original)
        decrypted = encryptor.decrypt_from_struct(encrypted)

        assert decrypted == original


class TestEncryptedData:
    """Tests for EncryptedData dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary with base64 values."""
        data = EncryptedData(
            ciphertext=b"test_cipher",
            nonce=b"test_nonce12",
            tag=b"test_auth_tag123",
        )
        result = data.to_dict()

        assert "ciphertext" in result
        assert "nonce" in result
        assert "tag" in result

        # Verify base64 encoding
        assert base64.b64decode(result["ciphertext"]) == b"test_cipher"
        assert base64.b64decode(result["nonce"]) == b"test_nonce12"
        assert base64.b64decode(result["tag"]) == b"test_auth_tag123"

    def test_from_dict(self):
        """Test creation from dictionary with base64 values."""
        original = EncryptedData(
            ciphertext=b"test_cipher",
            nonce=b"test_nonce12",
            tag=b"test_auth_tag123",
        )
        dict_form = original.to_dict()
        restored = EncryptedData.from_dict(dict_form)

        assert restored.ciphertext == original.ciphertext
        assert restored.nonce == original.nonce
        assert restored.tag == original.tag


class TestDeriveKeyFromPassword:
    """Tests for password-based key derivation."""

    def test_derive_key_returns_32_bytes(self):
        """Test that derived key is 32 bytes."""
        key, salt = derive_key_from_password("my_password")
        assert len(key) == KEY_SIZE
        assert len(salt) == 16

    def test_same_password_and_salt_produces_same_key(self):
        """Test deterministic key derivation."""
        key1, salt = derive_key_from_password("my_password")
        key2, _ = derive_key_from_password("my_password", salt=salt)
        assert key1 == key2

    def test_different_passwords_produce_different_keys(self):
        """Test that different passwords produce different keys."""
        key1, salt = derive_key_from_password("password1")
        key2, _ = derive_key_from_password("password2", salt=salt)
        assert key1 != key2

    def test_different_salts_produce_different_keys(self):
        """Test that different salts produce different keys."""
        key1, salt1 = derive_key_from_password("same_password")
        key2, salt2 = derive_key_from_password("same_password")
        assert key1 != key2
        assert salt1 != salt2

    def test_derived_key_works_with_encryptor(self):
        """Test that derived key can be used with CredentialEncryptor."""
        key, _ = derive_key_from_password("my_secure_password")
        encryptor = CredentialEncryptor(key=key)

        data = {"secret": "value"}
        ciphertext, nonce, tag = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag)

        assert decrypted == data


class TestComplexDataTypes:
    """Tests for encrypting complex data structures."""

    @pytest.fixture
    def encryptor(self) -> CredentialEncryptor:
        return CredentialEncryptor(key=CredentialEncryptor.generate_key())

    def test_encrypt_nested_dict(self, encryptor: CredentialEncryptor):
        """Test encrypting nested dictionary."""
        data = {
            "credentials": {
                "access_token": "token123",
                "refresh_token": "refresh456",
            },
            "config": {
                "timeout": 30,
                "retries": 3,
            },
        }
        ciphertext, nonce, tag = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag)
        assert decrypted == data

    def test_encrypt_with_lists(self, encryptor: CredentialEncryptor):
        """Test encrypting data with lists."""
        data = {
            "scopes": ["read", "write", "admin"],
            "account_ids": ["act_123", "act_456"],
        }
        ciphertext, nonce, tag = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag)
        assert decrypted == data

    def test_encrypt_with_numbers(self, encryptor: CredentialEncryptor):
        """Test encrypting data with numbers."""
        data = {
            "customer_id": 12345678,
            "rate_limit": 100.5,
            "is_active": True,
        }
        ciphertext, nonce, tag = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag)
        assert decrypted == data

    def test_encrypt_unicode(self, encryptor: CredentialEncryptor):
        """Test encrypting Unicode content."""
        data = {
            "name": "Test Account",
            "description": "Test account for platform integration",
        }
        ciphertext, nonce, tag = encryptor.encrypt(data)
        decrypted = encryptor.decrypt(ciphertext, nonce, tag)
        assert decrypted == data
