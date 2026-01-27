{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge',
        enabled=var('enable_ga4', true)
    )
}}

{#
    Staging model for Google Analytics 4 daily traffic data.

    GA4 provides session and event-level data aggregated to daily grain.
    This model focuses on traffic acquisition and conversion metrics
    by source/medium/campaign for attribution analysis.

    Note: GA4 is typically used as an attribution source, not a cost source.
    Spend comes from ad platforms, not GA4.
#}

with raw_ga4_events as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as event_data
    from {{ source('raw_sources', 'raw_ga4_events') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'ga4') }}
    {% endif %}
),

ga4_events_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Property ID (account equivalent)
        raw.event_data->>'property_id' as property_id_raw,
        -- Traffic source dimensions
        raw.event_data->>'session_source' as source,
        raw.event_data->>'session_medium' as medium,
        raw.event_data->>'session_campaign' as campaign_name,
        raw.event_data->>'session_default_channel_grouping' as channel_grouping,
        -- Date
        raw.event_data->>'event_date' as date_raw,
        -- Session metrics
        raw.event_data->>'sessions' as sessions_raw,
        raw.event_data->>'engaged_sessions' as engaged_sessions_raw,
        raw.event_data->>'total_users' as users_raw,
        raw.event_data->>'new_users' as new_users_raw,
        -- Pageview metrics
        raw.event_data->>'screen_page_views' as pageviews_raw,
        -- Conversion metrics
        raw.event_data->>'conversions' as conversions_raw,
        raw.event_data->>'ecommerce_purchases' as purchases_raw,
        raw.event_data->>'ecommerce_revenue' as revenue_raw,
        raw.event_data->>'currency' as currency_code
    from raw_ga4_events raw
),

ga4_normalized as (
    select
        -- Property ID as account
        case
            when property_id_raw is null or trim(property_id_raw) = '' then null
            else trim(property_id_raw)
        end as platform_account_id,

        -- Use source/medium as campaign identifier
        source || ' / ' || medium as platform_campaign_id,

        campaign_name,
        source,
        medium,

        -- Channel grouping
        coalesce(lower(trim(channel_grouping)), 'direct') as platform_channel,

        -- Report date
        case
            when date_raw is null or trim(date_raw) = '' then null
            -- GA4 date format is YYYYMMDD
            when date_raw ~ '^\d{8}$'
                then to_date(date_raw, 'YYYYMMDD')
            when date_raw ~ '^\d{4}-\d{2}-\d{2}'
                then date_raw::date
            else null
        end as report_date,

        -- Session metrics
        case
            when sessions_raw is null or trim(sessions_raw) = '' then 0
            when trim(sessions_raw) ~ '^-?[0-9]+$'
                then greatest(trim(sessions_raw)::bigint, 0)
            else 0
        end as sessions,

        case
            when users_raw is null or trim(users_raw) = '' then 0
            when trim(users_raw) ~ '^-?[0-9]+$'
                then greatest(trim(users_raw)::bigint, 0)
            else 0
        end as users,

        case
            when new_users_raw is null or trim(new_users_raw) = '' then 0
            when trim(new_users_raw) ~ '^-?[0-9]+$'
                then greatest(trim(new_users_raw)::bigint, 0)
            else 0
        end as new_users,

        case
            when pageviews_raw is null or trim(pageviews_raw) = '' then 0
            when trim(pageviews_raw) ~ '^-?[0-9]+$'
                then greatest(trim(pageviews_raw)::bigint, 0)
            else 0
        end as pageviews,

        -- Conversion metrics
        case
            when purchases_raw is null or trim(purchases_raw) = '' then 0.0
            when trim(purchases_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(purchases_raw)::numeric, 0)
            else 0.0
        end as conversions,

        case
            when revenue_raw is null or trim(revenue_raw) = '' then 0.0
            when trim(revenue_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(revenue_raw)::numeric, 0)
            else 0.0
        end as conversion_value,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        airbyte_record_id,
        airbyte_emitted_at

    from ga4_events_extracted
),

ga4_with_tenant as (
    select
        g.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-google-analytics-data-api'
               and platform_account_id = g.platform_account_id
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from ga4_normalized g
),

final as (
    select
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(report_date::text, '') || '|' ||
            coalesce(platform_account_id, '') || '|' ||
            coalesce(platform_campaign_id, '') || '|' ||
            coalesce(platform_channel, '')
        ) as row_surrogate_key,

        tenant_id,
        report_date,
        'ga4' as source,

        platform_channel,
        {{ map_canonical_channel("'ga4'", 'platform_channel') }} as canonical_channel,

        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'ga4'", 'platform_account_id') }} as internal_account_id,

        platform_campaign_id,
        {{ generate_internal_campaign_id('tenant_id', "'ga4'", 'platform_campaign_id') }} as internal_campaign_id,

        null::text as platform_adgroup_id,
        null::text as internal_adgroup_id,
        null::text as platform_ad_id,
        null::text as internal_ad_id,

        campaign_name,
        null::text as adgroup_name,
        null::text as ad_name,
        null::text as objective,

        -- GA4 doesn't have spend data
        0.0::numeric as spend,
        sessions::bigint as impressions,  -- Sessions as proxy
        pageviews::bigint as clicks,      -- Pageviews as engagement proxy
        users::bigint as reach,
        conversions,
        conversion_value,
        currency,

        -- No cost-based metrics for GA4
        null::numeric as cpm,
        null::numeric as cpc,
        null::numeric as ctr,
        null::numeric as cpa,
        null::numeric as roas_platform,

        -- GA4-specific metrics
        sessions,
        users,
        new_users,
        pageviews,
        source as traffic_source,
        medium as traffic_medium,

        airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from ga4_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and report_date is not null
)

select * from final
