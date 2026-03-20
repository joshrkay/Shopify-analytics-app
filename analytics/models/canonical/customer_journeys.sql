{{
    config(
        materialized='incremental',
        unique_key='id',
        schema='analytics',
        on_schema_change='append_new_columns'
    )
}}

{#
    Customer Journeys model — aggregates sessions by visitor into journey profiles.

    Groups customer_sessions by visitor_id (derived from session linkage) to build
    a longitudinal view of each visitor's engagement over time.

    Enables:
    - Repeat visit analysis (how many sessions before first purchase?)
    - Conversion path length analysis
    - Visitor-level attribution (all touchpoints across sessions)
    - Customer acquisition cost analysis

    SECURITY: Tenant isolation enforced via tenant_id.
#}

with sessions as (
    select
        id as session_id,
        tenant_id,
        session_id as raw_session_id,
        landing_page_url,
        landing_utm_source,
        landing_utm_medium,
        landing_utm_campaign,
        session_start,
        session_end,
        session_duration_seconds,
        pages_viewed,
        products_viewed,
        collections_viewed,
        searches_performed,
        cart_viewed,
        checkout_started,
        checkout_completed,
        payment_submitted,
        linked_order_id
    from {{ ref('customer_sessions') }}
    where tenant_id is not null

    {% if is_incremental() %}
        and session_start >= (
            select coalesce(
                max(last_session_at) - interval '3 days',
                '2020-01-01'::timestamp
            )
            from {{ this }}
        )
    {% endif %}
),

-- Extract a visitor identifier from the session's landing page URL
-- The pixel generates a visitor_id per browser; it's stored in event_data
-- For now, group by tenant + landing page domain + first session UTM as a proxy
visitor_sessions as (
    select
        *,
        -- Use raw_session_id prefix as visitor proxy (pixel generates session_id
        -- with a visitor component when available)
        split_part(raw_session_id, '-', 1) || '-' ||
        split_part(raw_session_id, '-', 2) as visitor_key
    from sessions
),

journey_aggregation as (
    select
        md5(tenant_id || '|' || visitor_key) as id,
        tenant_id,
        visitor_key,

        -- Timeline
        min(session_start) as first_visit_at,
        max(session_end) as last_session_at,

        -- Volume
        count(*) as total_sessions,
        sum(pages_viewed) as total_page_views,
        sum(products_viewed) as total_products_viewed,
        sum(collections_viewed) as total_collections_viewed,
        sum(searches_performed) as total_searches,

        -- Funnel progression (any session)
        bool_or(cart_viewed) as ever_viewed_cart,
        bool_or(checkout_started) as ever_started_checkout,
        bool_or(checkout_completed) as ever_completed_checkout,
        bool_or(payment_submitted) as ever_submitted_payment,

        -- Conversion
        count(distinct linked_order_id) filter (
            where linked_order_id is not null
        ) as total_orders,
        bool_or(linked_order_id is not null) as has_converted,

        -- First-touch attribution
        (array_agg(landing_utm_source order by session_start asc)
            filter (where landing_utm_source is not null))[1] as first_touch_utm_source,
        (array_agg(landing_utm_medium order by session_start asc)
            filter (where landing_utm_medium is not null))[1] as first_touch_utm_medium,
        (array_agg(landing_utm_campaign order by session_start asc)
            filter (where landing_utm_campaign is not null))[1] as first_touch_utm_campaign,

        -- Last-touch attribution
        (array_agg(landing_utm_source order by session_start desc)
            filter (where landing_utm_source is not null))[1] as last_touch_utm_source,
        (array_agg(landing_utm_medium order by session_start desc)
            filter (where landing_utm_medium is not null))[1] as last_touch_utm_medium,
        (array_agg(landing_utm_campaign order by session_start desc)
            filter (where landing_utm_campaign is not null))[1] as last_touch_utm_campaign,

        -- Engagement metrics
        avg(session_duration_seconds) as avg_session_duration_seconds,
        max(session_duration_seconds) as max_session_duration_seconds

    from visitor_sessions
    group by tenant_id, visitor_key
)

select
    id,
    tenant_id,
    visitor_key,
    first_visit_at,
    last_session_at,
    total_sessions,
    total_page_views,
    total_products_viewed,
    total_collections_viewed,
    total_searches,
    ever_viewed_cart,
    ever_started_checkout,
    ever_completed_checkout,
    ever_submitted_payment,
    total_orders,
    has_converted,
    first_touch_utm_source,
    first_touch_utm_medium,
    first_touch_utm_campaign,
    last_touch_utm_source,
    last_touch_utm_medium,
    last_touch_utm_campaign,
    round(avg_session_duration_seconds::numeric, 2) as avg_session_duration_seconds,
    max_session_duration_seconds,
    current_timestamp as dbt_updated_at
from journey_aggregation
