{{
    config(
        materialized='table',
        schema='marts',
        tags=['marts', 'marketing', 'metrics']
    )
}}

-- Marketing Metrics Mart (ROAS + CAC) with Flexible Date Ranges
--
-- This mart combines ROAS and CAC metrics with:
-- - All date range types (daily, last_30_days, monthly, etc.)
-- - Period-over-period comparisons
-- - Platform-level breakdown
-- - Multi-currency support
--
-- Usage:
--   SELECT * FROM mart_marketing_metrics
--   WHERE period_type = 'last_30_days'
--     AND period_end = current_date
--     AND platform = 'meta_ads';

with date_ranges as (
    select * from {{ ref('dim_date_ranges') }}
),

-- Daily ROAS metrics
daily_roas as (
    select
        tenant_id,
        platform,
        currency,
        campaign_id,
        date_trunc('day', period_start)::date as date,
        sum(total_spend) as spend,
        sum(order_count) as orders,
        sum(total_gross_revenue) as gross_revenue,
        sum(total_net_revenue) as net_revenue
    from {{ ref('fct_roas') }}
    where period_type = 'daily'
        and tenant_id is not null
    group by 1, 2, 3, 4, 5
),

-- Daily CAC metrics
daily_cac as (
    select
        tenant_id,
        platform,
        currency,
        campaign_id,
        date_trunc('day', period_start)::date as date,
        sum(new_customers) as new_customers,
        sum(net_new_customers) as net_new_customers,
        sum(total_spend) as spend,
        sum(first_order_revenue_total) as first_order_revenue
    from {{ ref('fct_cac') }}
    where period_type = 'daily'
        and tenant_id is not null
    group by 1, 2, 3, 4, 5
),

-- Combine daily ROAS + CAC
daily_combined as (
    select
        coalesce(r.tenant_id, c.tenant_id) as tenant_id,
        coalesce(r.platform, c.platform) as platform,
        coalesce(r.currency, c.currency) as currency,
        coalesce(r.campaign_id, c.campaign_id) as campaign_id,
        coalesce(r.date, c.date) as date,

        -- ROAS metrics
        coalesce(r.spend, 0) as roas_spend,
        coalesce(r.orders, 0) as orders,
        coalesce(r.gross_revenue, 0) as gross_revenue,
        coalesce(r.net_revenue, 0) as net_revenue,

        -- CAC metrics
        coalesce(c.spend, 0) as cac_spend,
        coalesce(c.new_customers, 0) as new_customers,
        coalesce(c.net_new_customers, 0) as net_new_customers,
        coalesce(c.first_order_revenue, 0) as first_order_revenue,

        -- Use max spend (should be same from both tables)
        greatest(coalesce(r.spend, 0), coalesce(c.spend, 0)) as total_spend

    from daily_roas r
    full outer join daily_cac c
        on r.tenant_id = c.tenant_id
        and r.platform = c.platform
        and r.currency = c.currency
        and coalesce(r.campaign_id, '') = coalesce(c.campaign_id, '')
        and r.date = c.date
),

-- Aggregate to all date ranges (CURRENT period)
current_period_metrics as (
    select
        dr.date_range_id,
        dr.period_type,
        dr.period_start,
        dr.period_end,
        dr.period_days,
        dr.comparison_type,

        m.tenant_id,
        m.platform,
        m.currency,
        m.campaign_id,

        -- Spend
        sum(m.total_spend) as spend,

        -- ROAS metrics
        sum(m.orders) as orders,
        sum(m.gross_revenue) as gross_revenue,
        sum(m.net_revenue) as net_revenue,

        -- ROAS calculations
        case
            when sum(m.total_spend) > 0
            then round((sum(m.gross_revenue) / sum(m.total_spend))::numeric, 2)
            else 0
        end as gross_roas,

        case
            when sum(m.total_spend) > 0
            then round((sum(m.net_revenue) / sum(m.total_spend))::numeric, 2)
            else 0
        end as net_roas,

        -- CAC metrics
        sum(m.new_customers) as new_customers,
        sum(m.net_new_customers) as net_new_customers,
        sum(m.first_order_revenue) as first_order_revenue,

        -- CAC calculations
        case
            when sum(m.new_customers) > 0
            then round((sum(m.total_spend) / sum(m.new_customers))::numeric, 2)
            else 0
        end as cac,

        case
            when sum(m.net_new_customers) > 0
            then round((sum(m.total_spend) / sum(m.net_new_customers))::numeric, 2)
            else 0
        end as ncac,

        -- Customer retention rate
        case
            when sum(m.new_customers) > 0
            then round((sum(m.net_new_customers)::numeric / sum(m.new_customers)::numeric * 100)::numeric, 2)
            else 0
        end as customer_retention_rate_pct

    from date_ranges dr
    cross join (
        select distinct tenant_id, platform, currency, campaign_id
        from daily_combined
    ) tenants
    left join daily_combined m
        on m.tenant_id = tenants.tenant_id
        and m.platform = tenants.platform
        and m.currency = tenants.currency
        and coalesce(m.campaign_id, '') = coalesce(tenants.campaign_id, '')
        and m.date between dr.period_start and dr.period_end
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
),

