# OAuth Credential Storage

Secure OAuth credential storage with encryption at rest, automatic token refresh, and retention policy enforcement.

## Overview

This module provides:
- **Encrypted storage** for OAuth tokens (access_token, refresh_token)
- **Automatic token refresh** (scheduled + on-demand)
- **Retention policy enforcement** (soft delete with purge windows)
- **Audit logging** with automatic token redaction

## Security Requirements

### Encryption
- All tokens are encrypted at rest using **Fernet symmetric encryption**
- Encryption key is provided via `ENCRYPTION_KEY` environment variable
- No plaintext tokens exist outside of process memory
- Tokens are NEVER logged, exposed in API responses, or committed to audit trails

### PII Policy
| Data | Allowed in Logs/Audit |
|------|----------------------|
| `account_name` | ✅ Yes |
| `connector_name` | ✅ Yes |
| `access_token` | ❌ NEVER |
| `refresh_token` | ❌ NEVER |

### Access Control
- All operations are tenant-scoped (tenant_id from JWT only)
- Credential metadata visible only to **Merchant Admin** role
- Token values are NEVER exposed in any API response

## Quick Start

### 1. Set Encryption Key

```bash
# Set in environment (required before storing any credentials)
export ENCRYPTION_KEY="your-32-char-encryption-key-here"
```

### 2. Store Credentials

```python
from sqlalchemy.orm import Session
from src.credentials import CredentialStore
from src.models.oauth_credential import CredentialProvider

# Initialize store (tenant_id from JWT)
store = CredentialStore(db_session, tenant_id)

# Store OAuth tokens
credential = await store.store_credential(
    provider=CredentialProvider.SHOPIFY,
    access_token="<your-access-token>",  # Encrypted automatically
    refresh_token="<your-refresh-token>", # Encrypted automatically
    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    scopes=["read_products", "write_products"],
    account_name="My Store",              # Safe for logs
    connector_name="Shopify",             # Safe for logs
)
```

### 3. Use Credentials

```python
# Get decrypted access token (for API calls)
access_token = await store.get_access_token(credential.id)

# Use token for API call (token only in memory)
async with ShopifyClient(access_token) as client:
    products = await client.get_products()
```

### 4. Token Refresh

```python
from src.credentials import CredentialRefreshService

# Initialize refresh service
refresh_service = CredentialRefreshService(db_session, tenant_id)

# Register provider-specific refresh callback
refresh_service.register_refresh_callback(
    CredentialProvider.GOOGLE_ADS,
    refresh_google_ads_token,
)

# On-demand refresh (during sync)
result = await refresh_service.refresh_if_needed(credential_id)

# Scheduled refresh (background job)
results = await refresh_service.refresh_expiring_credentials(within_minutes=30)
```

## Retention Policy

### On Disconnect
When a user disconnects a connector:
1. Credential is marked **inactive immediately**
2. Token access is blocked
3. Encrypted tokens are **purged after 5 days**

```python
await store.disconnect_credential(credential_id)
# credential.is_active = False
# credential.scheduled_purge_at = now + 5 days
```

### On Uninstall
When the app is uninstalled:
1. Credential is marked **pending_deletion**
2. Token access is blocked
3. Encrypted tokens are **purged after 20 days**

```python
await store.mark_uninstall_pending(credential_id)
# credential.status = PENDING_DELETION
# credential.scheduled_purge_at = now + 20 days
```

### Purge Job
Run this job periodically to purge expired credentials:

```python
# Find credentials due for purge
credentials_to_purge = store.get_credentials_due_for_purge()

for credential in credentials_to_purge:
    await store.purge_credential(credential.id)
    # credential.access_token_encrypted = None
    # credential.refresh_token_encrypted = None
    # credential.purged_at = now
```

## Audit Events

All credential operations are logged:

| Event | Description |
|-------|-------------|
| `credential.stored` | New credential created or updated |
| `credential.refreshed` | Tokens refreshed successfully |
| `credential.revoked` | Credential disconnected or uninstall pending |
| `credential.purged` | Encrypted tokens removed |

```python
from src.credentials import CredentialAuditLogger, AuditEventType

audit = CredentialAuditLogger(tenant_id)
audit.log(
    event_type=AuditEventType.CREDENTIAL_STORED,
    credential_id=credential.id,
    provider="shopify",
    account_name="My Store",  # Safe for logs
)
```

## Database Schema

### oauth_credentials table

