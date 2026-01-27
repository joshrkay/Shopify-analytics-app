{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for Amazon Ads daily performance.

    Amazon Advertising has multiple ad types:
    - Sponsored Products (SP)
    - Sponsored Brands (SB)
    - Sponsored Display (SD)

    Amazon reports can have longer delays (up to 14 days for attribution).
#}

with raw_amazon_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('raw_sources', 'raw_amazon_ads_reports') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'amazon_ads') }}
    {% endif %}
),

amazon_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Account & Campaign hierarchy
        raw.ad_data->>'profileId' as profile_id_raw,
        raw.ad_data->>'campaignId' as campaign_id_raw,
        raw.ad_data->>'adGroupId' as ad_group_id_raw,
        raw.ad_data->>'adId' as ad_id_raw,
        -- Names
        raw.ad_data->>'campaignName' as campaign_name,
        raw.ad_data->>'adGroupName' as ad_group_name,
        -- Date
        raw.ad_data->>'date' as date_raw,
        -- Metrics
        raw.ad_data->>'cost' as spend_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        raw.ad_data->>'clicks' as clicks_raw,
        raw.ad_data->>'purchases14d' as conversions_raw,
        raw.ad_data->>'sales14d' as conversion_value_raw,
        -- Ad type for channel mapping
        raw.ad_data->>'adType' as ad_type,
        raw.ad_data->>'campaignType' as campaign_type,
        -- Currency
        raw.ad_data->>'currency' as currency_code
    from raw_amazon_ads raw
),

amazon_ads_normalized as (
    select
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
        end as platform_adgroup_id,

        case
            when ad_id_raw is null or trim(ad_id_raw) = '' then null
            else trim(ad_id_raw)
        end as platform_ad_id,

        campaign_name,
        ad_group_name as adgroup_name,
        ad_type as objective,

        -- Map ad type to platform channel
        case
            when lower(ad_type) like '%sponsored_products%' or lower(campaign_type) like '%sp%' then 'sponsored_products'
            when lower(ad_type) like '%sponsored_brands%' or lower(campaign_type) like '%sb%' then 'sponsored_brands'
            when lower(ad_type) like '%sponsored_display%' or lower(campaign_type) like '%sd%' then 'sponsored_display'
            else 'sponsored_products'
        end as platform_channel,

        case
            when date_raw is null or trim(date_raw) = '' then null
            when date_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_raw::date
            else null
        end as report_date,

        case
            when spend_raw is null or trim(spend_raw) = '' then 0.0
            when trim(spend_raw) ~ '^-?[0-9]+\.?[0-9]*$'
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
            when conversions_raw is null or trim(conversions_raw) = '' then 0.0
            when trim(conversions_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(conversions_raw)::numeric, 0)
            else 0.0
        end as conversions,

        case
            when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
            when trim(conversion_value_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(conversion_value_raw)::numeric, 0)
            else 0.0
        end as conversion_value,

        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        airbyte_record_id,
        airbyte_emitted_at

    from amazon_ads_extracted
),

amazon_ads_with_tenant as (
    select
        a.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-amazon-ads'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from amazon_ads_normalized a
),

final as (
    select
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(report_date::text, '') || '|' ||
            coalesce(platform_account_id, '') || '|' ||
            coalesce(platform_campaign_id, '') || '|' ||
            coalesce(platform_adgroup_id, '') || '|' ||
            coalesce(platform_ad_id, '')
        ) as row_surrogate_key,

        tenant_id,
        report_date,
        'amazon_ads' as source,

        platform_channel,
        {{ map_canonical_channel("'amazon_ads'", 'platform_channel') }} as canonical_channel,

        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'amazon_ads'", 'platform_account_id') }} as internal_account_id,

        platform_campaign_id,
        {{ generate_internal_campaign_id('tenant_id', "'amazon_ads'", 'platform_campaign_id') }} as internal_campaign_id,

        platform_adgroup_id,
        {{ generate_internal_adgroup_id('tenant_id', "'amazon_ads'", 'platform_adgroup_id') }} as internal_adgroup_id,

        platform_ad_id,
        {{ generate_internal_ad_id('tenant_id', "'amazon_ads'", 'platform_ad_id') }} as internal_ad_id,

        campaign_name,
        adgroup_name,
        null::text as ad_name,
        objective,

        spend,
        impressions,
        clicks,
        0::bigint as reach,
        conversions,
        conversion_value,
        currency,

        {{ calculate_cpm('spend', 'impressions') }} as cpm,
        {{ calculate_cpc('spend', 'clicks') }} as cpc,
        {{ calculate_ctr('clicks', 'impressions') }} as ctr,
        {{ calculate_cpa('spend', 'conversions') }} as cpa,
        {{ calculate_roas('conversion_value', 'spend') }} as roas_platform,

        airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from amazon_ads_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null
)

select * from final
