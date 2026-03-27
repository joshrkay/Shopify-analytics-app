{{
    config(
        materialized='view',
        schema='analytics'
    )
}}

{#
    Funnel Metrics — daily conversion funnel from pixel events.

    Tracks the customer journey funnel:
    page_views → product_views → cart_views → checkout_started → checkout_completed

    Broken down by:
    - tenant_id (multi-tenant isolation)
    - date (daily granularity)
    - utm_source / utm_medium (channel attribution)

    Enables:
    - Identifying drop-off points in the purchase funnel
    - Comparing funnel performance across marketing channels
    - Tracking conversion rate improvements over time

    SECURITY: Tenant isolation enforced via tenant_id.
#}

with sessions as (
    select
        tenant_id,
        date(session_start) as session_date,
        coalesce(utm_source, 'direct') as utm_source,
        coalesce(utm_medium, 'none') as utm_medium,
        session_id,
        pages_viewed,
        products_viewed,
        cart_viewed,
        checkout_started,
        checkout_completed
    from {{ ref('customer_sessions') }}
    where session_start is not null
)

select
    -- Primary key
    md5(concat(
        tenant_id, '|',
        session_date::text, '|',
        utm_source, '|',
        utm_medium
    )) as id,

    tenant_id,
    session_date,
    utm_source,
    utm_medium,

    -- Funnel stage counts (unique sessions)
    count(distinct session_id) as total_sessions,
    count(distinct session_id) filter (where pages_viewed > 0) as sessions_with_page_view,
    count(distinct session_id) filter (where products_viewed > 0) as sessions_with_product_view,
    count(distinct session_id) filter (where cart_viewed) as sessions_with_cart_view,
    count(distinct session_id) filter (where checkout_started) as sessions_with_checkout_start,
    count(distinct session_id) filter (where checkout_completed) as sessions_with_purchase,

    -- Conversion rates (as percentages)
    case
        when count(distinct session_id) > 0
        then round(100.0 * count(distinct session_id) filter (where products_viewed > 0)
            / count(distinct session_id), 2)
        else 0
    end as pct_view_to_product,

    case
        when count(distinct session_id) filter (where products_viewed > 0) > 0
        then round(100.0 * count(distinct session_id) filter (where cart_viewed)
            / count(distinct session_id) filter (where products_viewed > 0), 2)
        else 0
    end as pct_product_to_cart,

    case
        when count(distinct session_id) filter (where cart_viewed) > 0
        then round(100.0 * count(distinct session_id) filter (where checkout_started)
            / count(distinct session_id) filter (where cart_viewed), 2)
        else 0
    end as pct_cart_to_checkout,

    case
        when count(distinct session_id) filter (where checkout_started) > 0
        then round(100.0 * count(distinct session_id) filter (where checkout_completed)
            / count(distinct session_id) filter (where checkout_started), 2)
        else 0
    end as pct_checkout_to_purchase,

    -- Overall conversion rate (session → purchase)
    case
        when count(distinct session_id) > 0
        then round(100.0 * count(distinct session_id) filter (where checkout_completed)
            / count(distinct session_id), 2)
        else 0
    end as overall_conversion_rate,

    -- Audit
    current_timestamp as dbt_updated_at

from sessions
group by tenant_id, session_date, utm_source, utm_medium
