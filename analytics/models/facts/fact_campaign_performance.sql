{{
    config(
        materialized='incremental',
        unique_key='id',
        schema='analytics',
        on_schema_change='append_new_columns'
    )
}}

-- Canonical fact table for campaign performance across all platforms
--
-- This table unifies campaign-level performance metrics from all advertising platforms.
-- It provides a single source of truth for campaign analytics.
--
-- SECURITY: Tenant isolation is enforced - all rows must have tenant_id

with unified_campaigns as (
    select
        -- Use internal IDs for consistent cross-platform analysis
        internal_account_id,
        internal_campaign_id,
        platform_account_id as ad_account_id,
        platform_campaign_id as campaign_id,
        campaign_name,
        report_date as performance_date,
        source as platform,
        canonical_channel,
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
        currency,
        -- Pre-calculated metrics from staging
        cpm,
        cpc,
        ctr,
        cpa,
        roas_platform,
        airbyte_emitted_at,
        tenant_id
    from {{ ref('stg_ads_daily_union') }}
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null

    {% if is_incremental() %}
        and airbyte_emitted_at > (
            select coalesce(max(ingested_at), '1970-01-01'::timestamp with time zone)
            from {{ this }}
        )
    {% endif %}
),

-- Aggregate to campaign-date level (in case staging has ad-level granularity)
campaign_aggregated as (
    select
        tenant_id,
        internal_account_id,
        internal_campaign_id,
        ad_account_id,
        campaign_id,
        max(campaign_name) as campaign_name,
        performance_date,
        platform,
        max(canonical_channel) as canonical_channel,
        sum(spend) as spend,
        sum(impressions) as impressions,
        sum(clicks) as clicks,
        sum(conversions) as conversions,
        sum(conversion_value) as conversion_value,
        max(currency) as currency,
        max(airbyte_emitted_at) as airbyte_emitted_at
    from unified_campaigns
    group by
        tenant_id,
        internal_account_id,
        internal_campaign_id,
        ad_account_id,
        campaign_id,
        performance_date,
        platform
)

select
    -- Primary key: composite of tenant_id, platform, campaign_id, performance_date
    md5(concat(tenant_id, '|', platform, '|', campaign_id, '|', performance_date::text)) as id,

    -- Campaign identifiers
    ad_account_id,
    campaign_id,
    campaign_name,

    -- Internal identifiers (normalized)
    internal_account_id,
    internal_campaign_id,

    -- Performance date
    performance_date,

    -- Channel
    canonical_channel,

    -- Performance metrics (all numeric, normalized)
    spend,
    impressions,
    clicks,
    conversions,
    conversion_value,

    -- Calculated metrics
    case
        when impressions > 0 then round((spend / impressions::numeric) * 1000, 2)
        else null
    end as cpm,  -- Cost per mille

    case
        when impressions > 0 then round((clicks::numeric / impressions::numeric) * 100, 4)
        else null
    end as ctr,  -- Click-through rate (percentage)

    case
        when clicks > 0 then round(spend / clicks::numeric, 2)
        else null
    end as cpc,  -- Cost per click

    case
        when conversions > 0 then round(spend / conversions::numeric, 2)
        else null
    end as cpa,  -- Cost per acquisition/conversion

    case
        when spend > 0 then round(conversion_value / spend, 4)
        else null
    end as roas_platform,  -- Return on ad spend

    -- Currency
    currency,

    -- Platform identifier
    platform,

    -- Tenant isolation (CRITICAL)
    tenant_id,

    -- Metadata
    airbyte_emitted_at as ingested_at,

    -- Audit fields
    current_timestamp as dbt_updated_at

from campaign_aggregated
