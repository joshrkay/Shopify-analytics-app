-- ============================================================================
-- Test Database Setup Script
-- ============================================================================
-- This script creates empty source tables for dbt testing.
-- Run this in your test database before running dbt run.
--
-- Usage: psql $DATABASE_URL -f scripts/setup_test_sources.sql
-- ============================================================================

-- Create raw schema if not exists
CREATE SCHEMA IF NOT EXISTS raw;

-- ============================================================================
-- Airbyte-style source tables (public schema)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public._airbyte_raw_shopify_orders (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS public._airbyte_raw_shopify_customers (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS public._airbyte_raw_meta_ads (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS public._airbyte_raw_google_ads (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

-- ============================================================================
-- Raw schema source tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_tiktok_ads_metrics (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_pinterest_ads_insights (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_snap_ads_metrics (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_amazon_ads_reports (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_klaviyo_events (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_ga4_events (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

CREATE TABLE IF NOT EXISTS raw.raw_recharge_subscriptions (
    _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
    _airbyte_emitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _airbyte_data JSONB
);

-- ============================================================================
-- Platform tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tenant_airbyte_connections (
    id VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    airbyte_connection_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert a test tenant for development
INSERT INTO public.tenant_airbyte_connections (
    airbyte_connection_id,
    tenant_id,
    source_type,
    status,
    is_enabled
) VALUES
    ('test-connection-shopify', 'test-tenant-001', 'shopify', 'active', true),
    ('test-connection-meta', 'test-tenant-001', 'source-facebook-marketing', 'active', true),
    ('test-connection-google', 'test-tenant-001', 'source-google-ads', 'active', true),
    ('test-connection-tiktok', 'test-tenant-001', 'source-tiktok-marketing', 'active', true),
    ('test-connection-pinterest', 'test-tenant-001', 'source-pinterest-ads', 'active', true),
    ('test-connection-snap', 'test-tenant-001', 'source-snapchat-marketing', 'active', true),
    ('test-connection-amazon', 'test-tenant-001', 'source-amazon-ads', 'active', true),
    ('test-connection-klaviyo', 'test-tenant-001', 'source-klaviyo', 'active', true),
    ('test-connection-ga4', 'test-tenant-001', 'source-google-analytics-data-api', 'active', true),
    ('test-connection-recharge', 'test-tenant-001', 'source-recharge', 'active', true)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- Done
-- ============================================================================
SELECT 'Test source tables created successfully' AS status;
