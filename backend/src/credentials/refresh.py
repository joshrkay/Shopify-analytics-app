"""
Token refresh service for OAuth credentials.

Implements BOTH refresh strategies:
1. Scheduled refresh: Background job refreshes tokens before expiry
2. On-demand refresh: Refresh when token expires mid-sync

SECURITY REQUIREMENTS:
- Tokens are encrypted before storage
- No plaintext tokens in logs
- Audit events for all refresh operations

Usage:
    refresh_service = CredentialRefreshService(db_session, tenant_id)
    
    # On-demand refresh (during sync)
    result = await refresh_service.refresh_if_needed(credential_id)
    
    # Scheduled refresh (background job)
    results = await refresh_service.refresh_expiring_credentials()
"""

import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional, List, Callable, Awaitable
from enum import Enum

from sqlalchemy.orm import Session

from src.models.oauth_credential import (
    OAuthCredential,
    CredentialStatus,
    CredentialProvider,
)
from src.credentials.encryption import encrypt_token, decrypt_token
from src.credentials.redaction import CredentialAuditLogger, AuditEventType

logger = logging.getLogger(__name__)

# Refresh tokens that expire within this window
DEFAULT_REFRESH_WINDOW_MINUTES = 30


class RefreshError(Exception):
    """Base exception for token refresh errors."""
    pass


class RefreshNotNeededError(RefreshError):
    """Token does not need refresh."""
    pass


class RefreshNotPossibleError(RefreshError):
    """Token cannot be refreshed (no refresh token or expired)."""
    pass


class RefreshFailedError(RefreshError):
    """Token refresh failed with provider."""
    pass


class RefreshResultStatus(str, Enum):
    """Result status for refresh operations."""
    SUCCESS = "success"
    NOT_NEEDED = "not_needed"
    NOT_POSSIBLE = "not_possible"
    FAILED = "failed"


@dataclass
class RefreshResult:
    """
    Result of a token refresh operation.
    
    SECURITY: Does NOT include token values.
    """
    status: RefreshResultStatus
    credential_id: str
    provider: str
    new_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None


# Type for OAuth token refresh callbacks
# Signature: async (provider, refresh_token) -> (new_access_token, new_refresh_token, expires_in_seconds)
TokenRefreshCallback = Callable[
    [CredentialProvider, str],
    Awaitable[tuple[str, Optional[str], Optional[int]]]
]


