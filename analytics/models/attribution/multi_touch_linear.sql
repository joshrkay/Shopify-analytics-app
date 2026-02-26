{{
    config(
        materialized='view',
        schema='analytics'
    )
}}

-- Multi-Touch Linear Attribution Model
--
-- Assigns equal attribution credit to all campaigns that ran within a lookback window
-- before each order, weighted by their contribution to the customer journey.
--
-- APPROACH:
-- Since session-level multi-touch tracking is not yet available, this model uses
-- a campaign-window approach:
--   1. For each order with UTM parameters, identify the attributed campaign (last-click)
--   2. Find all OTHER campaigns for the same tenant that ran within the 7-day
--      lookback window prior to the order date
--   3. Distribute attribution credit equally across all matched campaigns
--      (1/N credit per campaign, where N = number of campaigns in window)
--
-- LIMITATIONS:
-- - Without session tracking, multi-touch is approximated using campaign activity windows
-- - True multi-touch requires session-level click data (future work)
-- - Single campaign in window → same result as last-click
--
-- SECURITY: Tenant isolation enforced via tenant_id.

with last_click_base as (
    -- Start from last-click model for orders with attribution
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

-- Find all campaigns active in the 7-day window before each order
campaigns_in_window as (
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
        c.conversions as campaign_conversions
    from last_click_base o
    inner join {{ ref('campaign_performance') }} c
        on o.tenant_id = c.tenant_id
        and c.date between
            date(o.order_created_at) - interval '7 days'
            and date(o.order_created_at)
        and c.spend > 0  -- Only active campaigns (had spend in window)
),

-- Count campaigns per order for equal credit distribution
campaign_counts as (
    select
        order_id,
        tenant_id,
        count(distinct campaign_id) as campaign_count
    from campaigns_in_window
    group by order_id, tenant_id
),

-- Join campaign window data to base orders
attributed_linear as (
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

        -- Assigned campaign for this attribution row
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

        -- Revenue allocated equally across all campaigns in window
        o.revenue as total_order_revenue,
        round(
            (o.revenue / nullif(cc.campaign_count, 0))::numeric,
            4
        ) as attributed_revenue,

        cc.campaign_count as total_campaigns_in_window,

        -- Attribution fraction
        round(
            (1.0 / nullif(cc.campaign_count, 0))::numeric,
            4
        ) as attribution_weight

    from last_click_base o
    inner join campaigns_in_window cw
        on o.order_id = cw.order_id
        and o.tenant_id = cw.tenant_id
    inner join campaign_counts cc
        on o.order_id = cc.order_id
        and o.tenant_id = cc.tenant_id
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
        o.revenue as total_order_revenue,
        o.revenue as attributed_revenue,
        1 as total_campaigns_in_window,
        1.0 as attribution_weight
    from last_click_base o
    where o.order_id not in (
        select distinct order_id from attributed_linear
    )
)

select
    -- Surrogate key: deterministic hash of order_id + campaign_id + model
    md5(concat(
        order_id, '|',
        coalesce(campaign_id, 'none'), '|',
        tenant_id, '|',
        'multi_touch_linear'
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

    attributed_revenue,
    attribution_weight,
    total_campaigns_in_window,

    'multi_touch_linear' as attribution_model,
    'attributed' as attribution_status,

    tenant_id,
    current_timestamp as dbt_updated_at

from attributed_linear

union all

select
    md5(concat(
        order_id, '|',
        coalesce(campaign_id, 'none'), '|',
        tenant_id, '|',
        'multi_touch_linear'
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

    attributed_revenue,
    attribution_weight,
    total_campaigns_in_window,

    'multi_touch_linear' as attribution_model,
    'attributed' as attribution_status,

    tenant_id,
    current_timestamp as dbt_updated_at

from orders_without_window
