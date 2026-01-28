"""
Credential encryption utilities.

Wraps the platform secrets module for credential-specific encryption.

SECURITY REQUIREMENTS:
- Uses Fernet symmetric encryption via ENCRYPTION_KEY env var
- No plaintext tokens outside process memory
- Encryption validation on startup
- Clear error messages without exposing sensitive data

Usage:
    from src.credentials.encryption import encrypt_token, decrypt_token
    
    # Encrypt before storage
    encrypted = await encrypt_token(access_token)
    
    # Decrypt for use (in memory only)
    plaintext = await decrypt_token(encrypted)
"""

import logging
from typing import Optional

from src.platform.secrets import (
    encrypt_secret,
    decrypt_secret,
    EncryptionError,
    validate_encryption_configured,
)

logger = logging.getLogger(__name__)


class CredentialEncryptionError(Exception):
    """Raised when credential encryption/decryption fails."""

    def __init__(self, message: str, operation: str = "unknown"):
        self.operation = operation
        super().__init__(message)


async def encrypt_token(plaintext: str) -> str:
    """
    Encrypt an OAuth token for secure storage.

    SECURITY:
    - Input is never logged
    - Uses Fernet encryption with ENCRYPTION_KEY
    - Returns base64-encoded ciphertext safe for database storage

    Args:
        plaintext: The token to encrypt (access_token or refresh_token)

    Returns:
        Encrypted string safe for database storage

    Raises:
        CredentialEncryptionError: If encryption fails
        ValueError: If plaintext is empty
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty token")

    if not validate_encryption_configured():
        logger.error(
            "Encryption not configured",
            extra={"operation": "encrypt_token"}
        )
        raise CredentialEncryptionError(
            "Encryption key not configured. Set ENCRYPTION_KEY environment variable.",
            operation="encrypt"
        )

    try:
        encrypted = await encrypt_secret(plaintext)
        logger.debug(
            "Token encrypted successfully",
            extra={"operation": "encrypt_token", "result": "success"}
        )
        return encrypted
    except EncryptionError as e:
        logger.error(
            "Token encryption failed",
            extra={"operation": "encrypt_token", "error_type": type(e).__name__}
        )
        raise CredentialEncryptionError(
            "Failed to encrypt token",
            operation="encrypt"
        ) from e


async def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt an encrypted OAuth token.

    SECURITY:
    - Decrypted value must NEVER be logged
    - Decrypted value should only exist in memory
    - Clear memory after use when possible

    Args:
        ciphertext: The encrypted token from database

    Returns:
        Decrypted plaintext token (handle with care!)

    Raises:
        CredentialEncryptionError: If decryption fails
        ValueError: If ciphertext is empty
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty ciphertext")

    if not validate_encryption_configured():
        logger.error(
            "Encryption not configured",
            extra={"operation": "decrypt_token"}
        )
        raise CredentialEncryptionError(
            "Encryption key not configured. Set ENCRYPTION_KEY environment variable.",
            operation="decrypt"
        )

    try:
        decrypted = await decrypt_secret(ciphertext)
        logger.debug(
            "Token decrypted successfully",
            extra={"operation": "decrypt_token", "result": "success"}
        )
        return decrypted
    except EncryptionError as e:
        logger.error(
            "Token decryption failed",
            extra={"operation": "decrypt_token", "error_type": type(e).__name__}
        )
        raise CredentialEncryptionError(
            "Failed to decrypt token. Token may be corrupted or encryption key changed.",
            operation="decrypt"
        ) from e


async def rotate_encryption(
    old_ciphertext: str,
    new_encryption_key: Optional[str] = None
) -> str:
    """
    Re-encrypt a token, optionally with a new key.

    Used during key rotation procedures.

    Args:
        old_ciphertext: Currently encrypted token
        new_encryption_key: New key to use (if None, uses current key)

    Returns:
        Newly encrypted token

    Raises:
        CredentialEncryptionError: If rotation fails
    """
    # Decrypt with current key
    plaintext = await decrypt_token(old_ciphertext)

    try:
        # Re-encrypt (with current or new key)
        # Note: Key rotation requires environment variable update
        # This is a placeholder for future key rotation support
        new_ciphertext = await encrypt_token(plaintext)
        return new_ciphertext
    finally:
        # Clear plaintext from memory (best effort)
        # Python doesn't guarantee immediate memory clearing
        del plaintext


def validate_encryption_ready() -> bool:
    """
    Validate that encryption is properly configured.

    Call this during application startup to fail fast if encryption
    is not configured.

    Returns:
        True if encryption is configured

    Raises:
        CredentialEncryptionError: If encryption is not configured
    """
    if not validate_encryption_configured():
        raise CredentialEncryptionError(
            "ENCRYPTION_KEY environment variable is required for credential storage. "
            "Set this in your environment or Render dashboard.",
            operation="validate"
        )

    logger.info("Credential encryption validated successfully")
    return True
