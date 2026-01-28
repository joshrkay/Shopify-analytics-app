"""
Credentials module for secure OAuth credential management.

This module provides:
- Encrypted storage for OAuth tokens
- Automatic token refresh (scheduled + on-demand)
- Retention policy enforcement (disconnect: 5 days, uninstall: 20 days)
- Audit logging with automatic redaction

SECURITY:
- Tokens are encrypted at rest using ENCRYPTION_KEY
- No plaintext tokens outside process memory
- Tokens NEVER appear in logs or API responses
- Allowed in logs: account_name, connector_name

Usage:
    from src.credentials import CredentialStore, CredentialRefreshService
    
    # Store credentials
    store = CredentialStore(db_session, tenant_id)
    cred = await store.store_credential(
        provider=CredentialProvider.SHOPIFY,
        access_token="shpat_xxx",
        refresh_token="refresh_xxx",
        account_name="My Store"
    )
    
    # Refresh tokens
    refresh_service = CredentialRefreshService(db_session, tenant_id)
    await refresh_service.refresh_if_needed(credential_id)
"""

from src.credentials.store import CredentialStore, CredentialStoreError
from src.credentials.encryption import (
    encrypt_token,
    decrypt_token,
    CredentialEncryptionError,
)
from src.credentials.refresh import (
    CredentialRefreshService,
    RefreshResult,
    RefreshError,
)
from src.credentials.redaction import (
    redact_credential_data,
    CredentialAuditLogger,
    AuditEventType,
)

__all__ = [
    # Store
    "CredentialStore",
    "CredentialStoreError",
    # Encryption
    "encrypt_token",
    "decrypt_token",
    "CredentialEncryptionError",
    # Refresh
    "CredentialRefreshService",
    "RefreshResult",
    "RefreshError",
    # Redaction & Audit
    "redact_credential_data",
    "CredentialAuditLogger",
    "AuditEventType",
]
