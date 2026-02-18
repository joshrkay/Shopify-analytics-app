"""
Platform credentials management service.

Handles secure retrieval and management of external platform credentials
for action execution.

SECURITY:
- Credentials are encrypted at rest in the database via Fernet (src.platform.secrets)
- Decrypted only when needed for API calls
- Access is scoped to tenant via tenant_id from JWT
- Supports credential rotation and validation

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.connector_credential import ConnectorCredential, CredentialStatus
from src.platform.secrets import encrypt_secret, decrypt_secret
from src.services.platform_executors import (
    MetaCredentials,
    GoogleAdsCredentials,
    MetaAdsExecutor,
    GoogleAdsExecutor,
    BasePlatformExecutor,
    RetryConfig,
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


# Maps Platform enum value to ConnectorCredential.source_type stored in DB
_PLATFORM_TO_SOURCE_TYPE: dict[str, str] = {
    "meta": "meta_ads",
    "google": "google_ads",
    "shopify": "shopify",
}


@dataclass
class CredentialValidation:
    """Result of credential validation."""
    is_valid: bool
    status: CredentialStatus
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
    - Fetching encrypted credentials from database
    - Decrypting credentials for use
    - Validating credential status
    - Creating platform executors

    SECURITY:
    - tenant_id must come from JWT, never from client input
    - Credentials are decrypted only when needed
    - Failed validation triggers notifications
    """

    def __init__(
        self,
        db_session: Session,
        encryption_key: Optional[str] = None,
    ):
        """
        Initialize the credentials service.

        Args:
            db_session: Database session for querying credentials
            encryption_key: Key for decrypting stored credentials
        """
        self.db = db_session
        self.encryption_key = encryption_key

    # =========================================================================
    # Credential Retrieval
    # =========================================================================

    async def get_meta_credentials(self, tenant_id: str) -> Optional[MetaCredentials]:
        """
        Get Meta (Facebook) API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            MetaCredentials if found and valid, None otherwise
        """
        record = await self._fetch_active_credential(tenant_id, "meta_ads")
        if record is None:
            return None
        try:
            data = await self._decrypt_credentials(record.encrypted_payload)
            return MetaCredentials(
                access_token=data["access_token"],
                ad_account_id=data["ad_account_id"],
            )
        except (KeyError, Exception) as exc:
            logger.error(
                "Failed to decode Meta credentials",
                extra={"tenant_id": tenant_id, "error": str(exc)},
            )
            return None

    async def get_google_credentials(self, tenant_id: str) -> Optional[GoogleAdsCredentials]:
        """
        Get Google Ads API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            GoogleAdsCredentials if found and valid, None otherwise
        """
        record = await self._fetch_active_credential(tenant_id, "google_ads")
        if record is None:
            return None
        try:
            data = await self._decrypt_credentials(record.encrypted_payload)
            return GoogleAdsCredentials(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                developer_token=data["developer_token"],
                customer_id=data["customer_id"],
                login_customer_id=data.get("login_customer_id"),
            )
        except (KeyError, Exception) as exc:
            logger.error(
                "Failed to decode Google credentials",
                extra={"tenant_id": tenant_id, "error": str(exc)},
            )
            return None

    async def get_credentials_for_platform(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> Optional[Union[MetaCredentials, GoogleAdsCredentials]]:
        """
        Get credentials for a specific platform.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            Platform-specific credentials if found, None otherwise
        """
        if platform == Platform.META:
            return await self.get_meta_credentials(tenant_id)
        elif platform == Platform.GOOGLE:
            return await self.get_google_credentials(tenant_id)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return None

    # =========================================================================
    # Executor Factory
    # =========================================================================

    async def get_executor_for_platform(
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
        credentials = await self.get_credentials_for_platform(tenant_id, platform)

        if credentials is None:
            logger.warning(
                "No credentials available for platform",
                extra={"tenant_id": tenant_id, "platform": platform.value},
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
        credentials = await self.get_credentials_for_platform(tenant_id, platform)

        if credentials is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatus.MISSING,
                message=f"No {platform.value} credentials configured",
                platform=platform,
                needs_reauth=True,
            )

        executor = await self.get_executor_for_platform(tenant_id, platform)

        if executor is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatus.INVALID,
                message=f"Failed to create executor for {platform.value}",
                platform=platform,
                needs_reauth=True,
            )

        if not executor.validate_credentials():
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatus.INVALID,
                message=f"Credentials validation failed for {platform.value}",
                platform=platform,
                needs_reauth=True,
            )

        return CredentialValidation(
            is_valid=True,
            status=CredentialStatus.ACTIVE,
            message="Credentials are valid",
            platform=platform,
        )

    async def check_credentials_exist(
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
        return await self.get_credentials_for_platform(tenant_id, platform) is not None

    # =========================================================================
    # Credential Management
    # =========================================================================

    async def store_credentials(
        self,
        tenant_id: str,
        platform: Platform,
        credentials: dict,
        created_by: str = "system",
    ) -> bool:
        """
        Store encrypted credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform
            credentials: Credential data to encrypt and store
            created_by: Clerk user ID of the storing user

        Returns:
            True if stored successfully, False otherwise
        """
        source_type = _PLATFORM_TO_SOURCE_TYPE.get(platform.value, platform.value)
        try:
            encrypted_payload = await self._encrypt_credentials(credentials)
            record = ConnectorCredential(
                tenant_id=tenant_id,
                credential_name=f"{platform.value.title()} Ads Credentials",
                source_type=source_type,
                encrypted_payload=encrypted_payload,
                credential_metadata={"platform": platform.value},
                status=CredentialStatus.ACTIVE,
                created_by=created_by,
                soft_deleted_at=None,
                hard_delete_after=None,
            )
            self.db.add(record)
            self.db.commit()
            logger.info(
                "Stored platform credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value},
            )
            return True
        except Exception as exc:
            self.db.rollback()
            logger.error(
                "Failed to store credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value, "error": str(exc)},
            )
            return False

    def revoke_credentials(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> bool:
        """
        Revoke/deactivate credentials for a tenant.

        Sets status to REVOKED and records soft_deleted_at timestamp.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            True if revoked successfully, False otherwise
        """
        source_type = _PLATFORM_TO_SOURCE_TYPE.get(platform.value, platform.value)
        try:
            stmt = (
                select(ConnectorCredential)
                .where(ConnectorCredential.tenant_id == tenant_id)
                .where(ConnectorCredential.source_type == source_type)
                .where(ConnectorCredential.soft_deleted_at.is_(None))
                .where(ConnectorCredential.status == CredentialStatus.ACTIVE)
            )
            record = self.db.execute(stmt).scalar_one_or_none()
            if record is None:
                logger.warning(
                    "No active credentials found to revoke",
                    extra={"tenant_id": tenant_id, "platform": platform.value},
                )
                return False
            record.status = CredentialStatus.REVOKED
            record.soft_deleted_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.info(
                "Revoked platform credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value},
            )
            return True
        except Exception as exc:
            self.db.rollback()
            logger.error(
                "Failed to revoke credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value, "error": str(exc)},
            )
            return False

    # =========================================================================
    # Encryption Helpers
    # =========================================================================

    async def _fetch_active_credential(
        self, tenant_id: str, source_type: str
    ) -> Optional[ConnectorCredential]:
        """Query the DB for an active, non-soft-deleted credential record."""
        stmt = (
            select(ConnectorCredential)
            .where(ConnectorCredential.tenant_id == tenant_id)
            .where(ConnectorCredential.source_type == source_type)
            .where(ConnectorCredential.soft_deleted_at.is_(None))
            .where(ConnectorCredential.status == CredentialStatus.ACTIVE)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    async def _encrypt_credentials(self, data: dict) -> str:
        """
        Encrypt credential data for storage using Fernet via src.platform.secrets.

        Args:
            data: Credential dictionary to encrypt

        Returns:
            Fernet-encrypted string safe for DB storage
        """
        return await encrypt_secret(json.dumps(data))

    async def _decrypt_credentials(self, encrypted_data: str) -> dict:
        """
        Decrypt credential data from storage.

        Args:
            encrypted_data: Fernet-encrypted credential string

        Returns:
            Decrypted credential dictionary
        """
        plaintext = await decrypt_secret(encrypted_data)
        return json.loads(plaintext)


# =============================================================================
# Factory Function
# =============================================================================

def get_platform_credentials_service(
    db_session: Session,
    encryption_key: Optional[str] = None,
) -> PlatformCredentialsService:
    """
    Factory function to create a PlatformCredentialsService.

    Args:
        db_session: Database session
        encryption_key: Unused — encryption handled by src.platform.secrets

    Returns:
        Configured PlatformCredentialsService instance
    """
    return PlatformCredentialsService(
        db_session=db_session,
        encryption_key=encryption_key,
    )
