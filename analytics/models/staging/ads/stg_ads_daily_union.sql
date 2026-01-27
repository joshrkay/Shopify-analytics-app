{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Unified staging model for all advertising platforms.

    This model unions all platform-specific staging models into a single
    consistent schema for downstream fact tables and reporting.

    All models must conform to this contract:
    - tenant_id: Tenant identifier for multi-tenancy
    - report_date: Date grain for the metrics
    - source: Platform identifier (meta_ads, google_ads, etc.)
    - platform_channel: Platform-specific channel value
    - canonical_channel: Normalized channel from taxonomy
    - internal_account_id: Deterministic account ID
    - internal_campaign_id: Deterministic campaign ID
    - Core metrics: spend, impressions, clicks, conversions, conversion_value
    - Derived metrics: cpm, cpc, ctr, cpa, roas_platform
#}

with meta_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_meta_ads_daily') }}
),

google_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_google_ads_daily') }}
),

tiktok_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_tiktok_ads_daily') }}
),

pinterest_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_pinterest_ads_daily') }}
),

snap_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_snap_ads_daily') }}
),

amazon_ads as (
    select
        row_surrogate_key,
        tenant_id,
        report_date,
        source,
        platform_channel,
        canonical_channel,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        platform_adgroup_id,
        internal_adgroup_id,
        platform_ad_id,
        internal_ad_id,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        spend,
        impressions,
        clicks,
        reach,
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
    from {{ ref('stg_amazon_ads_daily') }}
),

unioned as (
    select * from meta_ads
    union all
    select * from google_ads
    union all
    select * from tiktok_ads
    union all
    select * from pinterest_ads
    union all
    select * from snap_ads
    union all
    select * from amazon_ads
)

select * from unioned
