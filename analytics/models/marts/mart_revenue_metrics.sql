{{
    config(
        materialized='table',
        schema='marts',
        tags=['marts', 'revenue', 'metrics']
    )
}}

-- Revenue Metrics Mart with Flexible Date Ranges & Period Comparisons
--
-- This mart provides revenue metrics across:
-- - All date range types (daily, weekly, monthly, quarterly, yearly, last_N_days)
-- - Period-over-period comparisons (current vs prior period)
-- - Multi-currency support
-- - Tenant isolation
--
-- Usage:
--   SELECT * FROM mart_revenue_metrics
--   WHERE period_type = 'last_30_days'
--     AND period_end = current_date
--     AND tenant_id = 'your_tenant';

with date_ranges as (
    select * from {{ ref('dim_date_ranges') }}
),

daily_revenue as (
    select
        tenant_id,
        currency,
        date_trunc('day', revenue_date)::date as date,
        sum(case when revenue_type = 'gross_revenue' then gross_revenue else 0 end) as gross_revenue,
        sum(refund_amount) as refund_amount,
        sum(cancellation_amount) as cancellation_amount,
        sum(net_revenue) as net_revenue,
        count(distinct case when revenue_type = 'gross_revenue' then order_id end) as order_count
    from {{ ref('fct_revenue') }}
    where tenant_id is not null
    group by 1, 2, 3
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

        rev.tenant_id,
        rev.currency,

        -- Current period metrics
        sum(rev.gross_revenue) as gross_revenue,
        sum(rev.refund_amount) as refund_amount,
        sum(rev.cancellation_amount) as cancellation_amount,
        sum(rev.net_revenue) as net_revenue,
        sum(rev.order_count) as order_count,

        -- Averages
        avg(rev.gross_revenue) as avg_daily_gross_revenue,
        avg(rev.net_revenue) as avg_daily_net_revenue,

        -- AOV
        case
            when sum(rev.order_count) > 0
            then sum(rev.net_revenue) / sum(rev.order_count)
            else 0
        end as aov

    from date_ranges dr
    cross join (select distinct tenant_id, currency from daily_revenue) tenants
    left join daily_revenue rev
        on rev.tenant_id = tenants.tenant_id
        and rev.currency = tenants.currency
        and rev.date between dr.period_start and dr.period_end
    group by 1, 2, 3, 4, 5, 6, 7, 8
),

-- Aggregate to all date ranges (PRIOR period for comparison)
prior_period_metrics as (
    select
        dr.date_range_id,
        rev.tenant_id,
        rev.currency,

        -- Prior period metrics
        sum(rev.gross_revenue) as prior_gross_revenue,
        sum(rev.refund_amount) as prior_refund_amount,
        sum(rev.cancellation_amount) as prior_cancellation_amount,
        sum(rev.net_revenue) as prior_net_revenue,
        sum(rev.order_count) as prior_order_count,

        -- Averages
        avg(rev.gross_revenue) as prior_avg_daily_gross_revenue,
        avg(rev.net_revenue) as prior_avg_daily_net_revenue,

        -- AOV
        case
            when sum(rev.order_count) > 0
            then sum(rev.net_revenue) / sum(rev.order_count)
            else 0
        end as prior_aov

    from date_ranges dr
    cross join (select distinct tenant_id, currency from daily_revenue) tenants
    left join daily_revenue rev
        on rev.tenant_id = tenants.tenant_id
        and rev.currency = tenants.currency
        and rev.date between dr.prior_period_start and dr.prior_period_end
    group by 1, 2, 3
),

-- Join current and prior periods
combined as (
    select
        curr.*,
        prior.prior_gross_revenue,
        prior.prior_refund_amount,
        prior.prior_cancellation_amount,
        prior.prior_net_revenue,
        prior.prior_order_count,
        prior.prior_avg_daily_gross_revenue,
        prior.prior_avg_daily_net_revenue,
        prior.prior_aov
    from current_period_metrics curr
    left join prior_period_metrics prior
        on curr.date_range_id = prior.date_range_id
        and curr.tenant_id = prior.tenant_id
        and curr.currency = prior.currency
)

select
    date_range_id,
    tenant_id,
    currency,
    period_type,
    period_start,
    period_end,
    period_days,
    comparison_type,

    -- CURRENT PERIOD METRICS
    gross_revenue,
    refund_amount,
    cancellation_amount,
    net_revenue,
    order_count,
    avg_daily_gross_revenue,
    avg_daily_net_revenue,
    aov,

    -- PRIOR PERIOD METRICS
    prior_gross_revenue,
    prior_refund_amount,
    prior_cancellation_amount,
    prior_net_revenue,
    prior_order_count,
    prior_avg_daily_gross_revenue,
    prior_avg_daily_net_revenue,
    prior_aov,

    -- PERIOD-OVER-PERIOD CHANGES (Absolute)
    (gross_revenue - prior_gross_revenue) as gross_revenue_change,
    (net_revenue - prior_net_revenue) as net_revenue_change,
    (order_count - prior_order_count) as order_count_change,
    (aov - prior_aov) as aov_change,

    -- PERIOD-OVER-PERIOD CHANGES (Percentage)
    case
        when prior_gross_revenue > 0 then
            round(((gross_revenue - prior_gross_revenue) / prior_gross_revenue * 100)::numeric, 2)
        else 0
    end as gross_revenue_change_pct,

    case
        when prior_net_revenue > 0 then
            round(((net_revenue - prior_net_revenue) / prior_net_revenue * 100)::numeric, 2)
        else 0
    end as net_revenue_change_pct,

    case
        when prior_order_count > 0 then
            round(((order_count::numeric - prior_order_count) / prior_order_count * 100)::numeric, 2)
        else 0
    end as order_count_change_pct,

    case
        when prior_aov > 0 then
            round(((aov - prior_aov) / prior_aov * 100)::numeric, 2)
        else 0
    end as aov_change_pct,

    -- METADATA
    current_timestamp as dbt_updated_at

from combined
where tenant_id is not null
    -- Only include periods with data in current OR prior period
    and (gross_revenue > 0 or prior_gross_revenue > 0
         or order_count > 0 or prior_order_count > 0)

-- Order by most recent periods first
order by tenant_id, currency, period_end desc, period_type
