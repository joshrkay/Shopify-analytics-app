{{
    config(
        materialized='table',
        schema='metrics',
        tags=['metrics', 'ltv', 'cohort']
    )
}}

-- Customer Lifetime Value (LTV) Cohort Metric
--
-- Calculates cohort-based LTV by grouping customers by their first order month
-- and tracking cumulative revenue at 30, 90, 180, and 365 days.
--
-- METHODOLOGY:
-- 1. Identify each customer's first order (cohort entry date)
-- 2. Group customers into monthly cohorts based on first order month
-- 3. Sum all subsequent orders within each LTV window for each cohort
-- 4. Produce one row per cohort + LTV window combination
--
-- SECURITY: Tenant isolation enforced — all rows are scoped by tenant_id.
-- PII: customer_key is a pseudonymized identifier (never raw email/ID).

with first_orders as (
    -- Identify each customer's first order and cohort month
    select
        tenant_id,
        customer_key,
        min(order_created_at) as first_order_at,
        date_trunc('month', min(order_created_at)) as cohort_month
    from {{ ref('orders') }}
    where customer_key is not null
        and tenant_id is not null
        and order_created_at is not null
    group by tenant_id, customer_key
),

customer_orders as (
    -- All orders with days-since-first-order for each customer
    select
        o.tenant_id,
        o.customer_key,
        o.order_id,
        o.order_created_at,
        o.revenue_gross as order_revenue,
        o.currency,
        f.first_order_at,
        f.cohort_month,
        date_part(
            'day',
            o.order_created_at - f.first_order_at
        ) as days_since_first_order
    from {{ ref('orders') }} o
    inner join first_orders f
        on o.tenant_id = f.tenant_id
        and o.customer_key = f.customer_key
    where o.order_created_at is not null
        and o.customer_key is not null
        and o.revenue_gross > 0
),

-- Aggregate LTV at each window per cohort
ltv_windows as (
    select
        tenant_id,
        cohort_month,
        currency,
        count(distinct customer_key) as cohort_size,

        -- 30-day window
        count(distinct case when days_since_first_order <= 30 then customer_key end)
            as customers_with_30d_revenue,
        coalesce(sum(case when days_since_first_order <= 30 then order_revenue end), 0)
            as total_revenue_30d,

        -- 90-day window
        count(distinct case when days_since_first_order <= 90 then customer_key end)
            as customers_with_90d_revenue,
        coalesce(sum(case when days_since_first_order <= 90 then order_revenue end), 0)
            as total_revenue_90d,

        -- 180-day window
        count(distinct case when days_since_first_order <= 180 then customer_key end)
            as customers_with_180d_revenue,
        coalesce(sum(case when days_since_first_order <= 180 then order_revenue end), 0)
            as total_revenue_180d,

        -- 365-day window
        count(distinct case when days_since_first_order <= 365 then customer_key end)
            as customers_with_365d_revenue,
        coalesce(sum(case when days_since_first_order <= 365 then order_revenue end), 0)
            as total_revenue_365d

    from customer_orders
    group by tenant_id, cohort_month, currency
)

select
    -- Surrogate key: deterministic hash of tenant + cohort + currency
    md5(concat(tenant_id, '|', cohort_month::text, '|', currency)) as id,

    tenant_id,
    cohort_month,
    currency,
    cohort_size,

    -- 30-day LTV
    customers_with_30d_revenue,
    total_revenue_30d,
    case
        when cohort_size > 0
        then round((total_revenue_30d / cohort_size)::numeric, 2)
        else 0
    end as avg_ltv_30d,

    -- 90-day LTV
    customers_with_90d_revenue,
    total_revenue_90d,
    case
        when cohort_size > 0
        then round((total_revenue_90d / cohort_size)::numeric, 2)
        else 0
    end as avg_ltv_90d,

    -- 180-day LTV
    customers_with_180d_revenue,
    total_revenue_180d,
    case
        when cohort_size > 0
        then round((total_revenue_180d / cohort_size)::numeric, 2)
        else 0
    end as avg_ltv_180d,

    -- 365-day LTV
    customers_with_365d_revenue,
    total_revenue_365d,
    case
        when cohort_size > 0
        then round((total_revenue_365d / cohort_size)::numeric, 2)
        else 0
    end as avg_ltv_365d,

    -- Retention rates at each window
    case
        when cohort_size > 0
        then round((customers_with_90d_revenue::numeric / cohort_size * 100), 1)
        else 0
    end as retention_rate_90d_pct,

    case
        when cohort_size > 0
        then round((customers_with_365d_revenue::numeric / cohort_size * 100), 1)
        else 0
    end as retention_rate_365d_pct,

    -- Audit
    current_timestamp as dbt_updated_at

from ltv_windows
where tenant_id is not null
    and cohort_size > 0
