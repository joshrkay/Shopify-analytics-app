-- ============================================================================
-- OAuth Credentials Table Migration
-- ============================================================================
-- 
-- SECURITY REQUIREMENTS:
-- - Tokens are encrypted at rest using Fernet encryption
-- - No plaintext tokens stored in database
-- - Tenant isolation enforced via tenant_id column
-- - Retention windows: disconnect=5 days, uninstall=20 days
--
-- IMPORTANT: Run this migration AFTER setting ENCRYPTION_KEY environment variable
-- ============================================================================

-- Create enum types if they don't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'credential_status') THEN
        CREATE TYPE credential_status AS ENUM (
            'active',
            'inactive',
            'expired',
            'revoked',
            'pending_deletion'
        );
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'credential_provider') THEN
        CREATE TYPE credential_provider AS ENUM (
            'shopify',
            'google_ads',
            'facebook_ads',
            'tiktok_ads'
        );
    END IF;
END $$;

-- ============================================================================
-- OAuth Credentials Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS oauth_credentials (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY,
    
    -- Tenant isolation (from JWT org_id)
    tenant_id VARCHAR(255) NOT NULL,
    
    -- Provider identification
    provider credential_provider NOT NULL,
    external_account_id VARCHAR(255),
    
    -- Encrypted tokens (NEVER store plaintext)
    -- These columns contain Fernet-encrypted base64 strings
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    
    -- Token metadata
    token_type VARCHAR(50) DEFAULT 'Bearer',
    expires_at TIMESTAMP WITH TIME ZONE,
    refresh_token_expires_at TIMESTAMP WITH TIME ZONE,
    last_refreshed_at TIMESTAMP WITH TIME ZONE,
    
    -- Scopes (JSON array, NOT hardcoded)
    scopes TEXT,
    
    -- Display metadata (ALLOWED in logs per PII policy)
    account_name VARCHAR(255),
    connector_name VARCHAR(255),
    
    -- Status and lifecycle
    status credential_status NOT NULL DEFAULT 'active',
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Retention tracking
    disconnected_at TIMESTAMP WITH TIME ZONE,
    scheduled_purge_at TIMESTAMP WITH TIME ZONE,
    purged_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit trail
    last_used_at TIMESTAMP WITH TIME ZONE,
    error_count VARCHAR(10) DEFAULT '0',
    last_error TEXT,
    
    -- Foreign key to Shopify stores (optional)
    store_id VARCHAR(255) REFERENCES shopify_stores(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Unique constraint: one credential per tenant/provider/account
    CONSTRAINT uq_oauth_credentials_tenant_provider_account 
        UNIQUE (tenant_id, provider, external_account_id)
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Tenant + provider lookup (most common query pattern)
CREATE INDEX IF NOT EXISTS ix_oauth_credentials_tenant_provider 
    ON oauth_credentials (tenant_id, provider);

-- Tenant + status lookup (list active credentials)
CREATE INDEX IF NOT EXISTS ix_oauth_credentials_tenant_status 
    ON oauth_credentials (tenant_id, status);

-- Scheduled purge lookup (retention job)
CREATE INDEX IF NOT EXISTS ix_oauth_credentials_scheduled_purge 
    ON oauth_credentials (scheduled_purge_at) 
    WHERE scheduled_purge_at IS NOT NULL;

-- Token expiry lookup (refresh job)
CREATE INDEX IF NOT EXISTS ix_oauth_credentials_expires_at 
    ON oauth_credentials (expires_at) 
    WHERE is_active = true AND expires_at IS NOT NULL;

-- Store ID lookup (Shopify credential by store)
CREATE INDEX IF NOT EXISTS ix_oauth_credentials_store_id 
    ON oauth_credentials (store_id) 
    WHERE store_id IS NOT NULL;

-- ============================================================================
-- Trigger for updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_oauth_credentials_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_oauth_credentials_updated_at ON oauth_credentials;
CREATE TRIGGER trigger_oauth_credentials_updated_at
    BEFORE UPDATE ON oauth_credentials
    FOR EACH ROW
    EXECUTE FUNCTION update_oauth_credentials_updated_at();

-- ============================================================================
-- Audit Log Table for Credential Events
-- ============================================================================
CREATE TABLE IF NOT EXISTS credential_audit_log (
    id VARCHAR(255) PRIMARY KEY,
    
    -- Event details
    event_type VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    credential_id VARCHAR(255),
    provider VARCHAR(50),
    
    -- Safe metadata (allowed in logs per PII policy)
    account_name VARCHAR(255),
    connector_name VARCHAR(255),
    
    -- Event context (JSON, auto-redacted)
    metadata JSONB,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for audit queries by tenant
CREATE INDEX IF NOT EXISTS ix_credential_audit_log_tenant 
    ON credential_audit_log (tenant_id, created_at DESC);

-- Index for audit queries by credential
CREATE INDEX IF NOT EXISTS ix_credential_audit_log_credential 
    ON credential_audit_log (credential_id, created_at DESC);

-- Index for event type queries
CREATE INDEX IF NOT EXISTS ix_credential_audit_log_event_type 
    ON credential_audit_log (event_type, created_at DESC);

-- ============================================================================
-- Comments for Documentation
-- ============================================================================
COMMENT ON TABLE oauth_credentials IS 
    'Secure OAuth credential storage with encrypted tokens. Tokens are Fernet-encrypted.';

COMMENT ON COLUMN oauth_credentials.access_token_encrypted IS 
    'Fernet-encrypted access token. NEVER log plaintext.';

COMMENT ON COLUMN oauth_credentials.refresh_token_encrypted IS 
    'Fernet-encrypted refresh token. NEVER log plaintext.';

COMMENT ON COLUMN oauth_credentials.tenant_id IS 
    'Tenant ID from JWT org_id. NEVER accept from client input.';

COMMENT ON COLUMN oauth_credentials.scheduled_purge_at IS 
    'When encrypted blob will be purged. 5 days for disconnect, 20 days for uninstall.';

COMMENT ON COLUMN oauth_credentials.account_name IS 
    'Display name for the account. Allowed in logs per PII policy.';

COMMENT ON COLUMN oauth_credentials.connector_name IS 
    'User-friendly connector name. Allowed in logs per PII policy.';

COMMENT ON TABLE credential_audit_log IS 
    'Append-only audit log for credential operations. Tokens are never logged.';

-- ============================================================================
-- Row-Level Security (Optional but Recommended)
-- ============================================================================
-- Uncomment if using RLS for additional tenant isolation:
--
-- ALTER TABLE oauth_credentials ENABLE ROW LEVEL SECURITY;
-- 
-- CREATE POLICY oauth_credentials_tenant_isolation ON oauth_credentials
--     FOR ALL
--     USING (tenant_id = current_setting('app.current_tenant_id')::text);

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- Post-migration checklist:
-- 1. Verify ENCRYPTION_KEY environment variable is set
-- 2. Run: SELECT validate_encryption_configured() from application
-- 3. Test credential storage and retrieval
-- 4. Verify audit logs are being written
