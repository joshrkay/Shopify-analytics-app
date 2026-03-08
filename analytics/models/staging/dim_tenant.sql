{{
    config(
        materialized='view',
        schema='staging'
    )
}}

-- Tenant dimension with timezone support for date normalization
--
-- This model provides tenant-level attributes including timezone for
-- normalizing timestamps to tenant local dates (per user story 7.7.1).
--
-- Timezone is sourced from the shopify_stores table (populated from Shopify
-- shop settings during OAuth). Falls back to UTC when no store is linked
-- or timezone is not yet populated.
--
-- USAGE: Join to this model to get tenant timezone, then use the
-- convert_to_tenant_local_date macro for date conversion.

with tenant_base as (
    select distinct
        tenant_id
    from {{ ref('_tenant_airbyte_connections') }}
    where tenant_id is not null
),

-- Get timezone from the active Shopify store linked to each tenant
-- A tenant may have multiple stores; pick the active one (or most recently created)
store_timezones as (
    select
        tenant_id,
        timezone
    from {{ source('platform', 'shopify_stores') }}
    where status = 'active'
        and timezone is not null
        and trim(timezone) != ''
)

select
    tb.tenant_id,

    -- Timezone for date normalization
    -- Sourced from Shopify shop settings, falls back to UTC
    coalesce(st.timezone, 'UTC') as timezone,

    -- Metadata
    current_timestamp as dbt_updated_at

from tenant_base tb
left join store_timezones st on tb.tenant_id = st.tenant_id
