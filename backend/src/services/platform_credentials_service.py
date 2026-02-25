"""
Platform credentials management service.

Handles secure retrieval and management of external platform credentials
for action execution.

SECURITY:
- Credentials are encrypted at rest in the database via Fernet
- Decrypted only when needed for API calls
- Access is scoped to tenant via tenant_id from JWT
- Supports credential rotation and validation

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.connector_credential import (
    ConnectorCredential,
    CredentialStatus,
    HARD_DELETE_AFTER_DAYS,
)
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


# Source type strings used in ConnectorCredential.source_type
_PLATFORM_SOURCE_TYPES = {
    Platform.META: "meta",
    Platform.GOOGLE: "google_ads",
    Platform.SHOPIFY: "shopify",
}


# CredentialStatus is imported from src.models.connector_credential
# (canonical source of truth for credential lifecycle status)


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
    # Internal Helpers
    # =========================================================================

    def _find_active_credential(
        self,
        tenant_id: str,
        source_type: str,
    ) -> Optional[ConnectorCredential]:
        """Query the database for an active, non-deleted credential."""
        stmt = (
            select(ConnectorCredential)
            .where(ConnectorCredential.tenant_id == tenant_id)
            .where(ConnectorCredential.source_type == source_type)
            .where(ConnectorCredential.status == CredentialStatus.ACTIVE)
            .where(ConnectorCredential.soft_deleted_at.is_(None))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    # =========================================================================
    # Credential Retrieval
    # =========================================================================

    def get_meta_credentials(self, tenant_id: str) -> Optional[MetaCredentials]:
        """
        Get Meta (Facebook) API credentials for a tenant.

        Args:
            tenant_id: Tenant identifier (from JWT only)

        Returns:
            MetaCredentials if found and valid, None otherwise
        """
        credential = self._find_active_credential(
            tenant_id, _PLATFORM_SOURCE_TYPES[Platform.META]
        )
        if not credential or not credential.encrypted_payload:
            return None

        try:
            decrypted = self._decrypt_credentials(credential.encrypted_payload)
            return MetaCredentials(
                access_token=decrypted["access_token"],
                ad_account_id=decrypted.get("ad_account_id", ""),
            )
        except Exception as e:
            logger.error(
                "Failed to decrypt Meta credentials",
                extra={"tenant_id": tenant_id, "error": str(e)},
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
        credential = self._find_active_credential(
            tenant_id, _PLATFORM_SOURCE_TYPES[Platform.GOOGLE]
        )
        if not credential or not credential.encrypted_payload:
            return None

        try:
            decrypted = self._decrypt_credentials(credential.encrypted_payload)
            return GoogleAdsCredentials(
                access_token=decrypted["access_token"],
                refresh_token=decrypted.get("refresh_token", ""),
                client_id=decrypted.get("client_id", ""),
                client_secret=decrypted.get("client_secret", ""),
                developer_token=decrypted.get("developer_token", ""),
                customer_id=decrypted.get("customer_id", ""),
                login_customer_id=decrypted.get("login_customer_id"),
            )
        except Exception as e:
            logger.error(
                "Failed to decrypt Google Ads credentials",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            return None

    def get_credentials_for_platform(
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
            return self.get_meta_credentials(tenant_id)
        elif platform == Platform.GOOGLE:
            return self.get_google_credentials(tenant_id)
        else:
            logger.error(
                "Unsupported platform for credential retrieval",
                extra={"platform": platform.value},
            )
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
        else:
            logger.error(
                "No executor available for platform",
                extra={"platform": platform.value},
            )
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
        credentials = self.get_credentials_for_platform(tenant_id, platform)

        if credentials is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatus.MISSING,
                message=f"No {platform.value} credentials configured",
                platform=platform,
                needs_reauth=True,
            )

        executor = self.get_executor_for_platform(tenant_id, platform)

        if executor is None:
            return CredentialValidation(
                is_valid=False,
                status=CredentialStatus.INVALID,
                message=f"Failed to create executor for {platform.value}",
                platform=platform,
                needs_reauth=True,
            )

        # Validate credentials via executor
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
        return self.get_credentials_for_platform(tenant_id, platform) is not None

    # =========================================================================
    # Credential Management
    # =========================================================================

    def store_credentials(
        self,
        tenant_id: str,
        platform: Platform,
        credentials: dict,
        credential_name: Optional[str] = None,
        created_by: str = "system",
    ) -> bool:
        """
        Store encrypted credentials for a tenant.

        Upserts: if an active credential exists for the tenant+platform,
        updates it in place. Otherwise creates a new record.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform
            credentials: Credential data to encrypt and store
            credential_name: Human-readable label
            created_by: clerk_user_id of the user storing credentials

        Returns:
            True if stored successfully, False otherwise
        """
        source_type = _PLATFORM_SOURCE_TYPES.get(platform, platform.value)
        encrypted_payload = self._encrypt_credentials(credentials)

        existing = self._find_active_credential(tenant_id, source_type)

        try:
            if existing:
                existing.encrypted_payload = encrypted_payload
                if credential_name:
                    existing.credential_name = credential_name
            else:
                record = ConnectorCredential(
                    tenant_id=tenant_id,
                    credential_name=credential_name or f"{platform.value} credentials",
                    source_type=source_type,
                    encrypted_payload=encrypted_payload,
                    status=CredentialStatus.ACTIVE,
                    created_by=created_by,
                    credential_metadata={},
                )
                self.db.add(record)

            self.db.flush()
            logger.info(
                "Credentials stored",
                extra={"tenant_id": tenant_id, "platform": platform.value},
            )
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to store credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value, "error": str(e)},
            )
            return False

    def revoke_credentials(
        self,
        tenant_id: str,
        platform: Platform,
    ) -> bool:
        """
        Revoke/deactivate credentials for a tenant.

        Soft-deletes the credential with a 5-day restoration window
        and schedules permanent wipe after 20 days.

        Args:
            tenant_id: Tenant identifier (from JWT only)
            platform: Target platform

        Returns:
            True if revoked successfully, False otherwise
        """
        source_type = _PLATFORM_SOURCE_TYPES.get(platform, platform.value)
        credential = self._find_active_credential(tenant_id, source_type)

        if not credential:
            logger.warning(
                "No active credential to revoke",
                extra={"tenant_id": tenant_id, "platform": platform.value},
            )
            return False

        try:
            now = datetime.now(timezone.utc)
            credential.status = CredentialStatus.REVOKED
            credential.soft_deleted_at = now
            credential.hard_delete_after = now + timedelta(days=HARD_DELETE_AFTER_DAYS)
            self.db.flush()

            logger.info(
                "Credentials revoked",
                extra={"tenant_id": tenant_id, "platform": platform.value},
            )
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(
                "Failed to revoke credentials",
                extra={"tenant_id": tenant_id, "platform": platform.value, "error": str(e)},
            )
            return False

    # =========================================================================
    # Encryption Helpers
    # =========================================================================

    def _encrypt_credentials(self, data: dict) -> str:
        """
        Encrypt credential data for storage.

        Uses the platform.secrets module (Fernet encryption via ENCRYPTION_KEY).

        Args:
            data: Credential dictionary to encrypt

        Returns:
            Encrypted string safe for database storage
        """
        plaintext = json.dumps(data)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            raise RuntimeError(
                "Cannot call _encrypt_credentials from running async loop; "
                "use await encrypt_secret() directly"
            )
        return asyncio.run(encrypt_secret(plaintext))

    def _decrypt_credentials(self, encrypted_data: str) -> dict:
        """
        Decrypt credential data from storage.

        Uses the platform.secrets module (Fernet encryption via ENCRYPTION_KEY).

        Args:
            encrypted_data: Encrypted credential string from database

        Returns:
            Decrypted credential dictionary
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            raise RuntimeError(
                "Cannot call _decrypt_credentials from running async loop; "
                "use await decrypt_secret() directly"
            )
        plaintext = asyncio.run(decrypt_secret(encrypted_data))
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
        encryption_key: Optional encryption key

    Returns:
        Configured PlatformCredentialsService instance
    """
    return PlatformCredentialsService(
        db_session=db_session,
        encryption_key=encryption_key,
    )
