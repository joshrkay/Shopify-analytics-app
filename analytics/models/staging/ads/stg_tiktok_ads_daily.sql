{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'ad_account_id', 'campaign_id', 'adgroup_id', 'ad_id', 'date'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for TikTok Ads with normalized fields and tenant isolation.

    This model:
    - Extracts and normalizes raw TikTok Ads data from Airbyte
    - Adds internal IDs for cross-platform joins (Option B ID normalization)
    - Maps to canonical channel taxonomy
    - Supports incremental processing with configurable lookback window
    - Excludes PII fields

    TikTok Ads API field mappings:
    - advertiser_id -> ad_account_id
    - campaign_id -> campaign_id
    - adgroup_id -> adgroup_id (similar to adset)
    - ad_id -> ad_id
    - stat_time_day -> date
    - spend -> spend
    - impressions -> impressions
    - clicks -> clicks
    - conversion -> conversions
    - total_complete_payment_rate -> conversion_value (estimated)
#}

with raw_tiktok_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_tiktok_ads') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ get_lookback_days("tiktok_ads") }} days'
    {% endif %}
),

tiktok_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'advertiser_id' as advertiser_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'adgroup_id' as adgroup_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        coalesce(raw.ad_data->>'stat_time_day', raw.ad_data->>'date') as date_raw,
        raw.ad_data->>'spend' as spend_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        coalesce(raw.ad_data->>'conversion', raw.ad_data->>'conversions') as conversions_raw,
        raw.ad_data->>'total_complete_payment_rate' as conversion_value_raw,
        coalesce(raw.ad_data->>'currency', 'USD') as currency_code,
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'adgroup_name' as adgroup_name,
        raw.ad_data->>'ad_name' as ad_name,
        raw.ad_data->>'objective_type' as objective,
        raw.ad_data->>'cpm' as cpm_raw,
        raw.ad_data->>'cpc' as cpc_raw,
        raw.ad_data->>'ctr' as ctr_raw,
        raw.ad_data->>'cost_per_conversion' as cost_per_conversion_raw,
        -- Platform channel: TikTok is always paid social
        'in_feed' as platform_channel_raw
    from raw_tiktok_ads raw
),

tiktok_ads_normalized as (
    select
        -- Primary identifiers
        case
            when advertiser_id_raw is null or trim(advertiser_id_raw) = '' then null
            else trim(advertiser_id_raw)
        end as ad_account_id,

        case
            when campaign_id_raw is null or trim(campaign_id_raw) = '' then null
            else trim(campaign_id_raw)
        end as campaign_id,

        case
            when adgroup_id_raw is null or trim(adgroup_id_raw) = '' then null
            else trim(adgroup_id_raw)
        end as adgroup_id,

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
        end as date,

        -- Spend
        case
            when spend_raw is null or trim(spend_raw) = '' then 0.0
            when trim(spend_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(spend_raw)::numeric, 0), 999999999.99)
            else 0.0
        end as spend,

        -- Impressions
        case
            when impressions_raw is null or trim(impressions_raw) = '' then 0
            when trim(impressions_raw) ~ '^-?[0-9]+$'
                then least(greatest(trim(impressions_raw)::integer, 0), 2147483647)
            else 0
        end as impressions,

        -- Clicks
        case
            when clicks_raw is null or trim(clicks_raw) = '' then 0
            when trim(clicks_raw) ~ '^-?[0-9]+$'
                then least(greatest(trim(clicks_raw)::integer, 0), 2147483647)
            else 0
        end as clicks,

        -- Conversions
        case
            when conversions_raw is null or trim(conversions_raw) = '' then 0.0
            when trim(conversions_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(conversions_raw)::numeric, 0.0), 999999999.99)
            else 0.0
        end as conversions,

        -- Conversion value
        case
            when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
            when trim(conversion_value_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(conversion_value_raw)::numeric, 0.0), 999999999.99)
            else 0.0
        end as conversion_value,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Additional fields
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        coalesce(platform_channel_raw, 'in_feed') as platform_channel,

        -- Platform metrics (from API)
        case
            when cpm_raw is null or trim(cpm_raw) = '' then null
            when trim(cpm_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then trim(cpm_raw)::numeric
            else null
        end as cpm_platform,

        case
            when cpc_raw is null or trim(cpc_raw) = '' then null
            when trim(cpc_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then trim(cpc_raw)::numeric
            else null
        end as cpc_platform,

        case
            when ctr_raw is null or trim(ctr_raw) = '' then null
            when trim(ctr_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then trim(ctr_raw)::numeric
            else null
        end as ctr_platform,

        case
            when cost_per_conversion_raw is null or trim(cost_per_conversion_raw) = '' then null
            when trim(cost_per_conversion_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then trim(cost_per_conversion_raw)::numeric
            else null
        end as cpa_platform,

        -- Source identifier
        'tiktok_ads' as source,
        'tiktok_ads' as platform,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from tiktok_ads_extracted
),

-- Join to tenant mapping
tiktok_ads_with_tenant as (
    select
        ads.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-tiktok-marketing'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from tiktok_ads_normalized ads
),

-- Add internal IDs and canonical channel
tiktok_ads_final as (
    select
        tenant_id,
        date,
        date as report_date,
        source,
        ad_account_id,
        campaign_id,
        adgroup_id,
        ad_id,
        {{ generate_internal_id('tenant_id', 'source', 'ad_account_id') }} as internal_account_id,
        {{ generate_internal_id('tenant_id', 'source', 'campaign_id') }} as internal_campaign_id,
        platform_channel,
        {{ map_canonical_channel('source', 'platform_channel') }} as canonical_channel,
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
        currency,
        -- Derived metrics
        case when impressions > 0 then round((spend / impressions) * 1000, 4) else cpm_platform end as cpm,
        case when clicks > 0 then round(spend / clicks, 4) else cpc_platform end as cpc,
        case when impressions > 0 then round((clicks::numeric / impressions) * 100, 4) else ctr_platform end as ctr,
        case when conversions > 0 then round(spend / conversions, 4) else cpa_platform end as cpa,
        case when spend > 0 then round(conversion_value / spend, 4) else null end as roas_platform,
        campaign_name,
        adgroup_name,
        ad_name,
        objective,
        platform,
        airbyte_record_id,
        airbyte_emitted_at
    from tiktok_ads_with_tenant
)

select * from tiktok_ads_final
where tenant_id is not null
    and ad_account_id is not null
    and campaign_id is not null
    and date is not null
    {% if is_incremental() %}
    and date >= current_date - {{ get_lookback_days('tiktok_ads') }}
    {% endif %}
