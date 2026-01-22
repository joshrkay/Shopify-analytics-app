-- Migration: OAuth States Table
-- Description: Creates table for OAuth state management during Shopify app installation
-- Security: States are single-use, expire after 10 minutes, and provide CSRF protection

-- ============================================================
-- OAUTH STATES (No tenant_id - temporary state only)
-- ============================================================
-- Stores temporary OAuth state/nonce pairs for CSRF protection
-- States expire after 10 minutes and are marked as used after consumption

CREATE TABLE IF NOT EXISTS oauth_states (
    id VARCHAR(255) PRIMARY KEY,
    shop_domain VARCHAR(255) NOT NULL,
    state VARCHAR(255) NOT NULL UNIQUE,
    nonce VARCHAR(255) NOT NULL,
    scopes TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS ix_oauth_states_state ON oauth_states(state);
CREATE INDEX IF NOT EXISTS ix_oauth_states_shop_domain ON oauth_states(shop_domain);
CREATE INDEX IF NOT EXISTS ix_oauth_states_expires_at ON oauth_states(expires_at);

-- Composite index for common query pattern (state + shop_domain)
CREATE INDEX IF NOT EXISTS ix_oauth_states_state_shop ON oauth_states(state, shop_domain);

-- Comment on table
COMMENT ON TABLE oauth_states IS 'Temporary OAuth states for CSRF protection during Shopify app installation';
COMMENT ON COLUMN oauth_states.state IS 'Cryptographically secure state parameter (32 bytes)';
COMMENT ON COLUMN oauth_states.expires_at IS 'When this state expires (10 minutes from creation)';
COMMENT ON COLUMN oauth_states.used_at IS 'When this state was consumed (single-use)';
