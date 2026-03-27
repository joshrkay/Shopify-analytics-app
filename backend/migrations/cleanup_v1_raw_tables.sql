-- =============================================================================
-- Migration: Clean up orphaned Airbyte V1 raw tables
-- =============================================================================
-- After migrating dbt staging models to Airbyte Destinations V2 (PR #396),
-- the V1 raw tables are no longer referenced by any dbt model or backend query.
--
-- V1 tables used _airbyte_data JSONB blobs. V2 tables use typed columns directly.
-- The V2 tables (airbyte_raw.orders, airbyte_raw.customers, airbyte_google_ads.ads_insights)
-- are the authoritative source for all dbt staging models.
--
-- IDEMPOTENT: Uses IF EXISTS — safe to run multiple times.
-- =============================================================================

DROP TABLE IF EXISTS airbyte_raw._airbyte_raw_shopify_orders;
DROP TABLE IF EXISTS airbyte_raw._airbyte_raw_shopify_customers;
DROP TABLE IF EXISTS airbyte_raw._airbyte_raw_meta_ads;
DROP TABLE IF EXISTS airbyte_raw._airbyte_raw_google_ads;
