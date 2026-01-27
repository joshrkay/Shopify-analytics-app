{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date', 'ad_account_id', 'campaign_id', 'ad_group_id', 'ad_id'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Google Ads daily metrics.

    Required contract fields for stg_ads_daily:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - internal_account_id, internal_campaign_id
    - spend, impressions, clicks, conversions, conversion_value
    - derived metrics: cpm, cpc, ctr, cpa, roas_platform

    PII Policy: No PII fields exposed. IDs and metrics only.
#}

with raw_google_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_google_ads') }}
),

google_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'customer_id' as customer_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'ad_group_id' as ad_group_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        raw.ad_data->>'date' as date_raw,
        raw.ad_data->>'cost_micros' as cost_micros_raw,
        raw.ad_data->>'cost' as cost_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        raw.ad_data->>'conversions' as conversions_raw,
        raw.ad_data->>'conversions_value' as conversion_value_raw,
        raw.ad_data->>'currency_code' as currency_code,
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'ad_group_name' as ad_group_name,
        raw.ad_data->>'campaign_type' as campaign_type,
        raw.ad_data->>'advertising_channel_type' as advertising_channel_type,
        raw.ad_data->>'network' as network
    from raw_google_ads raw
),

google_ads_normalized as (
    select
        -- IDs (Google uses customer_id as account identifier)
        case
            when customer_id_raw is null or trim(customer_id_raw) = '' then null
            else trim(customer_id_raw)
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
            else null
        end as report_date,

        -- Spend: Google Ads provides cost_micros (divide by 1,000,000) or cost
        case
            when cost_micros_raw is not null and trim(cost_micros_raw) != ''
                and trim(cost_micros_raw) ~ '^-?[0-9]+$' then
                greatest((trim(cost_micros_raw)::bigint / 1000000.0)::numeric, 0)
            when cost_raw is not null and trim(cost_raw) != ''
                and trim(cost_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$' then
                greatest(trim(cost_raw)::numeric, 0)
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

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Campaign info
        campaign_name,
        ad_group_name,
        coalesce(campaign_type, 'unknown') as campaign_type,
        coalesce(advertising_channel_type, network, 'search') as advertising_channel,

        -- Source identification
        'google_ads' as source,

        -- Platform channel (network/campaign type based)
        coalesce(advertising_channel_type, network, 'search') as platform_channel,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from google_ads_extracted
),

-- Join to tenant mapping
google_ads_with_tenant as (
    select
        ads.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-google-ads'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from google_ads_normalized ads
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

    -- For backwards compatibility
    platform_account_id as ad_account_id,
    platform_campaign_id as campaign_id,

    -- Internal IDs (deterministic hashes)
    {{ generate_internal_account_id('tenant_id', "'google_ads'", 'platform_account_id') }} as internal_account_id,
    {{ generate_internal_campaign_id('tenant_id', "'google_ads'", 'platform_campaign_id') }} as internal_campaign_id,

    -- Channel taxonomy
    platform_channel,
    {{ map_canonical_channel("'google_ads'", 'platform_channel') }} as canonical_channel,

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

    -- Campaign info
    campaign_name,
    ad_group_name,
    campaign_type,
    advertising_channel,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from google_ads_with_tenant
where tenant_id is not null
    and platform_account_id is not null
    and platform_campaign_id is not null
    and report_date is not null

{{ incremental_filter('report_date', 'google_ads') }}