class CredentialRefreshService:
    """
    Service for refreshing OAuth tokens.

    Supports both scheduled and on-demand refresh strategies.
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        refresh_callbacks: Optional[dict[CredentialProvider, TokenRefreshCallback]] = None,
    ):
        """
        Initialize refresh service.

        Args:
            db_session: Database session
            tenant_id: Tenant ID from JWT (org_id)
            refresh_callbacks: Provider-specific token refresh functions
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.refresh_callbacks = refresh_callbacks or {}
        self.audit = CredentialAuditLogger(tenant_id)

    def register_refresh_callback(
        self,
        provider: CredentialProvider,
        callback: TokenRefreshCallback,
    ) -> None:
        """
        Register a token refresh callback for a provider.

        Args:
            provider: OAuth provider
            callback: Async function to refresh tokens with the provider
        """
        self.refresh_callbacks[provider] = callback

    async def refresh_if_needed(
        self,
        credential_id: str,
        force: bool = False,
    ) -> RefreshResult:
        """
        Refresh credential if token is expired or expiring soon.

        ON-DEMAND REFRESH: Call this when using a credential during sync
        to ensure token is valid.

        Args:
            credential_id: Credential ID to refresh
            force: Force refresh even if token is not expired

        Returns:
            RefreshResult with status and new expiry time

        Raises:
            RefreshError: If refresh fails
        """
        credential = self._get_credential(credential_id)

        # Check if refresh is needed
        if not force and not self._needs_refresh(credential):
            return RefreshResult(
                status=RefreshResultStatus.NOT_NEEDED,
                credential_id=credential_id,
                provider=credential.provider.value,
            )

        # Check if refresh is possible
        if not credential.can_refresh:
            logger.warning(
                "Cannot refresh credential",
                extra={
                    "credential_id": credential_id,
                    "tenant_id": self.tenant_id,
                    "reason": "no_refresh_token" if not credential.refresh_token_encrypted else "refresh_token_expired",
                }
            )
            return RefreshResult(
                status=RefreshResultStatus.NOT_POSSIBLE,
                credential_id=credential_id,
                provider=credential.provider.value,
                error_message="Refresh token not available or expired",
            )

        return await self._do_refresh(credential)

    async def refresh_expiring_credentials(
        self,
        within_minutes: int = DEFAULT_REFRESH_WINDOW_MINUTES,
    ) -> List[RefreshResult]:
        """
        Refresh all credentials expiring within the given window.

        SCHEDULED REFRESH: Call this from a background job (e.g., every 15 minutes)
        to proactively refresh tokens before they expire.

        Args:
            within_minutes: Refresh credentials expiring within this window

        Returns:
            List of RefreshResults for all processed credentials
        """
        threshold = datetime.now(timezone.utc) + timedelta(minutes=within_minutes)

        expiring_credentials = self.db.query(OAuthCredential).filter(
            OAuthCredential.tenant_id == self.tenant_id,
            OAuthCredential.is_active == True,
            OAuthCredential.status == CredentialStatus.ACTIVE,
            OAuthCredential.expires_at <= threshold,
            OAuthCredential.refresh_token_encrypted.isnot(None),
        ).all()

        results = []
        for credential in expiring_credentials:
            try:
                result = await self._do_refresh(credential)
                results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to refresh credential in batch",
                    extra={
                        "credential_id": credential.id,
                        "tenant_id": self.tenant_id,
                        "error": str(e),
                    }
                )
                results.append(RefreshResult(
                    status=RefreshResultStatus.FAILED,
                    credential_id=credential.id,
                    provider=credential.provider.value,
                    error_message=str(e),
                ))

        logger.info(
            "Completed scheduled token refresh",
            extra={
                "tenant_id": self.tenant_id,
                "total": len(expiring_credentials),
                "success": sum(1 for r in results if r.status == RefreshResultStatus.SUCCESS),
                "failed": sum(1 for r in results if r.status == RefreshResultStatus.FAILED),
            }
        )

        return results

    def _get_credential(self, credential_id: str) -> OAuthCredential:
        """Get credential with tenant validation."""
        credential = self.db.query(OAuthCredential).filter(
            OAuthCredential.id == credential_id,
            OAuthCredential.tenant_id == self.tenant_id,
        ).first()

        if not credential:
            raise RefreshError(f"Credential not found: {credential_id}")

        return credential

    def _needs_refresh(
        self,
        credential: OAuthCredential,
        buffer_minutes: int = 5,
    ) -> bool:
        """
        Check if credential needs refresh.

        Considers a buffer to refresh slightly before actual expiry.
        """
        if not credential.expires_at:
            return False

        buffer = timedelta(minutes=buffer_minutes)
        return datetime.now(timezone.utc) >= (credential.expires_at - buffer)

    async def _do_refresh(self, credential: OAuthCredential) -> RefreshResult:
        """
        Perform the actual token refresh.

        SECURITY:
        - Tokens are decrypted only in memory
        - New tokens are encrypted before storage
        - Audit event is logged
        """
        provider = credential.provider

        # Check if we have a callback for this provider
        if provider not in self.refresh_callbacks:
            logger.error(
                "No refresh callback registered for provider",
                extra={
                    "credential_id": credential.id,
                    "provider": provider.value,
                }
            )
            return RefreshResult(
                status=RefreshResultStatus.FAILED,
                credential_id=credential.id,
                provider=provider.value,
                error_message=f"No refresh handler for provider: {provider.value}",
            )

        try:
            # Decrypt refresh token
            refresh_token = await decrypt_token(credential.refresh_token_encrypted)

            # Call provider-specific refresh
            callback = self.refresh_callbacks[provider]
            new_access_token, new_refresh_token, expires_in = await callback(
                provider, refresh_token
            )

            # Encrypt new tokens
            new_access_encrypted = await encrypt_token(new_access_token)
            new_refresh_encrypted = None
            if new_refresh_token:
                new_refresh_encrypted = await encrypt_token(new_refresh_token)

            # Calculate new expiry
            new_expires_at = None
            if expires_in:
                new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Update credential
            credential.access_token_encrypted = new_access_encrypted
            if new_refresh_encrypted:
                credential.refresh_token_encrypted = new_refresh_encrypted
            credential.expires_at = new_expires_at
            credential.last_refreshed_at = datetime.now(timezone.utc)
            credential.error_count = "0"
            credential.last_error = None

            self.db.flush()

            # Audit log
            self.audit.log(
                event_type=AuditEventType.CREDENTIAL_REFRESHED,
                credential_id=credential.id,
                provider=provider.value,
                account_name=credential.account_name,
                connector_name=credential.connector_name,
                metadata={
                    "new_expires_at": new_expires_at.isoformat() if new_expires_at else None,
                }
            )

            logger.info(
                "Credential refreshed successfully",
                extra={
                    "credential_id": credential.id,
                    "tenant_id": self.tenant_id,
                    "provider": provider.value,
                    "new_expires_at": new_expires_at.isoformat() if new_expires_at else None,
                }
            )

            return RefreshResult(
                status=RefreshResultStatus.SUCCESS,
                credential_id=credential.id,
                provider=provider.value,
                new_expires_at=new_expires_at,
            )

        except Exception as e:
            # Record error
            error_count = int(credential.error_count or "0") + 1
            credential.error_count = str(error_count)
            credential.last_error = str(e)[:500]  # Truncate long errors

            # Mark as expired if too many failures
            if error_count >= 3:
                credential.status = CredentialStatus.EXPIRED
                logger.error(
                    "Credential marked as expired after multiple refresh failures",
                    extra={
                        "credential_id": credential.id,
                        "tenant_id": self.tenant_id,
                        "error_count": error_count,
                    }
                )

            self.db.flush()

            logger.error(
                "Token refresh failed",
                extra={
                    "credential_id": credential.id,
                    "tenant_id": self.tenant_id,
                    "provider": provider.value,
                    "error_count": error_count,
                    # Note: error message is logged but NOT tokens
                    "error": str(e),
                }
            )

            return RefreshResult(
                status=RefreshResultStatus.FAILED,
                credential_id=credential.id,
                provider=provider.value,
                error_message=str(e),
            )