```sql
CREATE TABLE oauth_credentials (
    id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    
    -- Provider
    provider credential_provider NOT NULL,
    external_account_id VARCHAR(255),
    
    -- Encrypted tokens (NEVER log plaintext)
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    
    -- Token metadata
    expires_at TIMESTAMP WITH TIME ZONE,
    scopes TEXT,  -- JSON array
    
    -- Display metadata (allowed in logs)
    account_name VARCHAR(255),
    connector_name VARCHAR(255),
    
    -- Status
    status credential_status DEFAULT 'active',
    is_active BOOLEAN DEFAULT true,
    
    -- Retention
    disconnected_at TIMESTAMP WITH TIME ZONE,
    scheduled_purge_at TIMESTAMP WITH TIME ZONE,
    purged_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Running Migration

```bash
# Run the SQL migration
psql $DATABASE_URL -f backend/db/migrations/credentials.sql
```

## Token Refresh Strategies

### 1. Scheduled Refresh (Background Job)
Proactively refresh tokens before they expire:

```python
# Run every 15 minutes via cron/scheduler
async def scheduled_refresh_job():
    for tenant_id in get_all_tenant_ids():
        service = CredentialRefreshService(db_session, tenant_id)
        results = await service.refresh_expiring_credentials(within_minutes=30)
        
        for result in results:
            if result.status == RefreshResultStatus.FAILED:
                alert_ops_team(result)
```

### 2. On-Demand Refresh (During Sync)
Refresh tokens when they expire during a sync operation:

```python
async def sync_data(credential_id: str):
    refresh_service = CredentialRefreshService(db_session, tenant_id)
    
    # Refresh if needed before sync
    result = await refresh_service.refresh_if_needed(credential_id)
    
    if result.status == RefreshResultStatus.FAILED:
        raise SyncError(f"Token refresh failed: {result.error_message}")
    
    # Get fresh token
    access_token = await store.get_access_token(credential_id)
    
    # Proceed with sync
    await do_sync(access_token)
```

## Supported Providers

| Provider | Token Refresh | Notes |
|----------|--------------|-------|
| Shopify | N/A | Offline tokens don't expire |
| Google Ads | ✅ | OAuth2 refresh_token flow |
| Facebook Ads | ✅ | Long-lived token exchange |
| TikTok Ads | ✅ | OAuth2 refresh_token flow |

## Error Handling

```python
from src.credentials import (
    CredentialStoreError,
    CredentialNotFoundError,
    CredentialExpiredError,
    CredentialInactiveError,
)

try:
    token = await store.get_access_token(credential_id)
except CredentialNotFoundError:
    # Credential doesn't exist or wrong tenant
    return redirect("/connect")
except CredentialInactiveError:
    # Credential was disconnected
    return redirect("/reconnect")
except CredentialExpiredError:
    # Token expired and cannot refresh
    return redirect("/reauthorize")
```

## Testing

### Run Tests

```bash
# Run all credential tests
pytest backend/src/tests/test_credential_encryption.py -v
pytest backend/src/tests/test_retention_windows.py -v
```

### Test Checklist

The tests verify:
- ✅ Tokens never appear in logs
- ✅ Encryption round-trip works
- ✅ Retention windows enforced correctly (5 days disconnect, 20 days uninstall)
- ✅ Only merchant admin can view metadata
- ✅ Tenant isolation is enforced
- ✅ Token refresh works (scheduled + on-demand)

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ENCRYPTION_KEY` | **Yes** | 32+ character key for Fernet encryption |
| `GOOGLE_CLIENT_ID` | For Google Ads | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | For Google Ads | Google OAuth client secret |
| `FACEBOOK_APP_ID` | For Facebook Ads | Facebook app ID |
| `FACEBOOK_APP_SECRET` | For Facebook Ads | Facebook app secret |

### Application Startup

```python
from src.credentials.encryption import validate_encryption_ready
from src.credentials.redaction import setup_credential_logging

# Fail fast if encryption not configured
validate_encryption_ready()

# Configure logging redaction
setup_credential_logging()
```

## Security Best Practices

1. **Never log tokens** - Use `redact_credential_data()` before logging
2. **Short token lifetime** - Prefer short-lived tokens with refresh
3. **Minimal scopes** - Request only required OAuth scopes
4. **Rotate encryption keys** - Implement key rotation procedure
5. **Audit everything** - Use `CredentialAuditLogger` for compliance
6. **Tenant isolation** - Always pass `tenant_id` from JWT, never from input

## Troubleshooting

### "Encryption not configured" error
```bash
# Ensure ENCRYPTION_KEY is set
export ENCRYPTION_KEY="your-key-here"
```

### Token refresh failing
```python
# Check error_count on credential
credential = store.get_credential(credential_id)
print(f"Error count: {credential.error_count}")
print(f"Last error: {credential.last_error}")
```

### Credential marked as expired
```python
# Re-authenticate the user to get new tokens
# Credentials with 3+ refresh failures are marked EXPIRED
await store.store_credential(
    provider=provider,
    access_token=new_access_token,
    refresh_token=new_refresh_token,
    external_account_id=account_id,  # Same account to reactivate
)
```
