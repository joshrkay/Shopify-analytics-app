{{
    config(
        materialized='table',
        schema='analytics',
        tags=['cohorts', 'retention']
    )
}}

-- Cohort retention analysis
-- Groups customers by first-order month, tracks retention in subsequent months
-- SECURITY: Tenant isolation via tenant_id column

with customer_first_order as (
    select
        tenant_id,
        customer_key,
        date_trunc('month', min(order_created_at))::date as cohort_month,
        min(order_created_at) as first_order_date
    from {{ ref('orders') }}
    where tenant_id is not null
      and customer_key is not null
      and customer_key != ''
    group by 1, 2
),

customer_orders as (
    select
        o.tenant_id,
        o.customer_key,
        c.cohort_month,
        date_trunc('month', o.order_created_at)::date as order_month,
        extract(year from age(date_trunc('month', o.order_created_at), c.cohort_month)) * 12
        + extract(month from age(date_trunc('month', o.order_created_at), c.cohort_month)) as period_number,
        o.revenue_gross
    from {{ ref('orders') }} o
    inner join customer_first_order c
        on o.tenant_id = c.tenant_id
        and o.customer_key = c.customer_key
    where o.tenant_id is not null
),

cohort_metrics as (
    select
        tenant_id,
        cohort_month,
        period_number::int as period_number,
        count(distinct customer_key) as customers_active,
        sum(revenue_gross) as cohort_revenue,
        count(*) as order_count
    from customer_orders
    where period_number >= 0 and period_number <= 24
    group by 1, 2, 3
),

cohort_sizes as (
    select
        tenant_id,
        cohort_month,
        count(distinct customer_key) as customers_total
    from customer_first_order
    group by 1, 2
)

select
    md5(concat(cm.tenant_id, '|', cm.cohort_month::text, '|', cm.period_number::text)) as id,
    cm.tenant_id,
    cm.cohort_month,
    cm.period_number,
    cs.customers_total,
    cm.customers_active,
    round((cm.customers_active::numeric / nullif(cs.customers_total, 0))::numeric, 4) as retention_rate,
    cm.cohort_revenue,
    cm.order_count,
    current_timestamp as dbt_updated_at
from cohort_metrics cm
inner join cohort_sizes cs
    on cm.tenant_id = cs.tenant_id
    and cm.cohort_month = cs.cohort_month
where cm.tenant_id is not null
order by cm.tenant_id, cm.cohort_month, cm.period_number
