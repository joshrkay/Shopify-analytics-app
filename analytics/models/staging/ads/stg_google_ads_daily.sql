{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for Google Ads daily performance.

    Normalizes raw Google Ads data with special handling for:
    - Micros to dollars conversion (Google reports in micros = 1/1,000,000)
    - Multiple campaign types (Search, Display, Shopping, Video, etc.)
    - Fractional conversions (data-driven attribution)

    Output follows canonical staging contract.
#}

with raw_google_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_google_ads') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'google_ads') }}
    {% endif %}
),

google_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Account & Campaign hierarchy
        raw.ad_data->>'customer_id' as customer_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'ad_group_id' as ad_group_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        -- Names
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'ad_group_name' as ad_group_name,
        -- Campaign type for channel mapping
        raw.ad_data->>'advertising_channel_type' as channel_type,
        raw.ad_data->>'campaign_type' as campaign_type,
        -- Date
        raw.ad_data->>'segments_date' as date_raw,
        coalesce(
            raw.ad_data->>'segments_date',
            raw.ad_data->>'date',
            raw.ad_data->>'metrics_date'
        ) as report_date_raw,
        -- Metrics (Google reports in micros for cost)
        raw.ad_data->>'metrics_cost_micros' as cost_micros_raw,
        raw.ad_data->>'metrics_impressions' as impressions_raw,
        raw.ad_data->>'metrics_clicks' as clicks_raw,
        raw.ad_data->>'metrics_conversions' as conversions_raw,
        raw.ad_data->>'metrics_conversions_value' as conversion_value_raw,
        -- Quality metrics
        raw.ad_data->>'metrics_ctr' as ctr_raw,
        raw.ad_data->>'metrics_average_cpc' as avg_cpc_raw,
        -- Currency
        raw.ad_data->>'customer_currency_code' as currency_code
    from raw_google_ads raw
),

google_ads_normalized as (
    select
        -- =====================================================================
        -- Primary identifiers
        -- =====================================================================
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
        end as platform_adgroup_id,

        case
            when ad_id_raw is null or trim(ad_id_raw) = '' then null
            else trim(ad_id_raw)
        end as platform_ad_id,

        -- =====================================================================
        -- Names
        -- =====================================================================
        campaign_name,
        ad_group_name as adgroup_name,

        -- =====================================================================
        -- Channel type (for mapping)
        -- =====================================================================
        lower(coalesce(channel_type, campaign_type, 'search')) as platform_channel,

        -- =====================================================================
        -- Report date
        -- =====================================================================
        case
            when report_date_raw is null or trim(report_date_raw) = '' then null
            when report_date_raw ~ '^\d{4}-\d{2}-\d{2}'
                then report_date_raw::date
            else null
        end as report_date,

        -- =====================================================================
        -- Metrics (convert micros to dollars)
        -- =====================================================================
        case
            when cost_micros_raw is null or trim(cost_micros_raw) = '' then 0.0
            when trim(cost_micros_raw) ~ '^-?[0-9]+$'
                then greatest(trim(cost_micros_raw)::bigint / 1000000.0, 0)
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

        -- Conversions can be fractional in Google Ads (data-driven attribution)
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

    from google_ads_extracted
),

-- Join to tenant mapping
google_ads_with_tenant as (
    select
        g.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-google-ads'
               and platform_account_id = g.platform_account_id
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from google_ads_normalized g
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
        'google_ads' as source,

        -- =====================================================================
        -- Channel taxonomy
        -- =====================================================================
        platform_channel,
        {{ map_canonical_channel("'google_ads'", 'platform_channel') }} as canonical_channel,

        -- =====================================================================
        -- Account identity
        -- =====================================================================
        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'google_ads'", 'platform_account_id') }} as internal_account_id,

        -- =====================================================================
        -- Campaign identity
        -- =====================================================================
        platform_campaign_id,
        {{ generate_internal_campaign_id('tenant_id', "'google_ads'", 'platform_campaign_id') }} as internal_campaign_id,

        -- =====================================================================
        -- Ad group identity
        -- =====================================================================
        platform_adgroup_id,
        {{ generate_internal_adgroup_id('tenant_id', "'google_ads'", 'platform_adgroup_id') }} as internal_adgroup_id,

        -- =====================================================================
        -- Ad identity
        -- =====================================================================
        platform_ad_id,
        {{ generate_internal_ad_id('tenant_id', "'google_ads'", 'platform_ad_id') }} as internal_ad_id,

        -- =====================================================================
        -- Names
        -- =====================================================================
        campaign_name,
        adgroup_name,
        null::text as ad_name,
        null::text as objective,

        -- =====================================================================
        -- Core metrics
        -- =====================================================================
        spend,
        impressions,
        clicks,
        0::bigint as reach,  -- Google doesn't report reach at this level
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

    from google_ads_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null
)

select * from final
