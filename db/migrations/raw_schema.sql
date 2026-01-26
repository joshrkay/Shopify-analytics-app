-- Raw Warehouse Layer Schema Migration
-- Version: 1.0.0
-- Date: 2026-01-26
--
-- This migration creates the raw warehouse layer for multi-tenant analytics.
-- All raw tables enforce tenant isolation via RLS (configured separately in raw_rls.sql).
--
-- DECISIONS (LOCKED):
--   - Warehouse: Postgres
--   - Isolation: shared tables with tenant_id + RLS
--   - Raw table naming: source-prefixed domain tables
--   - Raw data retention: 13 months
--   - PII policy: minimal (IDs + metrics only)
--   - Partitioning/indexing: tenant_id + extracted_at
--
-- Usage: psql $DATABASE_URL -f raw_schema.sql
--
-- IMPORTANT: Run raw_rls.sql AFTER this migration to enable RLS policies.

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Raw Schema Setup
-- =============================================================================

-- Create raw schema namespace for data warehouse tables
CREATE SCHEMA IF NOT EXISTS raw;

COMMENT ON SCHEMA raw IS 'Raw warehouse layer - source-system data with minimal transformation';

-- =============================================================================
-- raw_shopify_orders
-- Raw order data from Shopify API (PII-free: IDs + metrics only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_shopify_orders (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Required tenant/source columns
    tenant_id VARCHAR(255) NOT NULL,
    source_account_id VARCHAR(255) NOT NULL,  -- Shopify shop_id or shop_domain

    -- Pipeline metadata
    extracted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    loaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(255) NOT NULL,

    -- Shopify order identifiers (IDs only, no PII)
    shopify_order_id VARCHAR(255) NOT NULL,
    order_number VARCHAR(50),

    -- Order status
    order_status VARCHAR(50),
    financial_status VARCHAR(50),
    fulfillment_status VARCHAR(50),
    cancelled_at TIMESTAMP WITH TIME ZONE,

    -- Financial metrics (stored in cents to avoid floating point issues)
    total_price_cents BIGINT,
    subtotal_price_cents BIGINT,
    total_tax_cents BIGINT,
    total_discounts_cents BIGINT,
    total_shipping_cents BIGINT,
    currency VARCHAR(10),

    -- Order metrics
    line_item_count INTEGER,
    total_weight_grams INTEGER,

    -- Customer reference (ID only, no PII)
    shopify_customer_id VARCHAR(255),

    -- Timestamps from source
    order_created_at TIMESTAMP WITH TIME ZONE,
    order_updated_at TIMESTAMP WITH TIME ZONE,
    order_processed_at TIMESTAMP WITH TIME ZONE,

    -- Source system metadata
    source_name VARCHAR(50) DEFAULT 'shopify',
    app_id VARCHAR(255),

    -- Raw API response (PII fields should be filtered at extraction)
    raw_data JSONB,

    -- Deduplication constraint
    CONSTRAINT uk_raw_shopify_orders_tenant_order
        UNIQUE (tenant_id, source_account_id, shopify_order_id)
);

-- Performance indexes (tenant_id + extracted_at as specified)
CREATE INDEX IF NOT EXISTS idx_raw_shopify_orders_tenant_extracted
    ON raw.raw_shopify_orders(tenant_id, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_orders_tenant_source
    ON raw.raw_shopify_orders(tenant_id, source_account_id);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_orders_run
    ON raw.raw_shopify_orders(run_id);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_orders_loaded
    ON raw.raw_shopify_orders(loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_orders_order_created
    ON raw.raw_shopify_orders(tenant_id, order_created_at DESC);

COMMENT ON TABLE raw.raw_shopify_orders IS 'Raw Shopify order data - IDs and metrics only, no PII. Retention: 13 months.';
COMMENT ON COLUMN raw.raw_shopify_orders.tenant_id IS 'Tenant identifier from JWT org_id - enforced by RLS';
COMMENT ON COLUMN raw.raw_shopify_orders.source_account_id IS 'Shopify shop_id or shop_domain';
COMMENT ON COLUMN raw.raw_shopify_orders.extracted_at IS 'Timestamp when data was extracted from Shopify API';
COMMENT ON COLUMN raw.raw_shopify_orders.loaded_at IS 'Timestamp when data was loaded into warehouse';
COMMENT ON COLUMN raw.raw_shopify_orders.run_id IS 'Pipeline run identifier for traceability';
COMMENT ON COLUMN raw.raw_shopify_orders.raw_data IS 'Full API response with PII fields filtered out';

-- =============================================================================
-- raw_meta_ads_insights
-- Raw ad performance data from Meta (Facebook/Instagram) Ads API
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_meta_ads_insights (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Required tenant/source columns
    tenant_id VARCHAR(255) NOT NULL,
    source_account_id VARCHAR(255) NOT NULL,  -- Meta ad_account_id

    -- Pipeline metadata
    extracted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    loaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(255) NOT NULL,

    -- Ad hierarchy identifiers
    campaign_id VARCHAR(255),
    campaign_name VARCHAR(500),
    adset_id VARCHAR(255),
    adset_name VARCHAR(500),
    ad_id VARCHAR(255),
    ad_name VARCHAR(500),

    -- Date range for insight
    date_start DATE NOT NULL,
    date_stop DATE NOT NULL,

    -- Impression metrics
    impressions BIGINT DEFAULT 0,
    reach BIGINT DEFAULT 0,
    frequency NUMERIC(10, 4),

    -- Engagement metrics
    clicks BIGINT DEFAULT 0,
    unique_clicks BIGINT DEFAULT 0,
    ctr NUMERIC(10, 6),
    unique_ctr NUMERIC(10, 6),

    -- Cost metrics (stored in cents)
    spend_cents BIGINT DEFAULT 0,
    cpm_cents BIGINT,
    cpc_cents BIGINT,
    cpp_cents BIGINT,

    -- Conversion metrics
    conversions BIGINT DEFAULT 0,
    conversion_value_cents BIGINT DEFAULT 0,
    cost_per_conversion_cents BIGINT,
    roas NUMERIC(10, 4),

    -- Video metrics
    video_views BIGINT DEFAULT 0,
    video_p25_watched BIGINT DEFAULT 0,
    video_p50_watched BIGINT DEFAULT 0,
    video_p75_watched BIGINT DEFAULT 0,
    video_p100_watched BIGINT DEFAULT 0,

    -- Source system metadata
    source_name VARCHAR(50) DEFAULT 'meta_ads',
    account_currency VARCHAR(10),

    -- Raw API response
    raw_data JSONB,

    -- Deduplication constraint (one insight per ad/date/account)
    CONSTRAINT uk_raw_meta_ads_insights_tenant_ad_date
        UNIQUE (tenant_id, source_account_id, ad_id, date_start, date_stop)
);

-- Performance indexes (tenant_id + extracted_at as specified)
CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_tenant_extracted
    ON raw.raw_meta_ads_insights(tenant_id, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_tenant_source
    ON raw.raw_meta_ads_insights(tenant_id, source_account_id);

CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_run
    ON raw.raw_meta_ads_insights(run_id);

CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_loaded
    ON raw.raw_meta_ads_insights(loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_date
    ON raw.raw_meta_ads_insights(tenant_id, date_start DESC);

CREATE INDEX IF NOT EXISTS idx_raw_meta_ads_insights_campaign
    ON raw.raw_meta_ads_insights(tenant_id, campaign_id);

COMMENT ON TABLE raw.raw_meta_ads_insights IS 'Raw Meta (Facebook/Instagram) Ads insights data. Retention: 13 months.';
COMMENT ON COLUMN raw.raw_meta_ads_insights.tenant_id IS 'Tenant identifier from JWT org_id - enforced by RLS';
COMMENT ON COLUMN raw.raw_meta_ads_insights.source_account_id IS 'Meta ad_account_id';
COMMENT ON COLUMN raw.raw_meta_ads_insights.spend_cents IS 'Ad spend in cents (multiply by 100 from API)';
COMMENT ON COLUMN raw.raw_meta_ads_insights.roas IS 'Return on ad spend (conversion_value / spend)';

-- =============================================================================
-- raw_google_ads_campaigns
-- Raw campaign performance data from Google Ads API
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_google_ads_campaigns (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Required tenant/source columns
    tenant_id VARCHAR(255) NOT NULL,
    source_account_id VARCHAR(255) NOT NULL,  -- Google Ads customer_id

    -- Pipeline metadata
    extracted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    loaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(255) NOT NULL,

    -- Campaign identifiers
    campaign_id VARCHAR(255) NOT NULL,
    campaign_name VARCHAR(500),
    campaign_status VARCHAR(50),
    campaign_type VARCHAR(100),
    advertising_channel_type VARCHAR(100),

    -- Date for metrics
    metrics_date DATE NOT NULL,

    -- Impression metrics
    impressions BIGINT DEFAULT 0,

    -- Engagement metrics
    clicks BIGINT DEFAULT 0,
    interactions BIGINT DEFAULT 0,
    ctr NUMERIC(10, 6),
    interaction_rate NUMERIC(10, 6),

    -- Cost metrics (stored in micros as per Google Ads API, divided by 1M for dollars)
    cost_micros BIGINT DEFAULT 0,
    average_cpc_micros BIGINT,
    average_cpm_micros BIGINT,

    -- Conversion metrics
    conversions NUMERIC(18, 6) DEFAULT 0,
    conversions_value_micros BIGINT DEFAULT 0,
    cost_per_conversion_micros BIGINT,
    conversion_rate NUMERIC(10, 6),

    -- Quality metrics
    search_impression_share NUMERIC(10, 6),
    search_rank_lost_impression_share NUMERIC(10, 6),

    -- Source system metadata
    source_name VARCHAR(50) DEFAULT 'google_ads',
    account_currency VARCHAR(10),

    -- Raw API response
    raw_data JSONB,

    -- Deduplication constraint (one record per campaign/date/account)
    CONSTRAINT uk_raw_google_ads_campaigns_tenant_campaign_date
        UNIQUE (tenant_id, source_account_id, campaign_id, metrics_date)
);

-- Performance indexes (tenant_id + extracted_at as specified)
CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_tenant_extracted
    ON raw.raw_google_ads_campaigns(tenant_id, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_tenant_source
    ON raw.raw_google_ads_campaigns(tenant_id, source_account_id);

CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_run
    ON raw.raw_google_ads_campaigns(run_id);

CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_loaded
    ON raw.raw_google_ads_campaigns(loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_date
    ON raw.raw_google_ads_campaigns(tenant_id, metrics_date DESC);

CREATE INDEX IF NOT EXISTS idx_raw_google_ads_campaigns_campaign
    ON raw.raw_google_ads_campaigns(tenant_id, campaign_id);

COMMENT ON TABLE raw.raw_google_ads_campaigns IS 'Raw Google Ads campaign performance data. Retention: 13 months.';
COMMENT ON COLUMN raw.raw_google_ads_campaigns.tenant_id IS 'Tenant identifier from JWT org_id - enforced by RLS';
COMMENT ON COLUMN raw.raw_google_ads_campaigns.source_account_id IS 'Google Ads customer_id';
COMMENT ON COLUMN raw.raw_google_ads_campaigns.cost_micros IS 'Cost in micros (divide by 1,000,000 for currency value)';
COMMENT ON COLUMN raw.raw_google_ads_campaigns.conversions IS 'Conversion count (can be fractional for data-driven attribution)';

-- =============================================================================
-- raw_shopify_customers (IDs only, no PII)
-- Customer reference data for analytics joins
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_shopify_customers (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Required tenant/source columns
    tenant_id VARCHAR(255) NOT NULL,
    source_account_id VARCHAR(255) NOT NULL,  -- Shopify shop_id

    -- Pipeline metadata
    extracted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    loaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(255) NOT NULL,

    -- Customer identifier (NO PII - ID only)
    shopify_customer_id VARCHAR(255) NOT NULL,

    -- Behavioral metrics (no PII)
    orders_count INTEGER DEFAULT 0,
    total_spent_cents BIGINT DEFAULT 0,
    currency VARCHAR(10),

    -- Customer state
    customer_state VARCHAR(50),  -- enabled, disabled, invited, declined
    accepts_marketing BOOLEAN,
    tax_exempt BOOLEAN,
    verified_email BOOLEAN,

    -- Timestamps from source
    customer_created_at TIMESTAMP WITH TIME ZONE,
    customer_updated_at TIMESTAMP WITH TIME ZONE,

    -- Source system metadata
    source_name VARCHAR(50) DEFAULT 'shopify',

    -- Raw API response (PII fields must be filtered at extraction)
    raw_data JSONB,

    -- Deduplication constraint
    CONSTRAINT uk_raw_shopify_customers_tenant_customer
        UNIQUE (tenant_id, source_account_id, shopify_customer_id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_raw_shopify_customers_tenant_extracted
    ON raw.raw_shopify_customers(tenant_id, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_customers_tenant_source
    ON raw.raw_shopify_customers(tenant_id, source_account_id);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_customers_run
    ON raw.raw_shopify_customers(run_id);

COMMENT ON TABLE raw.raw_shopify_customers IS 'Raw Shopify customer reference data - IDs and metrics only, NO PII. Retention: 13 months.';
COMMENT ON COLUMN raw.raw_shopify_customers.shopify_customer_id IS 'Shopify customer ID - NO name, email, address, or other PII stored';

-- =============================================================================
-- raw_shopify_products
-- Product catalog data for analytics joins
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_shopify_products (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Required tenant/source columns
    tenant_id VARCHAR(255) NOT NULL,
    source_account_id VARCHAR(255) NOT NULL,  -- Shopify shop_id

    -- Pipeline metadata
    extracted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    loaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    run_id VARCHAR(255) NOT NULL,

    -- Product identifiers
    shopify_product_id VARCHAR(255) NOT NULL,
    product_title VARCHAR(500),
    product_handle VARCHAR(500),
    product_type VARCHAR(255),
    vendor VARCHAR(255),

    -- Product status
    product_status VARCHAR(50),  -- active, archived, draft
    published_at TIMESTAMP WITH TIME ZONE,

    -- Product attributes
    tags TEXT,
    template_suffix VARCHAR(255),

    -- Variants summary
    variants_count INTEGER DEFAULT 0,

    -- Timestamps from source
    product_created_at TIMESTAMP WITH TIME ZONE,
    product_updated_at TIMESTAMP WITH TIME ZONE,

    -- Source system metadata
    source_name VARCHAR(50) DEFAULT 'shopify',

    -- Raw API response
    raw_data JSONB,

    -- Deduplication constraint
    CONSTRAINT uk_raw_shopify_products_tenant_product
        UNIQUE (tenant_id, source_account_id, shopify_product_id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_raw_shopify_products_tenant_extracted
    ON raw.raw_shopify_products(tenant_id, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_products_tenant_source
    ON raw.raw_shopify_products(tenant_id, source_account_id);

CREATE INDEX IF NOT EXISTS idx_raw_shopify_products_run
    ON raw.raw_shopify_products(run_id);

COMMENT ON TABLE raw.raw_shopify_products IS 'Raw Shopify product catalog data. Retention: 13 months.';

-- =============================================================================
-- raw_pipeline_runs
-- Pipeline execution tracking for data lineage
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_pipeline_runs (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    run_id VARCHAR(255) NOT NULL UNIQUE,

    -- Pipeline identification
    pipeline_name VARCHAR(255) NOT NULL,
    pipeline_type VARCHAR(100) NOT NULL,  -- 'extraction', 'transformation', 'load'
    source_type VARCHAR(100) NOT NULL,    -- 'shopify', 'meta_ads', 'google_ads'

    -- Scope (optional tenant scoping for multi-tenant pipelines)
    tenant_id VARCHAR(255),
    source_account_id VARCHAR(255),

    -- Execution details
    status VARCHAR(50) NOT NULL DEFAULT 'running',  -- running, success, failed, cancelled
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Data range processed
    data_start_date DATE,
    data_end_date DATE,

    -- Metrics
    records_extracted BIGINT DEFAULT 0,
    records_loaded BIGINT DEFAULT 0,
    records_failed BIGINT DEFAULT 0,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Metadata
    run_metadata JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for pipeline tracking
CREATE INDEX IF NOT EXISTS idx_raw_pipeline_runs_tenant
    ON raw.raw_pipeline_runs(tenant_id) WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raw_pipeline_runs_status
    ON raw.raw_pipeline_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_pipeline_runs_source
    ON raw.raw_pipeline_runs(source_type, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_pipeline_runs_started
    ON raw.raw_pipeline_runs(started_at DESC);

COMMENT ON TABLE raw.raw_pipeline_runs IS 'Pipeline execution tracking for data lineage and debugging';
COMMENT ON COLUMN raw.raw_pipeline_runs.run_id IS 'Unique identifier referenced by all raw data records';

-- =============================================================================
-- Migration Complete
-- =============================================================================

SELECT 'Raw warehouse schema migration completed successfully' AS status;
SELECT 'IMPORTANT: Run raw_rls.sql to enable Row-Level Security policies' AS next_step;
