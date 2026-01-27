{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date', 'platform_account_id', 'platform_campaign_id', 'ad_group_id', 'ad_id'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Amazon Ads daily metrics.

    Supports:
    - Sponsored Products (SP)
    - Sponsored Brands (SB)
    - Sponsored Display (SD)

    Required contract fields for stg_ads_daily:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - internal_account_id, internal_campaign_id
    - spend, impressions, clicks, conversions, conversion_value
    - derived metrics: cpm, cpc, ctr, cpa, roas_platform

    PII Policy: No PII fields exposed. IDs and metrics only.
#}

with raw_amazon_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_amazon_ads_insights') }}
),

amazon_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'profileId' as profile_id_raw,
        raw.ad_data->>'campaignId' as campaign_id_raw,
        raw.ad_data->>'adGroupId' as ad_group_id_raw,
        raw.ad_data->>'adId' as ad_id_raw,
        raw.ad_data->>'date' as date_raw,
        raw.ad_data->>'cost' as cost_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        raw.ad_data->>'purchases' as conversions_raw,
        raw.ad_data->>'attributedConversions14d' as conversions_14d_raw,
        raw.ad_data->>'sales' as sales_raw,
        raw.ad_data->>'attributedSales14d' as sales_14d_raw,
        raw.ad_data->>'currency' as currency_code,
        raw.ad_data->>'campaignName' as campaign_name,
        raw.ad_data->>'campaignType' as campaign_type
    from raw_amazon_ads raw
),

amazon_ads_normalized as (
    select
        -- IDs (Amazon uses profileId as account identifier)
        case
            when profile_id_raw is null or trim(profile_id_raw) = '' then null
            else trim(profile_id_raw)
        end as platform_account_id,

        case
            when campaign_id_raw is null or trim(campaign_id_raw) = '' then null
            else trim(campaign_id_raw)
        end as platform_campaign_id,

        case
            when ad_group_id_raw is null or trim(ad_group_id_raw) = '' then null
            else trim(ad_group_id_raw)
        end as ad_group_id,

        case
            when ad_id_raw is null or trim(ad_id_raw) = '' then null
            else trim(ad_id_raw)
        end as ad_id,

        -- Date field
        case
            when date_raw is null or trim(date_raw) = '' then null
            when date_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_raw::date
            when date_raw ~ '^\d{8}$'
                then to_date(date_raw, 'YYYYMMDD')
            else null
        end as report_date,

        -- Spend (Amazon reports as 'cost')
        case
            when cost_raw is null or trim(cost_raw) = '' then 0.0
            when trim(cost_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(cost_raw)::numeric, 0)
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

        -- Conversions (prefer 14-day attribution window)
        case
            when conversions_14d_raw is not null and trim(conversions_14d_raw) != ''
                and trim(conversions_14d_raw) ~ '^-?[0-9]+\.?[0-9]*$' then
                greatest(trim(conversions_14d_raw)::numeric, 0)
            when conversions_raw is not null and trim(conversions_raw) != ''
                and trim(conversions_raw) ~ '^-?[0-9]+\.?[0-9]*$' then
                greatest(trim(conversions_raw)::numeric, 0)
            else 0.0
        end as conversions,

        -- Conversion value (prefer 14-day attribution)
        case
            when sales_14d_raw is not null and trim(sales_14d_raw) != ''
                and trim(sales_14d_raw) ~ '^-?[0-9]+\.?[0-9]*$' then
                greatest(trim(sales_14d_raw)::numeric, 0)
            when sales_raw is not null and trim(sales_raw) != ''
                and trim(sales_raw) ~ '^-?[0-9]+\.?[0-9]*$' then
                greatest(trim(sales_raw)::numeric, 0)
            else 0.0
        end as conversion_value,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Campaign info
        campaign_name,
        -- Normalize campaign type (SP, SB, SD)
        case
            when lower(coalesce(campaign_type, '')) like '%sponsored_product%'
                or lower(coalesce(campaign_type, '')) = 'sp' then 'sponsored_products'
            when lower(coalesce(campaign_type, '')) like '%sponsored_brand%'
                or lower(coalesce(campaign_type, '')) = 'sb' then 'sponsored_brands'
            when lower(coalesce(campaign_type, '')) like '%sponsored_display%'
                or lower(coalesce(campaign_type, '')) = 'sd' then 'sponsored_display'
            else 'sponsored_products'
        end as campaign_type,

        -- Source identification
        'amazon_ads' as source,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from amazon_ads_extracted
),

-- Join to tenant mapping
amazon_ads_with_tenant as (
    select
        ads.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-amazon-ads'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from amazon_ads_normalized ads
)

select
    -- Primary identifiers
    tenant_id,
    report_date,
    source,

    -- Platform IDs
    platform_account_id,
    platform_campaign_id,
    ad_group_id,
    ad_id,

    -- Internal IDs (deterministic hashes)
    {{ generate_internal_account_id('tenant_id', "'amazon_ads'", 'platform_account_id') }} as internal_account_id,
    {{ generate_internal_campaign_id('tenant_id', "'amazon_ads'", 'platform_campaign_id') }} as internal_campaign_id,

    -- Channel taxonomy
    campaign_type as platform_channel,
    {{ map_canonical_channel("'amazon_ads'", 'campaign_type') }} as canonical_channel,

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

    -- Amazon-specific: ACOS (Advertising Cost of Sales)
    case when conversion_value > 0 then (spend / conversion_value) * 100 else null end as acos,

    -- Campaign info
    campaign_name,
    campaign_type,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from amazon_ads_with_tenant
where tenant_id is not null
    and platform_account_id is not null
    and platform_campaign_id is not null
    and report_date is not null

{{ incremental_filter('report_date', 'amazon_ads') }}