# ============================================================================
# Provider-Specific Refresh Implementations
# ============================================================================

async def refresh_shopify_token(
    provider: CredentialProvider,
    refresh_token: str,
) -> tuple[str, Optional[str], Optional[int]]:
    """
    Refresh Shopify OAuth token.

    Note: Shopify access tokens are typically long-lived and don't expire.
    This is a placeholder for offline token rotation if needed.

    Args:
        provider: Should be CredentialProvider.SHOPIFY
        refresh_token: The refresh token (if using rotating tokens)

    Returns:
        Tuple of (new_access_token, new_refresh_token, expires_in_seconds)

    Raises:
        RefreshFailedError: If refresh fails
    """
    # Shopify offline tokens don't typically expire
    # This would need to implement Shopify's token rotation if enabled
    raise RefreshNotPossibleError(
        "Shopify access tokens do not expire. Re-authenticate if token is invalid."
    )


async def refresh_google_ads_token(
    provider: CredentialProvider,
    refresh_token: str,
) -> tuple[str, Optional[str], Optional[int]]:
    """
    Refresh Google Ads OAuth token.

    Args:
        provider: Should be CredentialProvider.GOOGLE_ADS
        refresh_token: The refresh token

    Returns:
        Tuple of (new_access_token, new_refresh_token, expires_in_seconds)

    Raises:
        RefreshFailedError: If refresh fails
    """
    import os
    import httpx

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RefreshFailedError("Google OAuth credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code != 200:
            raise RefreshFailedError(
                f"Google token refresh failed: {response.status_code}"
            )

        data = response.json()
        return (
            data["access_token"],
            data.get("refresh_token"),  # May not be returned
            data.get("expires_in", 3600),
        )


async def refresh_facebook_ads_token(
    provider: CredentialProvider,
    refresh_token: str,
) -> tuple[str, Optional[str], Optional[int]]:
    """
    Refresh Facebook Ads OAuth token.

    Note: Facebook uses long-lived tokens that need periodic exchange.

    Args:
        provider: Should be CredentialProvider.FACEBOOK_ADS
        refresh_token: The current long-lived token

    Returns:
        Tuple of (new_access_token, new_refresh_token, expires_in_seconds)

    Raises:
        RefreshFailedError: If refresh fails
    """
    import os
    import httpx

    app_id = os.getenv("FACEBOOK_APP_ID")
    app_secret = os.getenv("FACEBOOK_APP_SECRET")

    if not app_id or not app_secret:
        raise RefreshFailedError("Facebook OAuth credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.facebook.com/v18.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": refresh_token,
            },
        )

        if response.status_code != 200:
            raise RefreshFailedError(
                f"Facebook token refresh failed: {response.status_code}"
            )

        data = response.json()
        # Facebook returns a new long-lived token
        return (
            data["access_token"],
            data["access_token"],  # Use as refresh token too
            data.get("expires_in", 5184000),  # ~60 days
        )
