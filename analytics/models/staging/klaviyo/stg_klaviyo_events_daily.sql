{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date', 'event_type'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Klaviyo events aggregated daily.

    Supports email and SMS marketing events:
    - Email: opened, clicked, received, bounced, unsubscribed
    - SMS: sent, received, clicked

    Required contract fields:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - Event metrics aggregated by day and type

    PII Policy: No PII fields exposed. IDs and aggregate metrics only.
#}

with raw_klaviyo_events as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as event_data
    from {{ source('airbyte_raw', '_airbyte_raw_klaviyo_events') }}
),

klaviyo_events_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.event_data->>'id' as event_id_raw,
        raw.event_data->>'timestamp' as timestamp_raw,
        raw.event_data->>'datetime' as datetime_raw,
        raw.event_data->>'event_name' as event_name_raw,
        raw.event_data->>'metric_id' as metric_id,
        raw.event_data->>'campaign_id' as campaign_id_raw,
        raw.event_data->>'flow_id' as flow_id,
        raw.event_data->>'flow_message_id' as flow_message_id,
        -- Revenue from e-commerce events (Placed Order, etc.)
        raw.event_data->'event_properties'->>'$value' as revenue_raw,
        raw.event_data->'event_properties'->>'currency' as currency_code,
        -- Message type for channel classification
        raw.event_data->>'message_type' as message_type
    from raw_klaviyo_events raw
),

klaviyo_events_normalized as (
    select
        -- Event ID
        case
            when event_id_raw is null or trim(event_id_raw) = '' then null
            else trim(event_id_raw)
        end as event_id,

        -- Extract date from timestamp
        case
            when timestamp_raw is not null and trim(timestamp_raw) != '' then
                case
                    when timestamp_raw ~ '^\d+$' then
                        (to_timestamp(timestamp_raw::bigint))::date
                    when timestamp_raw ~ '^\d{4}-\d{2}-\d{2}' then
                        timestamp_raw::date
                    else null
                end
            when datetime_raw is not null and datetime_raw ~ '^\d{4}-\d{2}-\d{2}' then
                datetime_raw::date
            else null
        end as report_date,

        -- Event name normalization
        lower(coalesce(event_name_raw, 'unknown')) as event_type,

        -- Campaign ID
        case
            when campaign_id_raw is null or trim(campaign_id_raw) = '' then null
            else trim(campaign_id_raw)
        end as platform_campaign_id,

        -- Flow ID (for automated flows)
        flow_id,
        flow_message_id,
        metric_id,

        -- Revenue (for conversion events)
        case
            when revenue_raw is null or trim(revenue_raw) = '' then 0.0
            when trim(revenue_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then greatest(trim(revenue_raw)::numeric, 0)
            else 0.0
        end as revenue,

        -- Currency
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Channel classification (email vs sms)
        case
            when lower(coalesce(message_type, '')) like '%sms%' then 'sms'
            when lower(coalesce(event_name_raw, '')) like '%sms%' then 'sms'
            else 'email'
        end as platform_channel,

        -- Source
        'klaviyo' as source,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from klaviyo_events_extracted
),

-- Aggregate events by day, event type, and campaign
klaviyo_daily_aggregated as (
    select
        report_date,
        event_type,
        platform_campaign_id,
        platform_channel,
        source,
        currency,
        count(*) as event_count,
        sum(revenue) as total_revenue,
        max(airbyte_emitted_at) as airbyte_emitted_at
    from klaviyo_events_normalized
    where report_date is not null
    group by
        report_date,
        event_type,
        platform_campaign_id,
        platform_channel,
        source,
        currency
),

-- Join to tenant mapping
klaviyo_with_tenant as (
    select
        agg.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-klaviyo'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from klaviyo_daily_aggregated agg
)

select
    -- Primary identifiers
    tenant_id,
    report_date,
    source,

    -- Event classification
    event_type,
    platform_campaign_id,

    -- Internal campaign ID (if campaign exists)
    case
        when platform_campaign_id is not null then
            {{ generate_internal_campaign_id('tenant_id', "'klaviyo'", 'platform_campaign_id') }}
        else null
    end as internal_campaign_id,

    -- Channel taxonomy
    platform_channel,
    {{ map_canonical_channel("'klaviyo'", 'platform_channel') }} as canonical_channel,

    -- Metrics
    event_count,
    total_revenue as conversion_value,
    currency,

    -- Email/SMS specific metrics (derived from event_type)
    case when event_type in ('received email', 'email_received', 'received') then event_count else 0 end as emails_sent,
    case when event_type in ('opened email', 'email_opened', 'opened') then event_count else 0 end as emails_opened,
    case when event_type in ('clicked email', 'email_clicked', 'clicked') then event_count else 0 end as emails_clicked,
    case when event_type in ('bounced email', 'email_bounced', 'bounced') then event_count else 0 end as emails_bounced,
    case when event_type in ('unsubscribed', 'email_unsubscribed') then event_count else 0 end as unsubscribes,
    case when event_type in ('sms_sent', 'sent sms') then event_count else 0 end as sms_sent,
    case when event_type in ('sms_clicked', 'clicked sms') then event_count else 0 end as sms_clicked,
    case when event_type in ('placed order', 'ordered product') then event_count else 0 end as conversions,

    -- Metadata
    airbyte_emitted_at

from klaviyo_with_tenant
where tenant_id is not null

{{ incremental_filter('report_date', 'klaviyo') }}
