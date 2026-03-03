{{
    config(
        materialized='view',
        schema='staging'
    )
}}

-- This model exposes the tenant_airbyte_connections table for use in staging models
-- It filters to only active connections for tenant isolation
--
-- SECURITY: This model is used to map Airbyte connections to tenants.
-- Shopify staging models join on shop_domain to ensure correct tenant isolation.
-- Ad platform staging models join on account_id to ensure correct tenant isolation.
-- Email/SMS staging models join on source_type (one connection per source_type per tenant).

select
    airbyte_connection_id,
    tenant_id,
    source_type,
    connection_name,
    status,
    is_enabled,
    -- Extract shop_domain from configuration JSONB for Shopify tenant mapping
    -- Normalize: lowercase, strip protocol and trailing slash
    lower(
        trim(
            trailing '/' from
            regexp_replace(
                coalesce(configuration->>'shop_domain', ''),
                '^https?://',
                '',
                'i'
            )
        )
    ) as shop_domain,
    -- Extract account identifiers from configuration JSONB for ad platform tenant mapping
    -- Each platform stores its primary account ID under a different key:
    --   Meta Ads / Snapchat: account_id
    --   Google Ads: customer_id
    --   TikTok Ads: advertiser_id
    coalesce(configuration->>'account_id', '') as config_account_id,
    coalesce(configuration->>'customer_id', '') as config_customer_id,
    coalesce(configuration->>'advertiser_id', '') as config_advertiser_id
from {{ source('platform', 'tenant_airbyte_connections') }}
where status = 'active'
    and is_enabled = true
