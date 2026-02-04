"""
Encryption utilities for secure credential storage.

Implements AES-256-GCM encryption for storing sensitive data at rest.

SECURITY:
- Uses AES-256-GCM for authenticated encryption
- Each encryption uses a unique random nonce
- Encryption key should be stored securely (env var, secrets manager)
- Key must be exactly 32 bytes (256 bits)

Usage:
    from src.utils.encryption import CredentialEncryptor

    # Initialize with 32-byte key (from environment)
    encryptor = CredentialEncryptor(key=os.environ["ENCRYPTION_KEY"])

    # Encrypt credentials
    encrypted, nonce, tag = encryptor.encrypt({"access_token": "secret"})

    # Decrypt credentials
    data = encryptor.decrypt(encrypted, nonce, tag)
"""

import json
import os
import secrets
import base64
import logging
from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)


# AES-GCM constants
NONCE_SIZE = 12  # 96 bits, recommended for AES-GCM
TAG_SIZE = 16    # 128 bits, standard for AES-GCM
KEY_SIZE = 32    # 256 bits for AES-256


class EncryptionError(Exception):
    """Raised when encryption fails."""
    pass


class DecryptionError(Exception):
    """Raised when decryption fails."""
    pass


class InvalidKeyError(Exception):
    """Raised when encryption key is invalid."""
    pass


