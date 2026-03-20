{{
    config(
        materialized='view',
        schema='analytics'
    )
}}

{#
    Session-Based Multi-Touch Attribution Model

    Unlike multi_touch_linear.sql (which approximates multi-touch using
    campaign activity windows), this model uses actual session data from
    the Web Pixel to attribute revenue across all sessions a visitor had
    before converting.

    APPROACH:
      1. Find all converted sessions (checkout_completed = true with an order)
      2. For each conversion, find all prior sessions for the same visitor
         within a configurable lookback window (default 30 days)
      3. Distribute attribution credit using linear weighting (equal credit
         per session) across all touchpoint sessions

    This model enables true multi-touch attribution based on observed
    customer behavior rather than campaign-window approximation.

    SECURITY: Tenant isolation enforced via tenant_id.
#}

{% set lookback_days = var('session_attribution_lookback_days', 30) %}

with converted_sessions as (
    -- Sessions that resulted in a purchase
    select
        id as converting_session_id,
        tenant_id,
        session_id,
        linked_order_id as order_id,
        session_start as conversion_session_start,
        landing_utm_source,
        landing_utm_medium,
        landing_utm_campaign,
        landing_utm_term,
        landing_utm_content,
        -- Use session_id prefix as visitor key (same logic as customer_journeys)
        split_part(session_id, '-', 1) || '-' ||
        split_part(session_id, '-', 2) as visitor_key
    from {{ ref('customer_sessions') }}
    where linked_order_id is not null
        and checkout_completed = true
),

-- Find all sessions for the same visitor within the lookback window
touchpoint_sessions as (
    select
        cs.converting_session_id,
        cs.order_id,
        cs.tenant_id,
        cs.visitor_key,
        cs.conversion_session_start,
        s.id as touchpoint_session_id,
        s.session_id as touchpoint_raw_session_id,
        s.session_start as touchpoint_session_start,
        s.landing_utm_source as touchpoint_utm_source,
        s.landing_utm_medium as touchpoint_utm_medium,
        s.landing_utm_campaign as touchpoint_utm_campaign,
        s.landing_utm_term as touchpoint_utm_term,
        s.landing_utm_content as touchpoint_utm_content,
        s.landing_page_url as touchpoint_landing_page,
        s.pages_viewed as touchpoint_pages_viewed,
        s.products_viewed as touchpoint_products_viewed,
        s.checkout_started as touchpoint_checkout_started,
        s.checkout_completed as touchpoint_checkout_completed
    from converted_sessions cs
    inner join {{ ref('customer_sessions') }} s
        on cs.tenant_id = s.tenant_id
        and (
            split_part(s.session_id, '-', 1) || '-' ||
            split_part(s.session_id, '-', 2)
        ) = cs.visitor_key
        and s.session_start <= cs.conversion_session_start
        and s.session_start >= cs.conversion_session_start - interval '{{ lookback_days }} days'
),

-- Count touchpoints per conversion for credit distribution
touchpoint_counts as (
    select
        converting_session_id,
        order_id,
        tenant_id,
        count(*) as touchpoint_count
    from touchpoint_sessions
    group by converting_session_id, order_id, tenant_id
),

-- Join to orders to get revenue for attribution
order_revenue as (
    select
        order_id,
        tenant_id,
        total_price as revenue,
        currency
    from {{ ref('stg_shopify_orders') }}
    where order_id is not null
)

select
    -- Deterministic surrogate key
    md5(concat(
        ts.order_id, '|',
        ts.touchpoint_session_id, '|',
        ts.tenant_id, '|',
        'multi_touch_session'
    )) as id,

    ts.order_id,
    ts.tenant_id,
    ts.visitor_key,

    -- Conversion info
    ts.conversion_session_start,
    ts.converting_session_id,

    -- Touchpoint info
    ts.touchpoint_session_id,
    ts.touchpoint_raw_session_id,
    ts.touchpoint_session_start,
    ts.touchpoint_landing_page,
    ts.touchpoint_pages_viewed,
    ts.touchpoint_products_viewed,
    ts.touchpoint_checkout_started,
    ts.touchpoint_checkout_completed,

    -- UTM attribution from this touchpoint
    ts.touchpoint_utm_source,
    ts.touchpoint_utm_medium,
    ts.touchpoint_utm_campaign,
    ts.touchpoint_utm_term,
    ts.touchpoint_utm_content,

    -- Revenue attribution (linear — equal credit per touchpoint)
    or_rev.revenue as total_order_revenue,
    or_rev.currency,
    round(
        (or_rev.revenue / nullif(tc.touchpoint_count, 0))::numeric,
        4
    ) as attributed_revenue,

    tc.touchpoint_count as total_touchpoints,
    round(
        (1.0 / nullif(tc.touchpoint_count, 0))::numeric,
        4
    ) as attribution_weight,

    -- Position in the journey (1 = first touch, N = converting touch)
    row_number() over (
        partition by ts.order_id, ts.tenant_id
        order by ts.touchpoint_session_start asc
    ) as touchpoint_position,

    case
        when ts.touchpoint_session_id = ts.converting_session_id then 'converting'
        when row_number() over (
            partition by ts.order_id, ts.tenant_id
            order by ts.touchpoint_session_start asc
        ) = 1 then 'first_touch'
        else 'assist'
    end as touchpoint_role,

    'multi_touch_session' as attribution_model,
    current_timestamp as dbt_updated_at

from touchpoint_sessions ts
inner join touchpoint_counts tc
    on ts.converting_session_id = tc.converting_session_id
    and ts.order_id = tc.order_id
    and ts.tenant_id = tc.tenant_id
left join order_revenue or_rev
    on ts.order_id = or_rev.order_id
    and ts.tenant_id = or_rev.tenant_id
