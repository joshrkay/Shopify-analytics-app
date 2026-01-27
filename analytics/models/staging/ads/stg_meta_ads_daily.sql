{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date', 'ad_account_id', 'campaign_id'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Meta (Facebook/Instagram) Ads daily metrics.

    Required contract fields for stg_ads_daily:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - internal_account_id, internal_campaign_id
    - spend, impressions, clicks, conversions, conversion_value
    - derived metrics: cpm, cpc, ctr, cpa, roas_platform

    PII Policy: No PII fields exposed. IDs and metrics only.
#}

with raw_meta_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_meta_ads') }}
),

meta_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'account_id' as account_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'adset_id' as adset_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        raw.ad_data->>'date_start' as date_start_raw,
        raw.ad_data->>'spend' as spend_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        raw.ad_data->>'conversions' as conversions_raw,
        raw.ad_data->>'conversion_value' as conversion_value_raw,
        raw.ad_data->>'purchase_roas' as purchase_roas_raw,
        raw.ad_data->>'currency' as currency_code,
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'adset_name' as adset_name,
        raw.ad_data->>'objective' as objective
    from raw_meta_ads raw
),

meta_ads_normalized as (
    select
        -- IDs
        case
            when account_id_raw is null or trim(account_id_raw) = '' then null
            else trim(account_id_raw)
        end as platform_account_id,

        case
            when campaign_id_raw is null or trim(campaign_id_raw) = '' then null
            else trim(campaign_id_raw)
        end as platform_campaign_id,

        case
            when adset_id_raw is null or trim(adset_id_raw) = '' then null
            else trim(adset_id_raw)
        end as adset_id,

        case
            when ad_id_raw is null or trim(ad_id_raw) = '' then null
            else trim(ad_id_raw)
        end as ad_id,

        -- Date field
        case
            when date_start_raw is null or trim(date_start_raw) = '' then null
            when date_start_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_start_raw::date
            else null
        end as report_date,

        -- Spend
        case
            when spend_raw is null or trim(spend_raw) = '' then 0.0
            when trim(spend_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(spend_raw)::numeric, 0)
            else 0.0
        end as spend,

        -- Impressions
        case
            when impressions_raw is null or trim(impressions_raw) = '' then 0
            when trim(impressions_raw) ~ '^-?[0-9]+$'
                then greatest(trim(impressions_raw)::bigint, 0)
            else 0
        end as impressions,

        -- Clicks
        case
            when clicks_raw is null or trim(clicks_raw) = '' then 0
            when trim(clicks_raw) ~ '^-?[0-9]+$'
                then greatest(trim(clicks_raw)::bigint, 0)
            else 0
        end as clicks,

        -- Conversions
        case
            when conversions_raw is null or trim(conversions_raw) = '' then 0.0
            when trim(conversions_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(conversions_raw)::numeric, 0)
            else 0.0
        end as conversions,

        -- Conversion value
        case
            when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
            when trim(conversion_value_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(conversion_value_raw)::numeric, 0)
            else 0.0
        end as conversion_value,

        -- Platform ROAS (reported by Meta)
        case
            when purchase_roas_raw is null or trim(purchase_roas_raw) = '' then null
            when trim(purchase_roas_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(purchase_roas_raw)::numeric, 0)
            else null
        end as platform_roas_reported,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Campaign info
        campaign_name,
        adset_name,
        coalesce(objective, 'unknown') as objective,

        -- Source identification
        'meta_ads' as source,

        -- Platform channel (objective-based)
        coalesce(objective, 'unknown') as platform_channel,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from meta_ads_extracted
),

-- Join to tenant mapping
meta_ads_with_tenant as (
    select
        ads.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-facebook-marketing'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from meta_ads_normalized ads
)

select
    -- Primary identifiers
    tenant_id,
    report_date,
    source,

    -- Platform IDs
    platform_account_id,
    platform_campaign_id,
    adset_id,
    ad_id,

    -- For backwards compatibility with existing models
    platform_account_id as ad_account_id,
    platform_campaign_id as campaign_id,

    -- Internal IDs (deterministic hashes)
    {{ generate_internal_account_id('tenant_id', "'meta_ads'", 'platform_account_id') }} as internal_account_id,
    {{ generate_internal_campaign_id('tenant_id', "'meta_ads'", 'platform_campaign_id') }} as internal_campaign_id,

    -- Channel taxonomy
    platform_channel,
    {{ map_canonical_channel("'meta_ads'", 'platform_channel') }} as canonical_channel,

    -- Core metrics
    spend,
    impressions,
    clicks,
    conversions,
    conversion_value,
    currency,

    -- Derived metrics (safe division)
    case when impressions > 0 then (spend / impressions) * 1000 else null end as cpm,
    case when clicks > 0 then spend / clicks else null end as cpc,
    case when impressions > 0 then (clicks::numeric / impressions) * 100 else null end as ctr,
    case when conversions > 0 then spend / conversions else null end as cpa,
    case when spend > 0 then conversion_value / spend else null end as roas_platform,

    -- Platform-reported ROAS (for comparison)
    platform_roas_reported,

    -- Campaign info
    campaign_name,
    adset_name,
    objective,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from meta_ads_with_tenant
where tenant_id is not null
    and platform_account_id is not null
    and platform_campaign_id is not null
    and report_date is not null

{{ incremental_filter('report_date', 'meta_ads') }}
