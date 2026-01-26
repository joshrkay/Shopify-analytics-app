"""
Credential storage service for secure OAuth credential management.

SECURITY REQUIREMENTS:
- Tokens are encrypted at rest before storage
- No plaintext tokens outside process memory
- Tenant-scoped access only (from JWT)
- Soft delete with retention windows:
  - Disconnect: 5 days
  - Uninstall: 20 days

Usage:
    store = CredentialStore(db_session, tenant_id)
    
    # Store new credentials
    cred = await store.store_credential(
        provider=CredentialProvider.SHOPIFY,
        access_token="shpat_xxx",
        refresh_token="refresh_xxx",
        account_name="My Store"
    )
    
    # Get decrypted token for use
    access_token = await store.get_access_token(credential_id)
    
    # Disconnect (soft delete with 5-day retention)
    await store.disconnect_credential(credential_id)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.models.oauth_credential import (
    OAuthCredential,
    CredentialStatus,
    CredentialProvider,
)
from src.credentials.encryption import encrypt_token, decrypt_token
from src.credentials.redaction import CredentialAuditLogger, AuditEventType

logger = logging.getLogger(__name__)

# Retention windows (days)
DISCONNECT_RETENTION_DAYS = 5
UNINSTALL_RETENTION_DAYS = 20


class CredentialStoreError(Exception):
    """Base exception for credential store errors."""
    pass


class CredentialNotFoundError(CredentialStoreError):
    """Credential not found or not accessible."""
    pass


class CredentialExpiredError(CredentialStoreError):
    """Credential tokens have expired."""
    pass


class CredentialInactiveError(CredentialStoreError):
    """Credential is inactive (disconnected or revoked)."""
    pass


@dataclass
class CredentialMetadata:
    """
    Credential metadata safe for API responses and logging.
    
    SECURITY: Does NOT include token values.
    """
    id: str
    tenant_id: str
    provider: str
    external_account_id: Optional[str]
    account_name: Optional[str]
    connector_name: Optional[str]
    status: str
    is_active: bool
    expires_at: Optional[datetime]
    last_refreshed_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: Optional[datetime]


class CredentialStore:
    """
    Service for secure OAuth credential storage.

    All methods require tenant_id from JWT context for tenant isolation.
    Tokens are encrypted before storage and decrypted only when needed.
    """

    def __init__(self, db_session: Session, tenant_id: str):
        """
        Initialize credential store.

        Args:
            db_session: Database session
            tenant_id: Tenant ID from JWT (org_id)

        Raises:
            ValueError: If tenant_id is not provided
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.audit = CredentialAuditLogger(tenant_id)

    async def store_credential(
        self,
        provider: CredentialProvider,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        scopes: Optional[List[str]] = None,
        external_account_id: Optional[str] = None,
        account_name: Optional[str] = None,
        connector_name: Optional[str] = None,
        store_id: Optional[str] = None,
    ) -> OAuthCredential:
        """
        Store new OAuth credentials with encryption.

        SECURITY:
        - Tokens are encrypted before storage
        - Plaintext tokens are not logged
        - Audit event is logged

        Args:
            provider: OAuth provider (shopify, google_ads, etc.)
            access_token: Access token to encrypt and store
            refresh_token: Optional refresh token to encrypt and store
            expires_at: When the access token expires
            scopes: List of granted OAuth scopes
            external_account_id: External account ID from provider
            account_name: Display name (allowed in logs)
            connector_name: User-friendly name (allowed in logs)
            store_id: Associated Shopify store ID (if applicable)

        Returns:
            Created OAuthCredential (without decrypted tokens)

        Raises:
            CredentialStoreError: If storage fails
        """
        # Encrypt tokens
        access_token_encrypted = await encrypt_token(access_token)
        refresh_token_encrypted = None
        if refresh_token:
            refresh_token_encrypted = await encrypt_token(refresh_token)

        # Check for existing credential
        existing = self._get_existing_credential(provider, external_account_id)
        if existing:
            # Update existing credential
            return await self._update_credential(
                existing,
                access_token_encrypted=access_token_encrypted,
                refresh_token_encrypted=refresh_token_encrypted,
                expires_at=expires_at,
                scopes=scopes,
                account_name=account_name,
                connector_name=connector_name,
            )

        # Create new credential
        credential = OAuthCredential(
            tenant_id=self.tenant_id,
            provider=provider,
            external_account_id=external_account_id,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            expires_at=expires_at,
            scopes=json.dumps(scopes) if scopes else None,
            account_name=account_name,
            connector_name=connector_name,
            store_id=store_id,
            status=CredentialStatus.ACTIVE,
            is_active=True,
        )

        self.db.add(credential)
        self.db.flush()

        # Audit log (tokens are NOT logged)
        self.audit.log(
            event_type=AuditEventType.CREDENTIAL_STORED,
            credential_id=credential.id,
            provider=provider.value,
            account_name=account_name,
            connector_name=connector_name,
        )

        logger.info(
            "Credential stored",
            extra={
                "credential_id": credential.id,
                "tenant_id": self.tenant_id,
                "provider": provider.value,
                "account_name": account_name,  # Allowed per PII policy
                "connector_name": connector_name,  # Allowed per PII policy
            }
        )

        return credential

    async def _update_credential(
        self,
        credential: OAuthCredential,
        access_token_encrypted: str,
        refresh_token_encrypted: Optional[str],
        expires_at: Optional[datetime],
        scopes: Optional[List[str]],
        account_name: Optional[str],
        connector_name: Optional[str],
    ) -> OAuthCredential:
        """Update existing credential with new tokens."""
        credential.access_token_encrypted = access_token_encrypted
        if refresh_token_encrypted:
            credential.refresh_token_encrypted = refresh_token_encrypted
        credential.expires_at = expires_at
        if scopes:
            credential.scopes = json.dumps(scopes)
        if account_name:
            credential.account_name = account_name
        if connector_name:
            credential.connector_name = connector_name

        # Reactivate if previously disconnected
        credential.status = CredentialStatus.ACTIVE
        credential.is_active = True
        credential.disconnected_at = None
        credential.scheduled_purge_at = None
        credential.last_refreshed_at = datetime.now(timezone.utc)

        self.db.flush()

        self.audit.log(
            event_type=AuditEventType.CREDENTIAL_STORED,
            credential_id=credential.id,
            provider=credential.provider.value,
            account_name=account_name,
            connector_name=connector_name,
            metadata={"action": "updated"}
        )

        return credential

    def _get_existing_credential(
        self,
        provider: CredentialProvider,
        external_account_id: Optional[str],
    ) -> Optional[OAuthCredential]:
        """Get existing credential for tenant/provider/account."""
        query = self.db.query(OAuthCredential).filter(
            OAuthCredential.tenant_id == self.tenant_id,
            OAuthCredential.provider == provider,
        )
        if external_account_id:
            query = query.filter(
                OAuthCredential.external_account_id == external_account_id
            )
        return query.first()

    def get_credential(self, credential_id: str) -> OAuthCredential:
        """
        Get credential by ID (tenant-scoped).

        SECURITY: Returns credential object, tokens remain encrypted.

        Args:
            credential_id: Credential ID

        Returns:
            OAuthCredential (tokens still encrypted)

        Raises:
            CredentialNotFoundError: If credential not found or not owned by tenant
        """
        credential = self.db.query(OAuthCredential).filter(
            OAuthCredential.id == credential_id,
            OAuthCredential.tenant_id == self.tenant_id,
        ).first()

        if not credential:
            raise CredentialNotFoundError(
                f"Credential not found: {credential_id}"
            )

        return credential

    def get_credential_metadata(self, credential_id: str) -> CredentialMetadata:
        """
        Get credential metadata safe for API responses.

        SECURITY: Does NOT include token values.

        Args:
            credential_id: Credential ID

        Returns:
            CredentialMetadata (no tokens)
        """
        credential = self.get_credential(credential_id)
        return CredentialMetadata(
            id=credential.id,
            tenant_id=credential.tenant_id,
            provider=credential.provider.value,
            external_account_id=credential.external_account_id,
            account_name=credential.account_name,
            connector_name=credential.connector_name,
            status=credential.status.value,
            is_active=credential.is_active,
            expires_at=credential.expires_at,
            last_refreshed_at=credential.last_refreshed_at,
            last_used_at=credential.last_used_at,
            created_at=credential.created_at,
        )

    def list_credentials(
        self,
        provider: Optional[CredentialProvider] = None,
        status: Optional[CredentialStatus] = None,
        active_only: bool = True,
    ) -> List[CredentialMetadata]:
        """
        List credentials for tenant (metadata only).

        SECURITY: Returns metadata only, no token values.

        Args:
            provider: Filter by provider
            status: Filter by status
            active_only: Only return active credentials

        Returns:
            List of CredentialMetadata (no tokens)
        """
        query = self.db.query(OAuthCredential).filter(
            OAuthCredential.tenant_id == self.tenant_id
        )

        if provider:
            query = query.filter(OAuthCredential.provider == provider)
        if status:
            query = query.filter(OAuthCredential.status == status)
        if active_only:
            query = query.filter(OAuthCredential.is_active == True)

        credentials = query.all()

        return [
            CredentialMetadata(
                id=c.id,
                tenant_id=c.tenant_id,
                provider=c.provider.value,
                external_account_id=c.external_account_id,
                account_name=c.account_name,
                connector_name=c.connector_name,
                status=c.status.value,
                is_active=c.is_active,
                expires_at=c.expires_at,
                last_refreshed_at=c.last_refreshed_at,
                last_used_at=c.last_used_at,
                created_at=c.created_at,
            )
            for c in credentials
        ]

    async def get_access_token(self, credential_id: str) -> str:
        """
        Get decrypted access token for use.

        SECURITY:
        - Decrypted token must NEVER be logged
        - Update last_used_at timestamp
        - Validate credential is active and not expired

        Args:
            credential_id: Credential ID

        Returns:
            Decrypted access token (handle with care!)

        Raises:
            CredentialNotFoundError: If credential not found
            CredentialInactiveError: If credential is inactive
            CredentialExpiredError: If token is expired and cannot refresh
        """
        credential = self.get_credential(credential_id)

        if not credential.is_active:
            raise CredentialInactiveError(
                f"Credential is inactive: {credential_id}"
            )

        if credential.is_token_expired and not credential.can_refresh:
            raise CredentialExpiredError(
                f"Token expired and cannot refresh: {credential_id}"
            )

        # Update last used timestamp
        credential.last_used_at = datetime.now(timezone.utc)
        self.db.flush()

        # Decrypt and return
        return await decrypt_token(credential.access_token_encrypted)

    async def get_refresh_token(self, credential_id: str) -> Optional[str]:
        """
        Get decrypted refresh token for token refresh.

        SECURITY: Decrypted token must NEVER be logged.

        Args:
            credential_id: Credential ID

        Returns:
            Decrypted refresh token or None if not available

        Raises:
            CredentialNotFoundError: If credential not found
        """
        credential = self.get_credential(credential_id)

        if not credential.refresh_token_encrypted:
            return None

        return await decrypt_token(credential.refresh_token_encrypted)

    async def disconnect_credential(self, credential_id: str) -> OAuthCredential:
        """
        Disconnect credential (soft delete with 5-day retention).

        RETENTION POLICY:
        - Mark credential as inactive immediately
        - Schedule purge of encrypted blob after 5 days
        - Audit event is logged

        Args:
            credential_id: Credential ID

        Returns:
            Updated OAuthCredential
        """
        credential = self.get_credential(credential_id)

        now = datetime.now(timezone.utc)
        credential.status = CredentialStatus.INACTIVE
        credential.is_active = False
        credential.disconnected_at = now
        credential.scheduled_purge_at = now + timedelta(days=DISCONNECT_RETENTION_DAYS)

        self.db.flush()

        self.audit.log(
            event_type=AuditEventType.CREDENTIAL_REVOKED,
            credential_id=credential.id,
            provider=credential.provider.value,
            account_name=credential.account_name,
            connector_name=credential.connector_name,
            metadata={
                "reason": "disconnect",
                "scheduled_purge_at": credential.scheduled_purge_at.isoformat(),
            }
        )

        logger.info(
            "Credential disconnected",
            extra={
                "credential_id": credential.id,
                "tenant_id": self.tenant_id,
                "scheduled_purge_at": credential.scheduled_purge_at.isoformat(),
            }
        )

        return credential

    async def mark_uninstall_pending(self, credential_id: str) -> OAuthCredential:
        """
        Mark credential for deletion due to app uninstall (20-day retention).

        RETENTION POLICY:
        - Mark tenant as pending_deletion
        - Schedule purge of encrypted blob after 20 days

        Args:
            credential_id: Credential ID

        Returns:
            Updated OAuthCredential
        """
        credential = self.get_credential(credential_id)

        now = datetime.now(timezone.utc)
        credential.status = CredentialStatus.PENDING_DELETION
        credential.is_active = False
        credential.disconnected_at = now
        credential.scheduled_purge_at = now + timedelta(days=UNINSTALL_RETENTION_DAYS)

        self.db.flush()

        self.audit.log(
            event_type=AuditEventType.CREDENTIAL_REVOKED,
            credential_id=credential.id,
            provider=credential.provider.value,
            account_name=credential.account_name,
            connector_name=credential.connector_name,
            metadata={
                "reason": "uninstall",
                "scheduled_purge_at": credential.scheduled_purge_at.isoformat(),
            }
        )

        logger.info(
            "Credential marked for uninstall deletion",
            extra={
                "credential_id": credential.id,
                "tenant_id": self.tenant_id,
                "scheduled_purge_at": credential.scheduled_purge_at.isoformat(),
            }
        )

        return credential

    async def purge_credential(self, credential_id: str) -> None:
        """
        Permanently purge encrypted tokens from credential.

        Called by retention job after retention window expires.

        SECURITY:
        - Removes encrypted token blobs
        - Keeps metadata for audit trail
        - Audit event is logged
        """
        credential = self.get_credential(credential_id)

        # Clear encrypted tokens
        credential.access_token_encrypted = None
        credential.refresh_token_encrypted = None
        credential.purged_at = datetime.now(timezone.utc)

        self.db.flush()

        self.audit.log(
            event_type=AuditEventType.CREDENTIAL_PURGED,
            credential_id=credential.id,
            provider=credential.provider.value,
            account_name=credential.account_name,
            connector_name=credential.connector_name,
        )

        logger.info(
            "Credential tokens purged",
            extra={
                "credential_id": credential.id,
                "tenant_id": self.tenant_id,
            }
        )

    def get_credentials_due_for_purge(self) -> List[OAuthCredential]:
        """
        Get credentials that are past their retention window.

        Used by scheduled purge job.

        Returns:
            List of credentials due for token purge
        """
        now = datetime.now(timezone.utc)
        return self.db.query(OAuthCredential).filter(
            OAuthCredential.scheduled_purge_at <= now,
            OAuthCredential.purged_at.is_(None),
            OAuthCredential.access_token_encrypted.isnot(None),
        ).all()

    def get_expiring_credentials(
        self,
        within_minutes: int = 30,
    ) -> List[OAuthCredential]:
        """
        Get credentials expiring soon (for scheduled refresh).

        Args:
            within_minutes: Look for credentials expiring within this window

        Returns:
            List of credentials that need refresh
        """
        threshold = datetime.now(timezone.utc) + timedelta(minutes=within_minutes)
        return self.db.query(OAuthCredential).filter(
            OAuthCredential.tenant_id == self.tenant_id,
            OAuthCredential.is_active == True,
            OAuthCredential.expires_at <= threshold,
            OAuthCredential.refresh_token_encrypted.isnot(None),
        ).all()
