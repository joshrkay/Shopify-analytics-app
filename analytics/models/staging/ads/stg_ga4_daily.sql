{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'date', 'source_medium', 'campaign'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Google Analytics 4 data with normalized fields and tenant isolation.

    GA4 provides traffic and conversion data by source/medium/campaign.
    This model aggregates to daily grain with channel attribution.

    GA4 field mappings:
    - date -> date
    - source -> traffic_source
    - medium -> traffic_medium
    - campaign -> campaign
    - sessions -> sessions
    - totalUsers -> users
    - newUsers -> new_users
    - transactions/conversions -> conversions
    - totalRevenue/purchaseRevenue -> conversion_value
#}

with raw_ga4 as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as ga_data
    from {{ source('airbyte_raw', '_airbyte_raw_ga4') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ get_lookback_days("ga4") }} days'
    {% endif %}
),

ga4_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.ga_data->>'date' as date_raw,
        coalesce(raw.ga_data->>'source', raw.ga_data->>'sessionSource', '(direct)') as traffic_source,
        coalesce(raw.ga_data->>'medium', raw.ga_data->>'sessionMedium', '(none)') as traffic_medium,
        coalesce(raw.ga_data->>'campaign', raw.ga_data->>'sessionCampaignName', '(not set)') as campaign,
        raw.ga_data->>'sessions' as sessions_raw,
        coalesce(raw.ga_data->>'totalUsers', raw.ga_data->>'users') as users_raw,
        raw.ga_data->>'newUsers' as new_users_raw,
        coalesce(raw.ga_data->>'transactions', raw.ga_data->>'conversions', raw.ga_data->>'ecommercePurchases') as conversions_raw,
        coalesce(raw.ga_data->>'totalRevenue', raw.ga_data->>'purchaseRevenue', raw.ga_data->>'revenue') as conversion_value_raw,
        coalesce(raw.ga_data->>'screenPageViews', raw.ga_data->>'pageviews') as pageviews_raw,
        coalesce(raw.ga_data->>'bounceRate', raw.ga_data->>'bounce_rate') as bounce_rate_raw,
        coalesce(raw.ga_data->>'averageSessionDuration', raw.ga_data->>'avg_session_duration') as avg_session_duration_raw,
        coalesce(raw.ga_data->>'currency', 'USD') as currency_code
    from raw_ga4 raw
),

ga4_normalized as (
    select
        case when date_raw is null or trim(date_raw) = '' then null
             when date_raw ~ '^\d{8}$' then to_date(date_raw, 'YYYYMMDD')
             when date_raw ~ '^\d{4}-\d{2}-\d{2}' then date_raw::date
             else null end as date,
        coalesce(traffic_source, '(direct)') as traffic_source,
        coalesce(traffic_medium, '(none)') as traffic_medium,
        coalesce(campaign, '(not set)') as campaign,
        concat(coalesce(traffic_source, '(direct)'), ' / ', coalesce(traffic_medium, '(none)')) as source_medium,
        case when sessions_raw is null or trim(sessions_raw) = '' then 0 when trim(sessions_raw) ~ '^[0-9]+$' then trim(sessions_raw)::integer else 0 end as sessions,
        case when users_raw is null or trim(users_raw) = '' then 0 when trim(users_raw) ~ '^[0-9]+$' then trim(users_raw)::integer else 0 end as users,
        case when new_users_raw is null or trim(new_users_raw) = '' then 0 when trim(new_users_raw) ~ '^[0-9]+$' then trim(new_users_raw)::integer else 0 end as new_users,
        case when conversions_raw is null or trim(conversions_raw) = '' then 0.0 when trim(conversions_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(conversions_raw)::numeric else 0.0 end as conversions,
        case when conversion_value_raw is null or trim(conversion_value_raw) = '' then 0.0 when trim(conversion_value_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(conversion_value_raw)::numeric else 0.0 end as conversion_value,
        case when pageviews_raw is null or trim(pageviews_raw) = '' then 0 when trim(pageviews_raw) ~ '^[0-9]+$' then trim(pageviews_raw)::integer else 0 end as pageviews,
        case when bounce_rate_raw is null or trim(bounce_rate_raw) = '' then null when trim(bounce_rate_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(bounce_rate_raw)::numeric else null end as bounce_rate,
        case when avg_session_duration_raw is null or trim(avg_session_duration_raw) = '' then null when trim(avg_session_duration_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(avg_session_duration_raw)::numeric else null end as avg_session_duration,
        case when currency_code is null or trim(currency_code) = '' then 'USD' when upper(trim(currency_code)) ~ '^[A-Z]{3}$' then upper(trim(currency_code)) else 'USD' end as currency,
        'ga4' as source,
        'ga4' as platform,
        airbyte_record_id, airbyte_emitted_at
    from ga4_extracted
),

ga4_with_tenant as (
    select ga.*,
        coalesce((select tenant_id from {{ ref('_tenant_airbyte_connections') }} where source_type = 'source-google-analytics-data-api' and status = 'active' and is_enabled = true limit 1), null) as tenant_id
    from ga4_normalized ga
),

ga4_final as (
    select
        tenant_id,
        date,
        date as report_date,
        source,
        traffic_source,
        traffic_medium,
        source_medium,
        campaign,
        -- Map medium to platform_channel for canonical channel mapping
        traffic_medium as platform_channel,
        {{ map_canonical_channel("'ga4'", 'traffic_medium') }} as canonical_channel,
        -- GA4 doesn't track spend (that comes from ad platforms)
        0.0 as spend,
        sessions as impressions,  -- Sessions as proxy for impressions
        0 as clicks,  -- GA4 doesn't track clicks in the same way
        conversions,
        conversion_value,
        currency,
        -- GA4 specific metrics
        sessions,
        users,
        new_users,
        pageviews,
        bounce_rate,
        avg_session_duration,
        -- Derived metrics
        case when sessions > 0 then round(conversions / sessions, 4) else null end as conversion_rate,
        case when users > 0 then round(sessions::numeric / users, 2) else null end as sessions_per_user,
        case when sessions > 0 then round(pageviews::numeric / sessions, 2) else null end as pages_per_session,
        platform,
        airbyte_record_id,
        airbyte_emitted_at
    from ga4_with_tenant
)

select * from ga4_final
where tenant_id is not null and date is not null
{% if is_incremental() %} and date >= current_date - {{ get_lookback_days('ga4') }} {% endif %}
