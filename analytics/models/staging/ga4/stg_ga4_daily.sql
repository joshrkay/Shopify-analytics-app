{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date', 'session_default_channel_grouping', 'source_medium'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for GA4 (Google Analytics 4) daily metrics.

    Aggregates session and event data by:
    - Date
    - Default channel grouping
    - Source/medium

    Required contract fields:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - Session and engagement metrics

    PII Policy: No PII fields exposed. Aggregate metrics only.
#}

with raw_ga4_events as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as event_data
    from {{ source('airbyte_raw', '_airbyte_raw_ga4_events') }}
),

ga4_events_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.event_data->>'event_date' as event_date_raw,
        raw.event_data->>'event_name' as event_name,
        raw.event_data->>'session_default_channel_grouping' as channel_grouping,
        raw.event_data->>'traffic_source_source' as traffic_source,
        raw.event_data->>'traffic_source_medium' as traffic_medium,
        raw.event_data->>'traffic_source_name' as traffic_campaign,
        raw.event_data->>'session_id' as session_id,
        raw.event_data->>'user_pseudo_id' as user_pseudo_id,
        -- Engagement metrics
        raw.event_data->>'engagement_time_msec' as engagement_time_raw,
        raw.event_data->>'session_engaged' as session_engaged_raw,
        -- E-commerce events
        raw.event_data->'ecommerce'->>'purchase_revenue' as purchase_revenue_raw,
        raw.event_data->'ecommerce'->>'transaction_id' as transaction_id,
        raw.event_data->>'currency' as currency_code
    from raw_ga4_events raw
),

ga4_events_normalized as (
    select
        -- Date field (GA4 uses YYYYMMDD format)
        case
            when event_date_raw is null or trim(event_date_raw) = '' then null
            when event_date_raw ~ '^\d{8}$' then
                to_date(event_date_raw, 'YYYYMMDD')
            when event_date_raw ~ '^\d{4}-\d{2}-\d{2}' then
                event_date_raw::date
            else null
        end as report_date,

        -- Event name
        lower(coalesce(event_name, 'unknown')) as event_name,

        -- Channel grouping (Google's default classification)
        coalesce(channel_grouping, 'direct') as session_default_channel_grouping,

        -- Source/medium
        coalesce(traffic_source, '(direct)') as traffic_source,
        coalesce(traffic_medium, '(none)') as traffic_medium,
        concat(
            coalesce(traffic_source, '(direct)'),
            ' / ',
            coalesce(traffic_medium, '(none)')
        ) as source_medium,
        traffic_campaign,

        -- Session identification
        session_id,
        user_pseudo_id,

        -- Engagement
        case
            when engagement_time_raw is not null
                and trim(engagement_time_raw) ~ '^[0-9]+$' then
                (trim(engagement_time_raw)::bigint / 1000.0)::numeric  -- Convert ms to seconds
            else 0
        end as engagement_time_seconds,

        case
            when session_engaged_raw = '1' or lower(session_engaged_raw) = 'true' then 1
            else 0
        end as is_engaged_session,

        -- Revenue
        case
            when purchase_revenue_raw is not null
                and trim(purchase_revenue_raw) ~ '^-?[0-9]+\.?[0-9]*$' then
                greatest(trim(purchase_revenue_raw)::numeric, 0)
            else 0
        end as revenue,

        transaction_id,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Source
        'ga4' as source,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from ga4_events_extracted
),

-- Aggregate by day and channel
ga4_daily_aggregated as (
    select
        report_date,
        session_default_channel_grouping,
        source_medium,
        traffic_source,
        traffic_medium,
        currency,
        'ga4' as source,

        -- Session metrics
        count(distinct session_id) as sessions,
        count(distinct user_pseudo_id) as users,
        sum(is_engaged_session) as engaged_sessions,
        sum(engagement_time_seconds) as total_engagement_time_seconds,

        -- Event metrics
        count(*) as total_events,
        count(case when event_name = 'page_view' then 1 end) as pageviews,
        count(case when event_name = 'session_start' then 1 end) as session_starts,
        count(case when event_name = 'purchase' then 1 end) as purchases,
        count(case when event_name = 'add_to_cart' then 1 end) as add_to_carts,
        count(case when event_name = 'begin_checkout' then 1 end) as begin_checkouts,

        -- Revenue
        sum(revenue) as total_revenue,
        count(distinct transaction_id) filter (where transaction_id is not null) as transactions,

        max(airbyte_emitted_at) as airbyte_emitted_at

    from ga4_events_normalized
    where report_date is not null
    group by
        report_date,
        session_default_channel_grouping,
        source_medium,
        traffic_source,
        traffic_medium,
        currency
),

-- Join to tenant mapping
ga4_with_tenant as (
    select
        agg.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-google-analytics-data-api'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from ga4_daily_aggregated agg
)

select
    -- Primary identifiers
    tenant_id,
    report_date,
    source,

    -- Channel taxonomy
    session_default_channel_grouping as platform_channel,
    {{ map_canonical_channel("'ga4'", 'session_default_channel_grouping') }} as canonical_channel,

    -- Source/medium breakdown
    source_medium,
    traffic_source,
    traffic_medium,

    -- Session metrics
    sessions,
    users,
    engaged_sessions,
    total_engagement_time_seconds,
    case when sessions > 0 then engaged_sessions::numeric / sessions else 0 end as engagement_rate,
    case when sessions > 0 then total_engagement_time_seconds / sessions else 0 end as avg_engagement_time_seconds,

    -- Event metrics
    total_events,
    pageviews,
    case when sessions > 0 then pageviews::numeric / sessions else 0 end as pages_per_session,

    -- Conversion funnel
    add_to_carts,
    begin_checkouts,
    purchases as conversions,
    transactions,

    -- Revenue
    total_revenue as conversion_value,
    currency,

    -- Conversion rates
    case when sessions > 0 then purchases::numeric / sessions * 100 else 0 end as conversion_rate,
    case when add_to_carts > 0 then purchases::numeric / add_to_carts * 100 else 0 end as cart_to_purchase_rate,

    -- Metadata
    airbyte_emitted_at

from ga4_with_tenant
where tenant_id is not null

{{ incremental_filter('report_date', 'ga4') }}
