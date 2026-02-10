-- Per-tenant entitlement overrides. Expiry required; governance via Super Admin/Support only.
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS entitlement_override (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    feature_key VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    actor_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    CONSTRAINT uq_tenant_feature UNIQUE (tenant_id, feature_key)
);

CREATE INDEX IF NOT EXISTS idx_entitlement_override_tenant_id
    ON entitlement_override (tenant_id);
CREATE INDEX IF NOT EXISTS idx_entitlement_override_expires_at
    ON entitlement_override (expires_at);
CREATE INDEX IF NOT EXISTS idx_entitlement_override_tenant_feature_expiry
    ON entitlement_override (tenant_id, feature_key, expires_at);

COMMENT ON TABLE entitlement_override IS 'Per-tenant entitlement overrides; expiry mandatory; audit via entitlement.override.* events';
