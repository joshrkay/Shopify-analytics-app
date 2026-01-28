{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'ad_account_id', 'campaign_id', 'ad_squad_id', 'ad_id', 'date'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Snapchat Ads with normalized fields and tenant isolation.

    Snapchat Ads API field mappings:
    - ad_account_id -> ad_account_id
    - campaign_id -> campaign_id
    - ad_squad_id -> ad_squad_id (similar to adset/ad_group)
    - ad_id -> ad_id
    - start_time/end_time -> date
    - spend (in micro-currency) -> spend
    - impressions -> impressions
    - swipes -> clicks
    - conversions_* -> conversions
#}

with raw_snap_ads as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ad_data
    from {{ source('airbyte_raw', '_airbyte_raw_snapchat_ads') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ get_lookback_days("snap_ads") }} days'
    {% endif %}
),

snap_ads_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ad_data->>'ad_account_id' as ad_account_id_raw,
        raw.ad_data->>'campaign_id' as campaign_id_raw,
        raw.ad_data->>'ad_squad_id' as ad_squad_id_raw,
        raw.ad_data->>'ad_id' as ad_id_raw,
        coalesce(raw.ad_data->>'date', raw.ad_data->>'start_time') as date_raw,
        raw.ad_data->>'spend' as spend_raw,
        raw.ad_data->>'impressions' as impressions_raw,
        coalesce(raw.ad_data->>'swipes', raw.ad_data->>'clicks') as clicks_raw,
        coalesce(raw.ad_data->>'conversions_purchases', raw.ad_data->>'conversions') as conversions_raw,
        raw.ad_data->>'conversion_purchases_value' as conversion_value_raw,
        coalesce(raw.ad_data->>'currency', 'USD') as currency_code,
        raw.ad_data->>'campaign_name' as campaign_name,
        raw.ad_data->>'ad_squad_name' as ad_squad_name,
        raw.ad_data->>'ad_name' as ad_name,
        raw.ad_data->>'objective' as objective,
        'story' as platform_channel_raw
    from raw_snap_ads raw
),

snap_ads_normalized as (
    select
        case when ad_account_id_raw is null or trim(ad_account_id_raw) = '' then null else trim(ad_account_id_raw) end as ad_account_id,
        case when campaign_id_raw is null or trim(campaign_id_raw) = '' then null else trim(campaign_id_raw) end as campaign_id,
        case when ad_squad_id_raw is null or trim(ad_squad_id_raw) = '' then null else trim(ad_squad_id_raw) end as ad_squad_id,
        case when ad_id_raw is null or trim(ad_id_raw) = '' then null else trim(ad_id_raw) end as ad_id,
        case when date_raw is null or trim(date_raw) = '' then null when date_raw ~ '^\d{4}-\d{2}-\d{2}' then date_raw::date else null end as date,
        -- Snap uses micro-currency (divide by 1,000,000)
        case
            when spend_raw is not null and trim(spend_raw) != '' and trim(spend_raw) ~ '^-?[0-9]+$'
                then (trim(spend_raw)::bigint / 1000000.0)::numeric
            else 0.0
        end as spend,
        case when impressions_raw is null or trim(impressions_raw) = '' then 0 when trim(impressions_raw) ~ '^[0-9]+$' then trim(impressions_raw)::integer else 0 end as impressions,
        case when clicks_raw is null or trim(clicks_raw) = '' then 0 when trim(clicks_raw) ~ '^[0-9]+$' then trim(clicks_raw)::integer else 0 end as clicks,
        case when conversions_raw is null or trim(conversions_raw) = '' then 0.0 when trim(conversions_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(conversions_raw)::numeric else 0.0 end as conversions,
        case when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0 when trim(conversion_value_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(conversion_value_raw)::numeric else 0.0 end as conversion_value,
        case when currency_code is null or trim(currency_code) = '' then 'USD' when upper(trim(currency_code)) ~ '^[A-Z]{3}$' then upper(trim(currency_code)) else 'USD' end as currency,
        campaign_name, ad_squad_name, ad_name, objective,
        coalesce(platform_channel_raw, 'story') as platform_channel,
        'snap_ads' as source,
        'snap_ads' as platform,
        airbyte_record_id, airbyte_emitted_at
    from snap_ads_extracted
),

snap_ads_with_tenant as (
    select ads.*,
        coalesce((select tenant_id from {{ ref('_tenant_airbyte_connections') }} where source_type = 'source-snapchat-marketing' and status = 'active' and is_enabled = true limit 1), null) as tenant_id
    from snap_ads_normalized ads
),

snap_ads_final as (
    select
        tenant_id, date, date as report_date, source, ad_account_id, campaign_id, ad_squad_id, ad_id,
        {{ generate_internal_id('tenant_id', 'source', 'ad_account_id') }} as internal_account_id,
        {{ generate_internal_id('tenant_id', 'source', 'campaign_id') }} as internal_campaign_id,
        platform_channel,
        {{ map_canonical_channel('source', 'platform_channel') }} as canonical_channel,
        spend, impressions, clicks, conversions, conversion_value, currency,
        case when impressions > 0 then round((spend / impressions) * 1000, 4) else null end as cpm,
        case when clicks > 0 then round(spend / clicks, 4) else null end as cpc,
        case when impressions > 0 then round((clicks::numeric / impressions) * 100, 4) else null end as ctr,
        case when conversions > 0 then round(spend / conversions, 4) else null end as cpa,
        case when spend > 0 then round(conversion_value / spend, 4) else null end as roas_platform,
        campaign_name, ad_squad_name, ad_name, objective, platform, airbyte_record_id, airbyte_emitted_at
    from snap_ads_with_tenant
)

select * from snap_ads_final
where tenant_id is not null and ad_account_id is not null and campaign_id is not null and date is not null
{% if is_incremental() %} and date >= current_date - {{ get_lookback_days('snap_ads') }} {% endif %}
