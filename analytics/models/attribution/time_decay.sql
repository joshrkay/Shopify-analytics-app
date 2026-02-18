{{
    config(
        materialized='view',
        schema='analytics'
    )
}}

-- Time Decay Attribution Model
--
-- Gives more attribution credit to campaigns that ran closer to the order date.
-- Uses an exponential decay function: weight = e^(-decay_rate * days_before_order)
--
-- APPROACH:
-- 1. For each attributed order, find all campaigns active in a 7-day lookback window
-- 2. Compute a decay weight for each campaign based on days before the order
-- 3. Normalize weights so they sum to 1.0 across all campaigns for that order
-- 4. Attribute revenue proportionally to normalized weights
--
-- DECAY RATE: 0.5 (configurable) — campaigns 7 days before order get ~3% weight
-- vs campaigns on the order date that get 100% weight.
--
-- FORMULA:
--   raw_weight = exp(-0.5 * days_before_order)
--   normalized_weight = raw_weight / sum(raw_weights_for_order)
--   attributed_revenue = order_revenue * normalized_weight
--
-- SECURITY: Tenant isolation enforced via tenant_id.

with last_click_base as (
    select
        order_id,
        order_name,
        order_number,
        customer_key,
        order_created_at,
        revenue,
        currency,
        utm_source,
        utm_medium,
        utm_campaign,
        utm_term,
        utm_content,
        campaign_fact_id,
        ad_account_id,
        campaign_id,
        campaign_name,
        platform,
        campaign_performance_date,
        campaign_spend,
        campaign_clicks,
        campaign_impressions,
        campaign_conversions,
        attribution_status,
        tenant_id
    from {{ ref('last_click') }}
    where attribution_status = 'attributed'
),

-- Find campaigns in lookback window with their temporal distance from order
campaigns_with_decay as (
    select
        o.order_id,
        o.tenant_id,
        o.order_created_at,
        c.id as campaign_fact_id,
        c.campaign_id,
        c.campaign_name,
        c.source_platform as platform,
        c.ad_account_id,
        c.date as campaign_performance_date,
        c.spend as campaign_spend,
        c.clicks as campaign_clicks,
        c.impressions as campaign_impressions,
        c.conversions as campaign_conversions,

        -- Days before order (0 = same day, 7 = 7 days before)
        date_part(
            'day',
            date(o.order_created_at) - c.date
        ) as days_before_order,

        -- Exponential decay weight: closer to order date = higher weight
        -- decay_rate = 0.5; campaign on day-0 gets weight 1.0
        -- campaign on day-7 gets weight exp(-0.5*7) ≈ 0.03
        exp(-0.5 * date_part('day', date(o.order_created_at) - c.date)) as raw_decay_weight

    from last_click_base o
    inner join {{ ref('campaign_performance') }} c
        on o.tenant_id = c.tenant_id
        and c.date between
            date(o.order_created_at) - interval '7 days'
            and date(o.order_created_at)
        and c.spend > 0
),

-- Sum raw weights per order for normalization
weight_totals as (
    select
        order_id,
        tenant_id,
        sum(raw_decay_weight) as total_raw_weight,
        count(distinct campaign_id) as campaign_count
    from campaigns_with_decay
    group by order_id, tenant_id
),

-- Compute normalized weights and attributed revenue
attributed_time_decay as (
    select
        o.order_id,
        o.order_name,
        o.order_number,
        o.customer_key,
        o.order_created_at,
        o.currency,
        o.utm_source,
        o.utm_medium,
        o.utm_campaign,
        o.utm_term,
        o.utm_content,
        o.tenant_id,

        cw.campaign_fact_id,
        cw.ad_account_id,
        cw.campaign_id,
        cw.campaign_name,
        cw.platform,
        cw.campaign_performance_date,
        cw.campaign_spend,
        cw.campaign_clicks,
        cw.campaign_impressions,
        cw.campaign_conversions,
        cw.days_before_order,

        o.revenue as total_order_revenue,

        -- Normalized weight: this campaign's share of total decay weight
        round(
            (cw.raw_decay_weight / nullif(wt.total_raw_weight, 0))::numeric,
            4
        ) as attribution_weight,

        -- Revenue attributed to this campaign
        round(
            (o.revenue * cw.raw_decay_weight / nullif(wt.total_raw_weight, 0))::numeric,
            4
        ) as attributed_revenue,

        wt.campaign_count as total_campaigns_in_window

    from last_click_base o
    inner join campaigns_with_decay cw
        on o.order_id = cw.order_id
        and o.tenant_id = cw.tenant_id
    inner join weight_totals wt
        on o.order_id = wt.order_id
        and o.tenant_id = wt.tenant_id
),

-- Fall back to last-click for orders with no campaigns in window
orders_without_window as (
    select
        o.order_id,
        o.order_name,
        o.order_number,
        o.customer_key,
        o.order_created_at,
        o.currency,
        o.utm_source,
        o.utm_medium,
        o.utm_campaign,
        o.utm_term,
        o.utm_content,
        o.tenant_id,
        o.campaign_fact_id,
        o.ad_account_id,
        o.campaign_id,
        o.campaign_name,
        o.platform,
        o.campaign_performance_date,
        o.campaign_spend,
        o.campaign_clicks,
        o.campaign_impressions,
        o.campaign_conversions,
        0 as days_before_order,
        o.revenue as total_order_revenue,
        1.0 as attribution_weight,
        o.revenue as attributed_revenue,
        1 as total_campaigns_in_window
    from last_click_base o
    where o.order_id not in (
        select distinct order_id from attributed_time_decay
    )
)

select
    md5(concat(
        order_id, '|',
        coalesce(campaign_id, 'none'), '|',
        tenant_id, '|',
        'time_decay'
    )) as id,

    order_id,
    order_name,
    order_number,
    customer_key,
    order_created_at,
    total_order_revenue as revenue,
    currency,

    utm_source,
    utm_medium,
    utm_campaign,
    utm_term,
    utm_content,

    campaign_fact_id,
    ad_account_id,
    campaign_id,
    campaign_name,
    platform,
    campaign_performance_date,
    campaign_spend,
    campaign_clicks,
    campaign_impressions,
    campaign_conversions,

    days_before_order,
    attributed_revenue,
    attribution_weight,
    total_campaigns_in_window,

    'time_decay' as attribution_model,
    'attributed' as attribution_status,

    tenant_id,
    current_timestamp as dbt_updated_at

from attributed_time_decay

union all

select
    md5(concat(
        order_id, '|',
        coalesce(campaign_id, 'none'), '|',
        tenant_id, '|',
        'time_decay'
    )) as id,

    order_id,
    order_name,
    order_number,
    customer_key,
    order_created_at,
    total_order_revenue as revenue,
    currency,

    utm_source,
    utm_medium,
    utm_campaign,
    utm_term,
    utm_content,

    campaign_fact_id,
    ad_account_id,
    campaign_id,
    campaign_name,
    platform,
    campaign_performance_date,
    campaign_spend,
    campaign_clicks,
    campaign_impressions,
    campaign_conversions,

    days_before_order,
    attributed_revenue,
    attribution_weight,
    total_campaigns_in_window,

    'time_decay' as attribution_model,
    'attributed' as attribution_status,

    tenant_id,
    current_timestamp as dbt_updated_at

from orders_without_window
