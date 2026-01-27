{{
    config(
        materialized='incremental',
        unique_key='id',
        schema='analytics',
        on_schema_change='append_new_columns'
    )
}}

-- Canonical fact table for ad spend across all platforms
--
-- This table unifies ad spend data from all advertising platforms.
-- It provides a single source of truth for all advertising spend.
--
-- SECURITY: Tenant isolation is enforced - all rows must have tenant_id

with unified_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date as spend_date,
        source as platform,
        platform_account_id as ad_account_id,
        internal_account_id,
        platform_campaign_id as campaign_id,
        internal_campaign_id,
        platform_adgroup_id as adset_id,
        internal_adgroup_id,
        platform_ad_id as ad_id,
        internal_ad_id,
        canonical_channel,
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
        currency,
        cpm,
        cpc,
        ctr,
        cpa,
        roas_platform,
        airbyte_emitted_at,
        dbt_loaded_at
    from {{ ref('stg_ads_daily_union') }}
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null
        and spend is not null

    {% if is_incremental() %}
        and airbyte_emitted_at > (
            select coalesce(max(ingested_at), '1970-01-01'::timestamp with time zone)
            from {{ this }}
        )
    {% endif %}
)

select
    -- Primary key: use the staging model's surrogate key
    row_surrogate_key as id,

    -- Ad identifiers (platform)
    ad_account_id,
    campaign_id,
    adset_id,
    ad_id,

    -- Internal identifiers (normalized)
    internal_account_id,
    internal_campaign_id,
    internal_adgroup_id,
    internal_ad_id,

    -- Spend information
    spend_date,
    spend,
    currency,

    -- Channel
    canonical_channel,

    -- Performance metrics
    impressions,
    clicks,
    conversions,
    conversion_value,
    cpm,
    cpc,
    ctr,
    cpa,
    roas_platform,

    -- Platform identifier
    platform,

    -- Tenant isolation (CRITICAL)
    tenant_id,

    -- Metadata
    airbyte_emitted_at as ingested_at,

    -- Audit fields
    current_timestamp as dbt_updated_at

from unified_ads
