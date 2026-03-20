{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Staging model for Web Pixel customer journey events.

    This model:
    - Reads directly from the pixel_events table (not via Airbyte)
    - Normalizes event types and extracts UTM fields
    - Deduplicates by (session_id, event_type, event_timestamp) within 1-second window
    - Applies tenant isolation via tenant_id

    SECURITY: Tenant isolation enforced via tenant_id column.
#}

with raw_events as (
    select
        id,
        tenant_id,
        shop_domain,
        session_id,
        lower(trim(event_type)) as event_type,
        event_data,
        page_url,
        referrer,
        trim(utm_source) as utm_source,
        trim(utm_medium) as utm_medium,
        trim(utm_campaign) as utm_campaign,
        trim(utm_term) as utm_term,
        trim(utm_content) as utm_content,
        event_timestamp,
        created_at
    from {{ source('platform', 'pixel_events') }}
    where tenant_id is not null
      and session_id is not null
      and event_type is not null
),

-- Deduplicate: same session + event_type within 1 second = same event
deduped as (
    select
        *,
        row_number() over (
            partition by tenant_id, session_id, event_type,
                date_trunc('second', event_timestamp)
            order by created_at desc
        ) as dedup_rank
    from raw_events
)

select
    id,
    tenant_id,
    shop_domain,
    session_id,
    event_type,
    event_data,
    page_url,
    referrer,
    utm_source,
    utm_medium,
    utm_campaign,
    utm_term,
    utm_content,
    event_timestamp,
    created_at
from deduped
where dedup_rank = 1
