"""
Platform credentials management service.

Handles secure retrieval and management of external platform credentials
for action execution.

SECURITY:
- Credentials are encrypted at rest using AES-256-GCM
- Decrypted only when needed for API calls
- Access is scoped to tenant via tenant_id from JWT
- Supports credential rotation and validation

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.models.platform_credential import (
    PlatformCredential,
    PlatformType,
    CredentialStatus as DBCredentialStatus,
)
from src.services.platform_executors import (
    MetaCredentials,
    GoogleAdsCredentials,
    ShopifyCredentials,
    MetaAdsExecutor,
    GoogleAdsExecutor,
    ShopifyExecutor,
    BasePlatformExecutor,
    RetryConfig,
)
from src.utils.encryption import (
    CredentialEncryptor,
    DecryptionError,
    EncryptionError,
    InvalidKeyError,
    get_encryption_key_from_env,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Supported Platforms
# =============================================================================

class Platform(str, Enum):
    """Supported external platforms for action execution."""
    META = "meta"
    GOOGLE = "google"
    SHOPIFY = "shopify"


# =============================================================================
# Credential Status (API-facing)
# =============================================================================

class CredentialStatusAPI(str, Enum):
    """Status of platform credentials (API response)."""
    ACTIVE = "active"          # Credentials are valid and usable
    EXPIRED = "expired"        # OAuth tokens have expired
    REVOKED = "revoked"        # Access has been revoked by user
    INVALID = "invalid"        # Credentials failed validation
    MISSING = "missing"        # No credentials configured


@dataclass
class CredentialValidation:
    """Result of credential validation."""
    is_valid: bool
    status: CredentialStatusAPI
    message: str
    platform: Platform
    needs_reauth: bool = False


# =============================================================================
# Platform Credentials Service
# =============================================================================

class PlatformCredentialsService:
    """
    Service for managing platform credentials.

    Handles:
    - Storing encrypted credentials in database
    - Fetching and decrypting credentials for use
    - Validating credential status
    - Creating platform executors
    - Credential revocation

    SECURITY:
    - tenant_id must come from JWT, never from client input
    - Credentials are encrypted with AES-256-GCM before storage
    - Decrypted only when needed
    - Failed validation triggers notifications
    """

    def __init__(
        self,
        db_session: Session,
        encryption_key: Optional[bytes] = None,
    ):
        """
        Initialize the credentials service.

        Args:
            db_session: Database session for querying credentials
            encryption_key: 32-byte key for AES-256-GCM encryption.
                          If not provided, reads from CREDENTIAL_ENCRYPTION_KEY env var.
        """
        self.db = db_session

        # Initialize encryptor
        if encryption_key:
            self._encryptor = CredentialEncryptor(key=encryption_key)
        else:
            key = get_encryption_key_from_env()
            if key:
                self._encryptor = CredentialEncryptor(key=key)
            else:
                logger.warning(
                    "No encryption key provided. Credential operations will fail. "
                    "Set CREDENTIAL_ENCRYPTION_KEY environment variable."
                )
                self._encryptor = None

    def _ensure_encryptor(self) -> CredentialEncryptor:
        """Ensure encryptor is available, raise if not."""
        if self._encryptor is None:
            raise InvalidKeyError(
                "Encryption key not configured. "
                "Set CREDENTIAL_ENCRYPTION_KEY environment variable."
            )
        return self._encryptor

    # =========================================================================
    # Credential Retrieval
    # =========================================================================

    def _get_credential_record(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> Optional[PlatformCredential]:
        """
        Get credential record from database.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            PlatformCredential if found, None otherwise
        """
        platform_type = PlatformType(platform.value)

        result = self.db.execute(
            select(PlatformCredential)
            .where(
                and_(
                    PlatformCredential.tenant_id == tenant_id,
                    PlatformCredential.platform == platform_type,
                )
            )
        ).scalar_one_or_none()

        return result

    def _decrypt_credential_data(
        self,
        record: PlatformCredential,
    ) -> Dict[str, Any]:
        """
        Decrypt credential data from database record.

        Args:
            record: PlatformCredential database record

        Returns:
            Decrypted credential dictionary

        Raises:
            DecryptionError: If decryption fails
        """
        encryptor = self._ensure_encryptor()

        # Associated data for additional authentication
        associated_data = f"{record.tenant_id}:{record.platform.value}".encode("utf-8")

        return encryptor.decrypt(
            ciphertext=record.encrypted_data,
            nonce=record.encryption_nonce,
            auth_tag=record.auth_tag,
            associated_data=associated_data,
        )

    def get_meta_credentials(self, tenant_id: str) -> Optional[MetaCredentials]:
        """
        Get Meta (Facebook) API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            MetaCredentials if found and valid, None otherwise
        """
        record = self._get_credential_record(tenant_id, Platform.META)

        if not record:
            logger.debug(
                "No Meta credentials found",
                extra={"tenant_id": tenant_id}
            )
            return None

        if not record.is_active:
            logger.warning(
                "Meta credentials not active",
                extra={"tenant_id": tenant_id, "status": record.status.value}
            )
            return None

        try:
            data = self._decrypt_credential_data(record)
            return MetaCredentials(
                access_token=data["access_token"],
                ad_account_id=data["ad_account_id"],
            )
        except (DecryptionError, KeyError) as e:
            logger.error(
                "Failed to decrypt Meta credentials",
                extra={"tenant_id": tenant_id, "error": str(e)}
            )
            return None

    def get_google_credentials(self, tenant_id: str) -> Optional[GoogleAdsCredentials]:
        """
        Get Google Ads API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            GoogleAdsCredentials if found and valid, None otherwise
        """
        record = self._get_credential_record(tenant_id, Platform.GOOGLE)

        if not record:
            logger.debug(
                "No Google credentials found",
                extra={"tenant_id": tenant_id}
            )
            return None

        if not record.is_active:
            logger.warning(
                "Google credentials not active",
                extra={"tenant_id": tenant_id, "status": record.status.value}
            )
            return None

        try:
            data = self._decrypt_credential_data(record)
            return GoogleAdsCredentials(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                developer_token=data["developer_token"],
                customer_id=data["customer_id"],
                login_customer_id=data.get("login_customer_id"),
            )
        except (DecryptionError, KeyError) as e:
            logger.error(
                "Failed to decrypt Google credentials",
                extra={"tenant_id": tenant_id, "error": str(e)}
            )
            return None

    def get_shopify_credentials(self, tenant_id: str) -> Optional[ShopifyCredentials]:
        """
        Get Shopify API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            ShopifyCredentials if found and valid, None otherwise
        """
        record = self._get_credential_record(tenant_id, Platform.SHOPIFY)

        if not record:
            logger.debug(
                "No Shopify credentials found",
                extra={"tenant_id": tenant_id}
            )
            return None

        if not record.is_active:
            logger.warning(
                "Shopify credentials not active",
                extra={"tenant_id": tenant_id, "status": record.status.value}
            )
            return None

        try:
            data = self._decrypt_credential_data(record)
            return ShopifyCredentials(
                access_token=data["access_token"],
                shop_domain=data["shop_domain"],
            )
        except (DecryptionError, KeyError) as e:
            logger.error(
                "Failed to decrypt Shopify credentials",
                extra={"tenant_id": tenant_id, "error": str(e)}
            )
            return None

    def get_credentials_for_platform(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> Optional[Union[MetaCredentials, GoogleAdsCredentials, ShopifyCredentials]]:
        """
        Get credentials for a specific platform.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            Platform-specific credentials if found, None otherwise
        """
        if platform == Platform.META:
            return self.get_meta_credentials(tenant_id)
        elif platform == Platform.GOOGLE:
            return self.get_google_credentials(tenant_id)
        elif platform == Platform.SHOPIFY:
            return self.get_shopify_credentials(tenant_id)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return None

    # =========================================================================
    # Executor Factory
    # =========================================================================

    def get_executor_for_platform(
        self,
        tenant_id: str,
        platform: Platform,
        retry_config: Optional[RetryConfig] = None,
    ) -> Optional[BasePlatformExecutor]:
        """
        Get a configured executor for a platform.

        This is the main entry point for obtaining an executor ready
        for action execution.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform
            retry_config: Optional retry configuration

        Returns:
            Configured platform executor, or None if credentials unavailable
        """
        credentials = self.get_credentials_for_platform(tenant_id, platform)

        if credentials is None:
            logger.warning(
                "No credentials available for platform",
                extra={"tenant_id": tenant_id, "platform": platform.value}
            )
            return None

        if platform == Platform.META:
            return MetaAdsExecutor(
                credentials=credentials,
                retry_config=retry_config,
            )
        elif platform == Platform.GOOGLE:
            return GoogleAdsExecutor(
                credentials=credentials,
                retry_config=retry_config,
            )
        elif platform == Platform.SHOPIFY:
            return ShopifyExecutor(
                credentials=credentials,
                retry_config=retry_config,
            )
        else:
            logger.error(f"No executor available for platform: {platform}")
            return None

    # =========================================================================
    # Credential Validation
    # =========================================================================

    async def validate_credentials(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> CredentialValidation:
        """
        Validate that credentials for a platform are valid and usable.

        This performs a lightweight API call to verify credentials work.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            CredentialValidation with status and details
        """
        record = self._get_credential_record(tenant_id, platform)

        if record is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.MISSING,
                message=f"No {platform.value} credentials configured",
                platform=platform,
                needs_reauth=True,
            )

        if record.is_revoked:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.REVOKED,
                message=f"{platform.value} credentials have been revoked",
                platform=platform,
                needs_reauth=True,
            )

        if record.is_expired:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.EXPIRED,
                message=f"{platform.value} access token has expired",
                platform=platform,
                needs_reauth=True,
            )

        # Get executor for API validation
        executor = self.get_executor_for_platform(tenant_id, platform)

        if executor is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.INVALID,
                message=f"Failed to create executor for {platform.value}",
                platform=platform,
                needs_reauth=True,
            )

        # Validate credentials format via executor
        if not executor.validate_credentials():
            record.mark_invalid("Credential format validation failed")
            self.db.commit()

            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.INVALID,
                message=f"Credentials validation failed for {platform.value}",
                platform=platform,
                needs_reauth=True,
            )

        # Perform API connection test
        try:
            # Use a lightweight API call to test connectivity
            if hasattr(executor, 'test_connection'):
                await executor.test_connection()

            # Update last validated timestamp
            record.mark_active()
            self.db.commit()

            return CredentialValidation(
                is_valid=True,
                status=CredentialStatusAPI.ACTIVE,
                message="Credentials are valid",
                platform=platform,
            )

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "Credential validation API call failed",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "error": error_msg,
                }
            )

            # Check for auth-related errors
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                record.mark_expired()
                self.db.commit()
                return CredentialValidation(
                    is_valid=False,
                    status=CredentialStatusAPI.EXPIRED,
                    message="Access token has expired",
                    platform=platform,
                    needs_reauth=True,
                )

            record.mark_invalid(error_msg[:500])
            self.db.commit()

            return CredentialValidation(
                is_valid=False,
                status=CredentialStatusAPI.INVALID,
                message=f"API validation failed: {error_msg[:200]}",
                platform=platform,
                needs_reauth=True,
            )

    def check_credentials_exist(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> bool:
        """
        Quick check if credentials exist (without validation).

        Args:
            tenant_id: Tenant identifier
            platform: Target platform

        Returns:
            True if credentials exist, False otherwise
        """
        record = self._get_credential_record(tenant_id, platform)
        return record is not None and record.is_active

    # =========================================================================
    # Credential Management
    # =========================================================================

    def store_credentials(
        self,
        tenant_id: str,
        platform: Platform,
        credentials: Dict[str, Any],
        label: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        """
        Store encrypted credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform
            credentials: Credential data to encrypt and store
            label: Optional user-friendly label
            expires_at: Optional expiration time for OAuth tokens

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            encryptor = self._ensure_encryptor()

            # Check for existing credentials
            existing = self._get_credential_record(tenant_id, platform)

            # Associated data for additional authentication
            platform_type = PlatformType(platform.value)
            associated_data = f"{tenant_id}:{platform.value}".encode("utf-8")

            # Encrypt credentials
            ciphertext, nonce, auth_tag = encryptor.encrypt(
                credentials,
                associated_data=associated_data,
            )

            if existing:
                # Update existing record
                existing.encrypted_data = ciphertext
                existing.encryption_nonce = nonce
                existing.auth_tag = auth_tag
                existing.status = DBCredentialStatus.PENDING
                existing.label = label or existing.label
                existing.expires_at = expires_at
                existing.validation_error = None
                existing.revoked_at = None
                existing.revoked_by = None

                logger.info(
                    "Updated platform credentials",
                    extra={"tenant_id": tenant_id, "platform": platform.value}
                )
            else:
                # Create new record
                record = PlatformCredential(
                    tenant_id=tenant_id,
                    platform=platform_type,
                    encrypted_data=ciphertext,
                    encryption_nonce=nonce,
                    auth_tag=auth_tag,
                    status=DBCredentialStatus.PENDING,
                    label=label,
                    expires_at=expires_at,
                )
                self.db.add(record)

                logger.info(
                    "Stored new platform credentials",
                    extra={"tenant_id": tenant_id, "platform": platform.value}
                )

            self.db.commit()
            return True

        except (EncryptionError, InvalidKeyError) as e:
            logger.error(
                "Failed to encrypt credentials",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "error": str(e),
                }
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to store credentials",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "error": str(e),
                }
            )
            self.db.rollback()
            return False

    def revoke_credentials(
        self,
        tenant_id: str,
        platform: Platform,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Revoke/deactivate credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform
            user_id: Optional user ID who initiated revocation

        Returns:
            True if revoked successfully, False otherwise
        """
        try:
            record = self._get_credential_record(tenant_id, platform)

            if not record:
                logger.warning(
                    "No credentials to revoke",
                    extra={"tenant_id": tenant_id, "platform": platform.value}
                )
                return False

            record.mark_revoked(user_id)
            self.db.commit()

            logger.info(
                "Revoked platform credentials",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "revoked_by": user_id,
                }
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to revoke credentials",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "error": str(e),
                }
            )
            self.db.rollback()
            return False

    def delete_credentials(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> bool:
        """
        Permanently delete credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            record = self._get_credential_record(tenant_id, platform)

            if not record:
                logger.warning(
                    "No credentials to delete",
                    extra={"tenant_id": tenant_id, "platform": platform.value}
                )
                return False

            self.db.delete(record)
            self.db.commit()

            logger.info(
                "Deleted platform credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value}
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to delete credentials",
                extra={
                    "tenant_id": tenant_id,
                    "platform": platform.value,
                    "error": str(e),
                }
            )
            self.db.rollback()
            return False

    def get_credential_status(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> Dict[str, Any]:
        """
        Get current status of credentials without decrypting.

        Args:
            tenant_id: Tenant identifier
            platform: Target platform

        Returns:
            Dictionary with credential status info
        """
        record = self._get_credential_record(tenant_id, platform)

        if not record:
            return {
                "exists": False,
                "status": CredentialStatusAPI.MISSING.value,
                "platform": platform.value,
            }

        return {
            "exists": True,
            "status": record.status.value,
            "platform": platform.value,
            "label": record.label,
            "last_validated_at": record.last_validated_at.isoformat() if record.last_validated_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "is_expired": record.is_expired,
            "needs_reauth": record.needs_reauth,
            "validation_error": record.validation_error,
        }


# =============================================================================
# Factory Function
# =============================================================================

def get_platform_credentials_service(
    db_session: Session,
    encryption_key: Optional[bytes] = None,
) -> PlatformCredentialsService:
    """
    Factory function to create a PlatformCredentialsService.

    Args:
        db_session: Database session
        encryption_key: Optional 32-byte encryption key

    Returns:
        Configured PlatformCredentialsService instance
    """
    return PlatformCredentialsService(
        db_session=db_session,
        encryption_key=encryption_key,
    )
