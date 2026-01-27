{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for Meta (Facebook/Instagram) Ads daily performance.

    Normalizes raw Meta Ads data into the canonical staging contract:
    - tenant_id, report_date
    - platform_channel, canonical_channel
    - platform_account_id, internal_account_id
    - platform_campaign_id, internal_campaign_id
    - Core marketing metrics (spend, impressions, clicks, conversions, etc.)
    - Derived metrics (CPM, CPC, CTR, CPA, ROAS)

    Incremental with configurable lookback window for late-arriving conversions.
#}

with raw_meta_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_meta_ads') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'meta_ads') }}
    {% endif %}
),

meta_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Account & Campaign hierarchy
        raw.ad_data->>'account_id' as account_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'adset_id' as adset_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        -- Names
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'adset_name' as adset_name,
        raw.ad_data->>'ad_name' as ad_name,
        -- Dates
        raw.ad_data->>'date_start' as date_start_raw,
        raw.ad_data->>'date_stop' as date_stop_raw,
        -- Metrics
        raw.ad_data->>'spend' as spend_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        raw.ad_data->>'reach' as reach_raw,
        raw.ad_data->>'frequency' as frequency_raw,
        -- Conversions (can be in different fields depending on API version)
        -- actions is a JSONB array, need to extract purchase action properly
        coalesce(
            raw.ad_data->>'conversions',
            (
                select elem->>'value'
                from jsonb_array_elements(raw.ad_data->'actions') as elem
                where elem->>'action_type' = 'purchase'
                limit 1
            ),
            '0'
        ) as conversions_raw,
        coalesce(
            raw.ad_data->>'conversion_value',
            (
                select elem->>'value'
                from jsonb_array_elements(raw.ad_data->'action_values') as elem
                where elem->>'action_type' = 'purchase'
                limit 1
            ),
            '0'
        ) as conversion_value_raw,
        -- Platform metrics
        raw.ad_data->>'cpm' as cpm_raw,
        raw.ad_data->>'cpc' as cpc_raw,
        raw.ad_data->>'ctr' as ctr_raw,
        raw.ad_data->>'cpp' as cpp_raw,
        -- Campaign objective (for channel mapping)
        raw.ad_data->>'objective' as objective,
        -- Currency
        raw.ad_data->>'currency' as currency_code
    from raw_meta_ads raw
),

meta_ads_normalized as (
    select
        -- =====================================================================
        -- Primary identifiers
        -- =====================================================================
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
        end as platform_adgroup_id,

        case
            when ad_id_raw is null or trim(ad_id_raw) = '' then null
            else trim(ad_id_raw)
        end as platform_ad_id,

        -- =====================================================================
        -- Names (for reference, not used in joins)
        -- =====================================================================
        campaign_name,
        adset_name as adgroup_name,
        ad_name,
        objective,

        -- =====================================================================
        -- Report date (date grain)
        -- =====================================================================
        case
            when date_start_raw is null or trim(date_start_raw) = '' then null
            when date_start_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_start_raw::date
            else null
        end as report_date,

        case
            when date_stop_raw is null or trim(date_stop_raw) = '' then null
            when date_stop_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_stop_raw::date
            else null
        end as date_stop,

        -- =====================================================================
        -- Channel (derived from objective or default)
        -- =====================================================================
        case
            when lower(objective) like '%video%' then 'video'
            when lower(objective) like '%catalog%' then 'shopping'
            when lower(objective) like '%product%' then 'shopping'
            else 'feed'
        end as platform_channel,

        -- =====================================================================
        -- Core metrics
        -- =====================================================================
        case
            when spend_raw is null or trim(spend_raw) = '' then 0.0
            when trim(spend_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(spend_raw)::numeric, 0)
            else 0.0
        end as spend,

        case
            when impressions_raw is null or trim(impressions_raw) = '' then 0
            when trim(impressions_raw) ~ '^-?[0-9]+$'
                then greatest(trim(impressions_raw)::bigint, 0)
            else 0
        end as impressions,

        case
            when clicks_raw is null or trim(clicks_raw) = '' then 0
            when trim(clicks_raw) ~ '^-?[0-9]+$'
                then greatest(trim(clicks_raw)::bigint, 0)
            else 0
        end as clicks,

        case
            when reach_raw is null or trim(reach_raw) = '' then 0
            when trim(reach_raw) ~ '^-?[0-9]+$'
                then greatest(trim(reach_raw)::bigint, 0)
            else 0
        end as reach,

        case
            when conversions_raw is null or trim(conversions_raw) = '' then 0.0
            when trim(conversions_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(conversions_raw)::numeric, 0)
            else 0.0
        end as conversions,

        case
            when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
            when trim(conversion_value_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(conversion_value_raw)::numeric, 0)
            else 0.0
        end as conversion_value,

        -- =====================================================================
        -- Currency
        -- =====================================================================
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- =====================================================================
        -- Metadata
        -- =====================================================================
        airbyte_record_id,
        airbyte_emitted_at

    from meta_ads_extracted
),

-- Join to tenant mapping
meta_ads_with_tenant as (
    select
        m.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-facebook-marketing'
               and platform_account_id = m.platform_account_id
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from meta_ads_normalized m
),

final as (
    select
        -- =====================================================================
        -- Surrogate key
        -- =====================================================================
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(report_date::text, '') || '|' ||
            coalesce(platform_account_id, '') || '|' ||
            coalesce(platform_campaign_id, '') || '|' ||
            coalesce(platform_adgroup_id, '') || '|' ||
            coalesce(platform_ad_id, '')
        ) as row_surrogate_key,

        -- =====================================================================
        -- Core identity
        -- =====================================================================
        tenant_id,
        report_date,
        'meta_ads' as source,

        -- =====================================================================
        -- Channel taxonomy
        -- =====================================================================
        platform_channel,
        {{ map_canonical_channel("'meta_ads'", 'platform_channel') }} as canonical_channel,

        -- =====================================================================
        -- Account identity
        -- =====================================================================
        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'meta_ads'", 'platform_account_id') }} as internal_account_id,

        -- =====================================================================
        -- Campaign identity
        -- =====================================================================
        platform_campaign_id,
        {{ generate_internal_campaign_id('tenant_id', "'meta_ads'", 'platform_campaign_id') }} as internal_campaign_id,

        -- =====================================================================
        -- Ad group / Ad set identity
        -- =====================================================================
        platform_adgroup_id,
        {{ generate_internal_adgroup_id('tenant_id', "'meta_ads'", 'platform_adgroup_id') }} as internal_adgroup_id,

        -- =====================================================================
        -- Ad identity
        -- =====================================================================
        platform_ad_id,
        {{ generate_internal_ad_id('tenant_id', "'meta_ads'", 'platform_ad_id') }} as internal_ad_id,

        -- =====================================================================
        -- Names (for reference)
        -- =====================================================================
        campaign_name,
        adgroup_name,
        ad_name,
        objective,

        -- =====================================================================
        -- Core metrics
        -- =====================================================================
        spend,
        impressions,
        clicks,
        reach,
        conversions,
        conversion_value,
        currency,

        -- =====================================================================
        -- Derived metrics
        -- =====================================================================
        {{ calculate_cpm('spend', 'impressions') }} as cpm,
        {{ calculate_cpc('spend', 'clicks') }} as cpc,
        {{ calculate_ctr('clicks', 'impressions') }} as ctr,
        {{ calculate_cpa('spend', 'conversions') }} as cpa,
        {{ calculate_roas('conversion_value', 'spend') }} as roas_platform,

        -- =====================================================================
        -- Metadata
        -- =====================================================================
        airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from meta_ads_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null
)

select * from final
