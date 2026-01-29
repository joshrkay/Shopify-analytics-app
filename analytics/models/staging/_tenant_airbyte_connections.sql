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
    ) as shop_domain
from {{ source('platform', 'tenant_airbyte_connections') }}
where source_type in ('shopify', 'source-shopify', 'source-facebook-marketing', 'source-google-ads')
    and status = 'active'
    and is_enabled = true
