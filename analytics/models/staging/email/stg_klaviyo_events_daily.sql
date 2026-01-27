{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge',
        enabled=var('enable_klaviyo', true)
    )
}}

{#
    Staging model for Klaviyo events aggregated to daily grain.

    Klaviyo events include:
    - Email sends, opens, clicks
    - SMS sends, clicks
    - Conversion events (placed order, started checkout)

    This model aggregates event-level data to daily campaign performance.
    PII is excluded - no email addresses or phone numbers.
#}

with raw_klaviyo_events as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as event_data
    from {{ source('raw_sources', 'raw_klaviyo_events') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'klaviyo') }}
    {% endif %}
),

klaviyo_events_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Account identifier (Klaviyo public API key or account ID)
        raw.event_data->>'account_id' as account_id_raw,
        -- Campaign/Flow identifiers
        raw.event_data->>'campaign_id' as campaign_id_raw,
        raw.event_data->>'flow_id' as flow_id_raw,
        raw.event_data->>'message_id' as message_id_raw,
        -- Event details
        raw.event_data->>'event_name' as event_name,
        raw.event_data->>'timestamp' as timestamp_raw,
        -- Metrics from event properties
        raw.event_data->'event_properties'->>'value' as revenue_raw,
        raw.event_data->'event_properties'->>'currency' as currency_code,
        -- Channel type
        raw.event_data->>'channel' as channel_type,
        -- Campaign/Flow name
        raw.event_data->>'campaign_name' as campaign_name,
        raw.event_data->>'flow_name' as flow_name
    from raw_klaviyo_events raw
),

-- Aggregate events to daily campaign level
klaviyo_daily_aggregated as (
    select
        -- Account
        case
            when account_id_raw is null or trim(account_id_raw) = '' then null
            else trim(account_id_raw)
        end as platform_account_id,

        -- Campaign or Flow ID (combined)
        coalesce(
            nullif(trim(campaign_id_raw), ''),
            nullif(trim(flow_id_raw), '')
        ) as platform_campaign_id,

        -- Campaign or Flow name
        coalesce(campaign_name, flow_name) as campaign_name,

        -- Channel type
        coalesce(lower(trim(channel_type)), 'email') as platform_channel,

        -- Report date
        case
            when timestamp_raw is null or trim(timestamp_raw) = '' then null
            when timestamp_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (timestamp_raw::timestamp with time zone)::date
            else null
        end as report_date,

        -- Event counts by type
        count(*) filter (where lower(event_name) in ('received email', 'sent sms', 'received sms')) as sends,
        count(*) filter (where lower(event_name) in ('opened email')) as opens,
        count(*) filter (where lower(event_name) in ('clicked email', 'clicked sms')) as clicks,
        count(*) filter (where lower(event_name) in ('placed order', 'ordered product')) as conversions,

        -- Revenue from conversion events
        sum(
            case
                when lower(event_name) in ('placed order', 'ordered product')
                    and revenue_raw is not null
                    and trim(revenue_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(revenue_raw)::numeric, 0)
                else 0
            end
        ) as conversion_value,

        -- Currency (take the most common)
        mode() within group (order by upper(coalesce(currency_code, 'USD'))) as currency,

        -- Metadata
        max(airbyte_emitted_at) as airbyte_emitted_at

    from klaviyo_events_extracted
    where report_date is not null
    group by 1, 2, 3, 4, 5
),

klaviyo_with_tenant as (
    select
        k.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-klaviyo'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from klaviyo_daily_aggregated k
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
        'klaviyo' as source,

        platform_channel,
        {{ map_canonical_channel("'klaviyo'", 'platform_channel') }} as canonical_channel,

        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'klaviyo'", 'platform_account_id') }} as internal_account_id,

        platform_campaign_id,
        {{ generate_internal_campaign_id('tenant_id', "'klaviyo'", 'platform_campaign_id') }} as internal_campaign_id,

        -- Klaviyo doesn't have ad groups/ads
        null::text as platform_adgroup_id,
        null::text as internal_adgroup_id,
        null::text as platform_ad_id,
        null::text as internal_ad_id,

        campaign_name,
        null::text as adgroup_name,
        null::text as ad_name,
        null::text as objective,

        -- Klaviyo is typically free/no spend
        0.0::numeric as spend,
        sends::bigint as impressions,  -- Sends as proxy for impressions
        clicks::bigint as clicks,
        0::bigint as reach,
        conversions::numeric as conversions,
        conversion_value,
        currency,

        -- Derived metrics
        null::numeric as cpm,  -- No spend
        null::numeric as cpc,
        {{ calculate_ctr('clicks', 'sends') }} as ctr,
        null::numeric as cpa,
        null::numeric as roas_platform,

        -- Email-specific metrics
        sends,
        opens,
        {{ calculate_ctr('opens', 'sends') }} as open_rate,

        null::text as airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from klaviyo_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and platform_campaign_id is not null
        and report_date is not null
)

select * from final