-- Aggregate to all date ranges (PRIOR period)
prior_period_metrics as (
    select
        dr.date_range_id,
        m.tenant_id,
        m.platform,
        m.currency,
        m.campaign_id,

        -- Spend
        sum(m.total_spend) as prior_spend,

        -- ROAS metrics
        sum(m.orders) as prior_orders,
        sum(m.gross_revenue) as prior_gross_revenue,
        sum(m.net_revenue) as prior_net_revenue,

        -- ROAS calculations
        case
            when sum(m.total_spend) > 0
            then round((sum(m.gross_revenue) / sum(m.total_spend))::numeric, 2)
            else 0
        end as prior_gross_roas,

        case
            when sum(m.total_spend) > 0
            then round((sum(m.net_revenue) / sum(m.total_spend))::numeric, 2)
            else 0
        end as prior_net_roas,

        -- CAC metrics
        sum(m.new_customers) as prior_new_customers,
        sum(m.net_new_customers) as prior_net_new_customers,

        -- CAC calculations
        case
            when sum(m.new_customers) > 0
            then round((sum(m.total_spend) / sum(m.new_customers))::numeric, 2)
            else 0
        end as prior_cac,

        case
            when sum(m.net_new_customers) > 0
            then round((sum(m.total_spend) / sum(m.net_new_customers))::numeric, 2)
            else 0
        end as prior_ncac

    from date_ranges dr
    cross join (
        select distinct tenant_id, platform, currency, campaign_id
        from daily_combined
    ) tenants
    left join daily_combined m
        on m.tenant_id = tenants.tenant_id
        and m.platform = tenants.platform
        and m.currency = tenants.currency
        and coalesce(m.campaign_id, '') = coalesce(tenants.campaign_id, '')
        and m.date between dr.prior_period_start and dr.prior_period_end
    group by 1, 2, 3, 4, 5
),

-- Join current and prior
combined as (
    select
        curr.*,
        prior.prior_spend,
        prior.prior_orders,
        prior.prior_gross_revenue,
        prior.prior_net_revenue,
        prior.prior_gross_roas,
        prior.prior_net_roas,
        prior.prior_new_customers,
        prior.prior_net_new_customers,
        prior.prior_cac,
        prior.prior_ncac
    from current_period_metrics curr
    left join prior_period_metrics prior
        on curr.date_range_id = prior.date_range_id
        and curr.tenant_id = prior.tenant_id
        and curr.platform = prior.platform
        and curr.currency = prior.currency
        and coalesce(curr.campaign_id, '') = coalesce(prior.campaign_id, '')
)

select
    date_range_id,
    tenant_id,
    platform,
    currency,
    campaign_id,
    period_type,
    period_start,
    period_end,
    period_days,
    comparison_type,

    -- CURRENT PERIOD METRICS
    spend,
    orders,
    gross_revenue,
    net_revenue,
    gross_roas,
    net_roas,
    new_customers,
    net_new_customers,
    cac,
    ncac,
    customer_retention_rate_pct,

    -- PRIOR PERIOD METRICS
    prior_spend,
    prior_orders,
    prior_gross_revenue,
    prior_net_revenue,
    prior_gross_roas,
    prior_net_roas,
    prior_new_customers,
    prior_net_new_customers,
    prior_cac,
    prior_ncac,

    -- PERIOD-OVER-PERIOD CHANGES (Absolute)
    (spend - prior_spend) as spend_change,
    (orders - prior_orders) as orders_change,
    (gross_roas - prior_gross_roas) as gross_roas_change,
    (net_roas - prior_net_roas) as net_roas_change,
    (cac - prior_cac) as cac_change,
    (ncac - prior_ncac) as ncac_change,
    (new_customers - prior_new_customers) as new_customers_change,

    -- PERIOD-OVER-PERIOD CHANGES (Percentage)
    case
        when prior_spend > 0 then
            round(((spend - prior_spend) / prior_spend * 100)::numeric, 2)
        else 0
    end as spend_change_pct,

    case
        when prior_orders > 0 then
            round(((orders::numeric - prior_orders) / prior_orders * 100)::numeric, 2)
        else 0
    end as orders_change_pct,

    case
        when prior_gross_roas > 0 then
            round(((gross_roas - prior_gross_roas) / prior_gross_roas * 100)::numeric, 2)
        else 0
    end as gross_roas_change_pct,

    case
        when prior_net_roas > 0 then
            round(((net_roas - prior_net_roas) / prior_net_roas * 100)::numeric, 2)
        else 0
    end as net_roas_change_pct,

    case
        when prior_cac > 0 then
            round(((cac - prior_cac) / prior_cac * 100)::numeric, 2)
        else 0
    end as cac_change_pct,

    -- METADATA
    current_timestamp as dbt_updated_at

from combined
where tenant_id is not null
    -- Only include periods with data
    and (spend > 0 or prior_spend > 0
         or orders > 0 or prior_orders > 0
         or new_customers > 0 or prior_new_customers > 0)

order by tenant_id, platform, currency, period_end desc, period_type
