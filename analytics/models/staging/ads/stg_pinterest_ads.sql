{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'ad_account_id', 'campaign_id', 'ad_group_id', 'ad_id', 'date'],
        incremental_strategy='delete+insert',
        enabled=var('enable_pinterest_ads', true)
    )
}}

{#
    Staging model for Pinterest Ads with normalized fields and tenant isolation.

    This model:
    - Extracts and normalizes raw Pinterest Ads data from Airbyte
    - Adds internal IDs for cross-platform joins (Option B ID normalization)
    - Maps to canonical channel taxonomy
    - Supports incremental processing with configurable lookback window
    - Excludes PII fields
    - Returns empty result if source table doesn't exist yet

    Required output columns (staging contract):
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - platform_account_id, internal_account_id, platform_campaign_id, internal_campaign_id
    - spend, impressions, clicks, conversions, conversion_value
    - cpm, cpc, ctr, cpa, roas_platform (derived where possible)
#}

-- Check if source table exists; if not, return empty result set
{% if not source_exists('raw_pinterest_ads', 'ad_reports') %}

select
    cast(null as text) as tenant_id,
    cast(null as date) as report_date,
    cast(null as date) as date,
    cast(null as text) as source,
    cast(null as text) as ad_account_id,
    cast(null as text) as campaign_id,
    cast(null as text) as ad_group_id,
    cast(null as text) as ad_id,
    cast(null as text) as internal_account_id,
    cast(null as text) as internal_campaign_id,
    cast(null as text) as platform_channel,
    cast(null as text) as canonical_channel,
    cast(null as numeric) as spend,
    cast(null as integer) as impressions,
    cast(null as integer) as clicks,
    cast(null as numeric) as conversions,
    cast(null as numeric) as conversion_value,
    cast(null as text) as currency,
    cast(null as numeric) as cpm,
    cast(null as numeric) as cpc,
    cast(null as numeric) as ctr,
    cast(null as numeric) as cpa,
    cast(null as numeric) as roas_platform,
    cast(null as text) as campaign_name,
    cast(null as text) as ad_group_name,
    cast(null as text) as ad_name,
    cast(null as text) as objective,
    cast(null as text) as platform,
    cast(null as text) as airbyte_record_id,
    cast(null as timestamp) as airbyte_emitted_at
where 1=0

{% else %}

with raw_pinterest_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('raw_pinterest_ads', 'ad_reports') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ var("lookback_days_pinterest_ads", 3) }} days'
    {% endif %}
),

pinterest_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'ad_account_id' as ad_account_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'ad_group_id' as ad_group_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        raw.ad_data->>'date' as date_raw,
        raw.ad_data->>'spend_in_micro_dollar' as spend_raw,
        raw.ad_data->>'impression' as impressions_raw,
        raw.ad_data->>'clickthrough' as clicks_raw,
        raw.ad_data->>'total_conversions' as conversions_raw,
        raw.ad_data->>'total_conversions_value_in_micro_dollar' as conversion_value_raw,
        raw.ad_data->>'currency' as currency_code,
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'ad_group_name' as ad_group_name,
        raw.ad_data->>'ad_name' as ad_name,
        raw.ad_data->>'campaign_objective_type' as objective,
        coalesce(raw.ad_data->>'placement', raw.ad_data->>'campaign_objective_type', 'pinterest_ads') as platform_channel_raw
    from raw_pinterest_ads raw
),

pinterest_ads_normalized as (
    select
        -- Primary identifiers
        case
            when ad_account_id_raw is null or trim(ad_account_id_raw) = '' then null
            else trim(ad_account_id_raw)
        end as ad_account_id,

        case
            when campaign_id_raw is null or trim(campaign_id_raw) = '' then null
            else trim(campaign_id_raw)
        end as campaign_id,

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
        end as date,

        -- Spend: Pinterest provides spend in micro-dollars (divide by 1,000,000)
        case
            when spend_raw is null or trim(spend_raw) = '' then 0.0
            when trim(spend_raw) ~ '^-?[0-9]+$' then
                least(greatest((trim(spend_raw)::bigint / 1000000.0)::numeric, -999999999.99), 999999999.99)
            when trim(spend_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$' then
                least(greatest(trim(spend_raw)::numeric, -999999999.99), 999999999.99)
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

        -- Conversion value (micro-dollars)
        case
            when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
            when trim(conversion_value_raw) ~ '^-?[0-9]+$' then
                least(greatest((trim(conversion_value_raw)::bigint / 1000000.0)::numeric, 0.0), 999999999.99)
            when trim(conversion_value_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$' then
                least(greatest(trim(conversion_value_raw)::numeric, 0.0), 999999999.99)
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
        ad_group_name,
        ad_name,
        objective,

        -- Platform channel
        coalesce(platform_channel_raw, 'pinterest_ads') as platform_channel,

        -- Platform identifier
        'pinterest_ads' as platform,
        'pinterest_ads' as source,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from pinterest_ads_extracted
),

-- Tenant mapping: join on ad_account_id for multi-tenant isolation
pinterest_tenant_mapping as (
    select
        tenant_id,
        config_account_id as mapped_account_id
    from {{ ref('_tenant_airbyte_connections') }}
    where source_type = 'source-pinterest-ads'
        and config_account_id is not null
        and config_account_id != ''
),

pinterest_ads_with_tenant as (
    select
        ads.*,
        tm.tenant_id
    from pinterest_ads_normalized ads
    inner join pinterest_tenant_mapping tm
        on ads.ad_account_id = tm.mapped_account_id
),

-- Add internal IDs and canonical channel
pinterest_ads_final as (
    select
        tenant_id,
        date,
        date as report_date,
        source,
        ad_account_id,
        campaign_id,
        ad_group_id,
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
        case
            when impressions > 0 then round((spend / impressions) * 1000, 4)
            else null
        end as cpm,

        case
            when clicks > 0 then round(spend / clicks, 4)
            else null
        end as cpc,

        case
            when impressions > 0 then round((clicks::numeric / impressions) * 100, 4)
            else null
        end as ctr,

        case
            when conversions > 0 then round(spend / conversions, 4)
            else null
        end as cpa,

        case
            when spend > 0 then round(conversion_value / spend, 4)
            else null
        end as roas_platform,

        campaign_name,
        ad_group_name,
        ad_name,
        objective,
        platform,
        airbyte_record_id,
        airbyte_emitted_at

    from pinterest_ads_with_tenant
)

select
    tenant_id,
    report_date,
    date,
    source,
    ad_account_id,
    campaign_id,
    ad_group_id,
    ad_id,
    internal_account_id,
    internal_campaign_id,
    platform_channel,
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
    campaign_name,
    ad_group_name,
    ad_name,
    objective,
    platform,
    airbyte_record_id,
    airbyte_emitted_at
from pinterest_ads_final
where tenant_id is not null
    and ad_account_id is not null
    and trim(ad_account_id) != ''
    and campaign_id is not null
    and trim(campaign_id) != ''
    and date is not null
    {% if is_incremental() %}
    and date >= current_date - {{ var("lookback_days_pinterest_ads", 3) }}
    {% endif %}

{% endif %}
