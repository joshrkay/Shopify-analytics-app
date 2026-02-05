-- Reconciliation test: Shopify Order Revenue
--
-- Validates that revenue totals in fact_orders_v1 match the staging
-- source (stg_shopify_orders) within a configurable tolerance.
--
-- Compares revenue_gross (= total_price) and revenue_net (= subtotal_price)
-- for the date range present in the canonical table, applying the same
-- filters that fact_orders_v1 uses when selecting from staging.
--
-- Tolerance: var('reconciliation_tolerance_pct', 1.0)  →  ±1 % by default.
-- Returns rows only when a metric exceeds tolerance (empty = pass).

{% set tolerance = var('reconciliation_tolerance_pct', 1.0) %}

with fact_date_range as (
    -- Restrict comparison to dates that exist in the canonical table.
    -- This handles partial loads / incremental builds gracefully.
    select
        min(order_date) as min_date,
        max(order_date) as max_date
    from {{ ref('fact_orders_v1') }}
),

fact_totals as (
    select
        coalesce(sum(revenue_gross), 0) as total_revenue_gross,
        coalesce(sum(revenue_net),   0) as total_revenue_net,
        count(*)                        as row_count
    from {{ ref('fact_orders_v1') }}
),

staging_totals as (
    -- Apply the same filters that fact_orders_v1 uses
    select
        coalesce(sum(s.total_price),    0) as total_revenue_gross,
        coalesce(sum(s.subtotal_price), 0) as total_revenue_net,
        count(*)                            as row_count
    from {{ ref('stg_shopify_orders') }} s
    cross join fact_date_range dr
    where s.tenant_id is not null
        and s.order_id is not null
        and trim(s.order_id) != ''
        and s.report_date >= dr.min_date
        and s.report_date <= dr.max_date
),

comparison as (
    select
        'revenue_gross' as metric,
        s.total_revenue_gross as staging_total,
        f.total_revenue_gross as fact_total,
        s.total_revenue_gross - f.total_revenue_gross as abs_diff,
        case
            when s.total_revenue_gross = 0 and f.total_revenue_gross = 0 then 0
            when s.total_revenue_gross = 0 then 100
            else abs(s.total_revenue_gross - f.total_revenue_gross)
                 / abs(s.total_revenue_gross) * 100
        end as pct_diff,
        s.row_count as staging_rows,
        f.row_count as fact_rows,
        {{ tolerance }} as tolerance_pct
    from staging_totals s
    cross join fact_totals f

    union all

    select
        'revenue_net' as metric,
        s.total_revenue_net as staging_total,
        f.total_revenue_net as fact_total,
        s.total_revenue_net - f.total_revenue_net as abs_diff,
        case
            when s.total_revenue_net = 0 and f.total_revenue_net = 0 then 0
            when s.total_revenue_net = 0 then 100
            else abs(s.total_revenue_net - f.total_revenue_net)
                 / abs(s.total_revenue_net) * 100
        end as pct_diff,
        s.row_count as staging_rows,
        f.row_count as fact_rows,
        {{ tolerance }} as tolerance_pct
    from staging_totals s
    cross join fact_totals f
)

select *
from comparison
where pct_diff > {{ tolerance }}
