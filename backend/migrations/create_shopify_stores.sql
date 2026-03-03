-- =============================================================================
-- Migration: Create shopify_stores Table
-- =============================================================================
-- Version: 1.0.0
-- Date: 2026-03-03
-- Purpose: Create the shopify_stores table for linking Shopify shops to tenants
--
-- Dependencies: 001_create_identity_tables.sql (tenants table must exist)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create store_status enum (idempotent)
DO $$ BEGIN
    CREATE TYPE store_status AS ENUM (
        'installing',
        'active',
        'inactive',
        'suspended',
        'uninstalled'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- Shopify Stores Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS shopify_stores (
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    tenant_id VARCHAR(255) NOT NULL,
    shop_domain VARCHAR(255) NOT NULL,
    shop_id VARCHAR(50),
    access_token_encrypted TEXT,
    scopes TEXT,
    shop_name VARCHAR(255),
    shop_email VARCHAR(255),
    shop_owner VARCHAR(255),
    currency VARCHAR(10) DEFAULT 'USD',
    timezone VARCHAR(100),
    country_code VARCHAR(10),
    status store_status NOT NULL DEFAULT 'installing',
    installed_at TIMESTAMP WITH TIME ZONE,
    uninstalled_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS uq_shopify_stores_shop_domain
    ON shopify_stores (shop_domain);
CREATE INDEX IF NOT EXISTS ix_shopify_stores_tenant_status
    ON shopify_stores (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_shopify_stores_tenant_domain
    ON shopify_stores (tenant_id, shop_domain);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_shopify_stores_updated_at ON shopify_stores;
CREATE TRIGGER update_shopify_stores_updated_at
    BEFORE UPDATE ON shopify_stores
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE shopify_stores IS 'Links Shopify shops to tenants. tenant_id from JWT only.';
COMMENT ON COLUMN shopify_stores.access_token_encrypted IS 'Encrypted Shopify access token. NEVER log.';

SELECT 'shopify_stores migration completed successfully' AS status;