@dataclass
class EncryptedData:
    """Container for encrypted data with all components."""
    ciphertext: bytes
    nonce: bytes
    tag: bytes

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary with base64-encoded values."""
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode("utf-8"),
            "nonce": base64.b64encode(self.nonce).decode("utf-8"),
            "tag": base64.b64encode(self.tag).decode("utf-8"),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "EncryptedData":
        """Create from dictionary with base64-encoded values."""
        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            nonce=base64.b64decode(data["nonce"]),
            tag=base64.b64decode(data["tag"]),
        )


class CredentialEncryptor:
    """
    AES-256-GCM encryptor for credential storage.

    Provides authenticated encryption with additional data (AEAD) support.
    Each encryption generates a unique random nonce for security.

    SECURITY:
    - Key must be 32 bytes (256 bits)
    - Never reuse nonces with the same key
    - Always use fresh nonce from generate_nonce()
    - Store key securely (never in code or logs)
    """

    def __init__(self, key: Optional[bytes] = None, key_string: Optional[str] = None):
        """
        Initialize encryptor with encryption key.

        Args:
            key: 32-byte encryption key as bytes
            key_string: Base64-encoded or hex-encoded key string

        Raises:
            InvalidKeyError: If key is missing or wrong size
        """
        if key is not None:
            self._key = key
        elif key_string is not None:
            self._key = self._decode_key_string(key_string)
        else:
            raise InvalidKeyError("Encryption key is required")

        if len(self._key) != KEY_SIZE:
            raise InvalidKeyError(
                f"Encryption key must be {KEY_SIZE} bytes, got {len(self._key)}"
            )

        self._aesgcm = AESGCM(self._key)

    def _decode_key_string(self, key_string: str) -> bytes:
        """
        Decode key from string format.

        Supports:
        - Base64 encoding
        - Hex encoding
        - Raw UTF-8 (if exactly 32 bytes)
        """
        # Try base64 first
        try:
            decoded = base64.b64decode(key_string)
            if len(decoded) == KEY_SIZE:
                return decoded
        except Exception:
            pass

        # Try hex
        try:
            decoded = bytes.fromhex(key_string)
            if len(decoded) == KEY_SIZE:
                return decoded
        except Exception:
            pass

        # Try raw bytes (UTF-8 encoded)
        raw = key_string.encode("utf-8")
        if len(raw) == KEY_SIZE:
            return raw

        raise InvalidKeyError(
            f"Could not decode key string. Expected {KEY_SIZE} bytes after decoding."
        )

    @staticmethod
    def generate_key() -> bytes:
        """
        Generate a new random 256-bit encryption key.

        Returns:
            32-byte cryptographically secure random key
        """
        return secrets.token_bytes(KEY_SIZE)

    @staticmethod
    def generate_key_string() -> str:
        """
        Generate a new random encryption key as base64 string.

        Returns:
            Base64-encoded 32-byte key
        """
        return base64.b64encode(secrets.token_bytes(KEY_SIZE)).decode("utf-8")

    @staticmethod
    def generate_nonce() -> bytes:
        """
        Generate a new random nonce for encryption.

        Returns:
            12-byte cryptographically secure random nonce
        """
        return secrets.token_bytes(NONCE_SIZE)

    def encrypt(
        self,
        data: Dict[str, Any],
        associated_data: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt credential data using AES-256-GCM.

        Args:
            data: Dictionary of credential data to encrypt
            associated_data: Optional additional data for authentication

        Returns:
            Tuple of (ciphertext, nonce, auth_tag)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Serialize data to JSON
            plaintext = json.dumps(data).encode("utf-8")

            # Generate unique nonce
            nonce = self.generate_nonce()

            # Encrypt with AES-GCM (includes authentication tag)
            # AESGCM.encrypt returns ciphertext + tag concatenated
            ciphertext_with_tag = self._aesgcm.encrypt(
                nonce,
                plaintext,
                associated_data,
            )

            # Split ciphertext and tag (tag is last 16 bytes)
            ciphertext = ciphertext_with_tag[:-TAG_SIZE]
            auth_tag = ciphertext_with_tag[-TAG_SIZE:]

            return ciphertext, nonce, auth_tag

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}") from e

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        auth_tag: bytes,
        associated_data: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Decrypt credential data using AES-256-GCM.

        Args:
            ciphertext: Encrypted data
            nonce: Nonce used for encryption (12 bytes)
            auth_tag: Authentication tag (16 bytes)
            associated_data: Optional additional data for authentication

        Returns:
            Decrypted credential dictionary

        Raises:
            DecryptionError: If decryption fails or authentication fails
        """
        try:
            # Reconstruct ciphertext + tag for AESGCM
            ciphertext_with_tag = ciphertext + auth_tag

            # Decrypt and verify authentication
            plaintext = self._aesgcm.decrypt(
                nonce,
                ciphertext_with_tag,
                associated_data,
            )

            # Parse JSON
            return json.loads(plaintext.decode("utf-8"))

        except InvalidTag:
            logger.error("Decryption failed: authentication tag mismatch")
            raise DecryptionError(
                "Decryption failed: data may have been tampered with"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Decryption failed: invalid JSON: {e}")
            raise DecryptionError(f"Decrypted data is not valid JSON: {e}")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt data: {e}") from e

    def encrypt_to_struct(
        self,
        data: Dict[str, Any],
        associated_data: Optional[bytes] = None,
    ) -> EncryptedData:
        """
        Encrypt data and return as EncryptedData struct.

        Args:
            data: Dictionary to encrypt
            associated_data: Optional AAD

        Returns:
            EncryptedData containing ciphertext, nonce, and tag
        """
        ciphertext, nonce, tag = self.encrypt(data, associated_data)
        return EncryptedData(ciphertext=ciphertext, nonce=nonce, tag=tag)

    def decrypt_from_struct(
        self,
        encrypted: EncryptedData,
        associated_data: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Decrypt from EncryptedData struct.

        Args:
            encrypted: EncryptedData struct
            associated_data: Optional AAD

        Returns:
            Decrypted dictionary
        """
        return self.decrypt(
            encrypted.ciphertext,
            encrypted.nonce,
            encrypted.tag,
            associated_data,
        )


def derive_key_from_password(
    password: str,
    salt: Optional[bytes] = None,
    iterations: int = 600000,
) -> Tuple[bytes, bytes]:
    """
    Derive an encryption key from a password using PBKDF2.

    This is useful for deriving keys from master passwords or
    environment variables that aren't raw key material.

    Args:
        password: Password string
        salt: Optional salt (generated if not provided)
        iterations: PBKDF2 iterations (default: 600000)

    Returns:
        Tuple of (derived_key, salt)

    Note:
        Store the salt alongside encrypted data if using derived keys.
    """
    if salt is None:
        salt = secrets.token_bytes(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )

    key = kdf.derive(password.encode("utf-8"))
    return key, salt


def get_encryption_key_from_env(
    env_var: str = "CREDENTIAL_ENCRYPTION_KEY",
) -> Optional[bytes]:
    """
    Get encryption key from environment variable.

    Args:
        env_var: Environment variable name

    Returns:
        Decoded key bytes, or None if not set
    """
    key_string = os.environ.get(env_var)
    if not key_string:
        return None

    try:
        # Try base64 decode
        key = base64.b64decode(key_string)
        if len(key) == KEY_SIZE:
            return key
    except Exception:
        pass

    try:
        # Try hex decode
        key = bytes.fromhex(key_string)
        if len(key) == KEY_SIZE:
            return key
    except Exception:
        pass

    # Try raw UTF-8
    key = key_string.encode("utf-8")
    if len(key) == KEY_SIZE:
        return key

    logger.warning(
        f"Environment variable {env_var} does not contain a valid {KEY_SIZE}-byte key"
    )
    return None
