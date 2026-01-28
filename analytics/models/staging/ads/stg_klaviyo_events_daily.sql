{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'event_id', 'date'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Klaviyo events with normalized fields and tenant isolation.

    Klaviyo tracks email marketing events (sends, opens, clicks, conversions).
    This model aggregates to daily grain for consistency with other staging models.

    Klaviyo API field mappings:
    - id -> event_id
    - datetime -> event_timestamp
    - metric.name -> event_type (Received Email, Opened Email, Clicked Email, etc.)
    - profile_id -> profile_id
    - flow_id/campaign_id -> campaign_id
    - $value -> conversion_value (for order events)
#}

with raw_klaviyo as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as event_data
    from {{ source('airbyte_raw', '_airbyte_raw_klaviyo') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ get_lookback_days("klaviyo") }} days'
    {% endif %}
),

klaviyo_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.event_data->>'id' as event_id_raw,
        coalesce(raw.event_data->>'datetime', raw.event_data->>'timestamp') as event_timestamp_raw,
        coalesce(raw.event_data->'metric'->>'name', raw.event_data->>'event_name', raw.event_data->>'type') as event_type,
        raw.event_data->>'profile_id' as profile_id,
        coalesce(raw.event_data->>'flow_id', raw.event_data->>'campaign_id') as campaign_id_raw,
        raw.event_data->>'campaign_name' as campaign_name,
        raw.event_data->>'flow_name' as flow_name,
        raw.event_data->>'subject' as email_subject,
        coalesce(raw.event_data->'event_properties'->>'$value', raw.event_data->>'value', '0') as conversion_value_raw,
        coalesce(raw.event_data->>'currency', 'USD') as currency_code
    from raw_klaviyo raw
),

klaviyo_normalized as (
    select
        case when event_id_raw is null or trim(event_id_raw) = '' then null else trim(event_id_raw) end as event_id,
        case when event_timestamp_raw is null or trim(event_timestamp_raw) = '' then null
             when event_timestamp_raw ~ '^\d{4}-\d{2}-\d{2}' then (event_timestamp_raw::timestamp with time zone) at time zone 'UTC'
             else null end as event_timestamp,
        coalesce(event_type, 'unknown') as event_type,
        profile_id,
        case when campaign_id_raw is null or trim(campaign_id_raw) = '' then null else trim(campaign_id_raw) end as campaign_id,
        campaign_name,
        flow_name,
        email_subject,
        case when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0
             when trim(conversion_value_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(conversion_value_raw)::numeric
             else 0.0 end as conversion_value,
        case when currency_code is null or trim(currency_code) = '' then 'USD'
             when upper(trim(currency_code)) ~ '^[A-Z]{3}$' then upper(trim(currency_code))
             else 'USD' end as currency,
        'klaviyo' as source,
        'klaviyo' as platform,
        'email' as platform_channel,
        airbyte_record_id, airbyte_emitted_at
    from klaviyo_extracted
),

klaviyo_with_tenant as (
    select events.*,
        coalesce((select tenant_id from {{ ref('_tenant_airbyte_connections') }} where source_type = 'source-klaviyo' and status = 'active' and is_enabled = true limit 1), null) as tenant_id
    from klaviyo_normalized events
),

-- Aggregate to daily grain with event counts
klaviyo_daily as (
    select
        tenant_id,
        event_timestamp::date as date,
        event_timestamp::date as report_date,
        source,
        campaign_id,
        campaign_name,
        flow_name,
        platform_channel,
        {{ map_canonical_channel("'klaviyo'", "'email'") }} as canonical_channel,
        -- Event counts by type
        count(*) as total_events,
        count(case when event_type ilike '%received%' or event_type ilike '%sent%' then 1 end) as emails_sent,
        count(case when event_type ilike '%opened%' then 1 end) as emails_opened,
        count(case when event_type ilike '%clicked%' then 1 end) as emails_clicked,
        count(case when event_type ilike '%unsubscribed%' then 1 end) as unsubscribes,
        count(case when event_type ilike '%bounced%' then 1 end) as bounces,
        count(case when event_type ilike '%placed order%' or event_type ilike '%ordered%' then 1 end) as conversions,
        sum(conversion_value) as conversion_value,
        currency,
        -- For compatibility with ad staging models
        0.0 as spend,
        count(case when event_type ilike '%received%' or event_type ilike '%sent%' then 1 end) as impressions,
        count(case when event_type ilike '%clicked%' then 1 end) as clicks,
        platform,
        min(airbyte_emitted_at) as airbyte_emitted_at
    from klaviyo_with_tenant
    where tenant_id is not null
        and event_timestamp is not null
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 18, 22
),

klaviyo_final as (
    select
        tenant_id, date, report_date, source,
        campaign_id,
        {{ generate_internal_id('tenant_id', 'source', 'campaign_id') }} as internal_campaign_id,
        campaign_name, flow_name,
        platform_channel, canonical_channel,
        spend, impressions, clicks, conversions::numeric as conversions, conversion_value, currency,
        -- Derived metrics for email
        case when emails_sent > 0 then round((emails_opened::numeric / emails_sent) * 100, 4) else null end as open_rate,
        case when emails_opened > 0 then round((emails_clicked::numeric / emails_opened) * 100, 4) else null end as click_to_open_rate,
        case when emails_sent > 0 then round((emails_clicked::numeric / emails_sent) * 100, 4) else null end as ctr,
        case when emails_sent > 0 then round((unsubscribes::numeric / emails_sent) * 100, 4) else null end as unsubscribe_rate,
        emails_sent, emails_opened, emails_clicked, unsubscribes, bounces, total_events,
        platform, airbyte_emitted_at
    from klaviyo_daily
)

select * from klaviyo_final
where date is not null
{% if is_incremental() %} and date >= current_date - {{ get_lookback_days('klaviyo') }} {% endif %}
