-- =============================================================================
-- Migration: Seed platform.tenant_airbyte_connections with Airbyte Cloud connections
-- =============================================================================
-- This seeds the three active Airbyte Cloud connections into the platform schema
-- table used by dbt staging models for multi-tenant data isolation.
--
-- WHY THIS IS NEEDED:
-- All dbt staging models (stg_shopify_orders, stg_facebook_ads_performance, etc.)
-- perform an INNER JOIN against platform.tenant_airbyte_connections to map
-- Airbyte raw data rows to their owning tenant. With an empty table, every
-- staging model returns 0 rows regardless of how much raw data exists in
-- airbyte_raw.* and airbyte_google_ads.*.
--
-- CONNECTIONS SEEDED:
--   1. Shopify → MarkInsight DB (f87a1906-...)
--      Configuration includes shop_domain for shop_url-based tenant mapping.
--   2. Facebook Marketing → MarkInsight DB (8bb25ebb-...)
--      Configuration includes account_id for ad-account-based tenant mapping.
--   3. Google Ads → MarkInsight DB (516b10d7-...)
--      Configuration includes customer_id for customer-id-based tenant mapping.
--
-- IDEMPOTENT: Uses ON CONFLICT DO NOTHING — safe to run multiple times.
-- =============================================================================

INSERT INTO platform.tenant_airbyte_connections (
    tenant_id,
    airbyte_connection_id,
    airbyte_source_id,
    airbyte_destination_id,
    connection_name,
    connection_type,
    source_type,
    status,
    configuration,
    sync_frequency_minutes,
    is_enabled,
    created_at,
    updated_at
)
VALUES
    -- Shopify connection
    (
        '7b9aad14-bb5c-4659-a23d-a5deecc8c52a',
        'f87a1906-6cf4-482d-8667-cbadc65f8401',
        '98a06836-e979-41f5-8f96-1a560fa058e7',
        '0fa4796b-9036-4f02-bbbe-851682ec7cff',
        'Shopify → MarkInsight DB',
        'source',
        'source-shopify',
        'active',
        -- shop_domain must match the shop_url value in airbyte_raw.customers/orders.
        -- Airbyte Shopify V2 stores the raw subdomain (without .myshopify.com suffix).
        '{"shop_domain": "test-1111111111111111111111111111111111711111111111129799"}'::jsonb,
        '1440',
        true,
        NOW(),
        NOW()
    ),
    -- Facebook Marketing connection
    (
        '7b9aad14-bb5c-4659-a23d-a5deecc8c52a',
        '8bb25ebb-7497-4a7b-80b5-437e35c561f3',
        '959d55ca-5f15-44a5-801b-4b00c95f52de',
        '0fa4796b-9036-4f02-bbbe-851682ec7cff',
        'Facebook Marketing → MarkInsight DB',
        'source',
        'source-facebook-marketing',
        'active',
        -- account_id used by stg_facebook_ads_performance for tenant mapping.
        -- Note: Airbyte V2 ads_insights.account_id may carry 'act_' prefix;
        -- the staging model strips it before this join.
        '{"account_id": "422959152328586"}'::jsonb,
        '1440',
        true,
        NOW(),
        NOW()
    ),
    -- Google Ads connection
    (
        '7b9aad14-bb5c-4659-a23d-a5deecc8c52a',
        '516b10d7-99ce-45fe-8cbe-0066e7670b23',
        'af6b2268-87cf-4576-9069-d5a28eddd88c',
        '0fa4796b-9036-4f02-bbbe-851682ec7cff',
        'Google Ads → MarkInsight DB',
        'source',
        'source-google-ads',
        'active',
        -- customer_id used by stg_google_ads_performance for tenant mapping.
        '{"customer_id": "2087565376"}'::jsonb,
        '1440',
        true,
        NOW(),
        NOW()
    )
ON CONFLICT (airbyte_connection_id) DO NOTHING;
