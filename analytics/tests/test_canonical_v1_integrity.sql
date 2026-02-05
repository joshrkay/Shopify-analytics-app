-- Regression test: Canonical v1 Fact Table Integrity
--
-- Validates data quality, tenant isolation, and business rules for
-- fact_orders_v1, fact_marketing_spend_v1, and fact_campaign_performance_v1.
--
-- CRITICAL: These tests enforce the hybrid revenue truth policy and
-- tenant isolation guarantees. Failure blocks the pipeline.
--
-- Returns rows only when there's a problem (empty result = all pass).

-- ── fact_orders_v1 ──────────────────────────────────────────────────────

-- T1: Orders must have valid tenant_id in tenant registry
select 'orders_v1_invalid_tenant' as test_name, count(*) as failure_count
from {{ ref('fact_orders_v1') }} o
left join {{ ref('_tenant_airbyte_connections') }} t
    on o.tenant_id = t.tenant_id
where o.tenant_id is not null
    and t.tenant_id is null
having count(*) > 0

union all

-- T2: Order revenue_gross must be non-negative (refunds flagged separately)
select 'orders_v1_negative_gross_revenue' as test_name, count(*) as failure_count
from {{ ref('fact_orders_v1') }}
where revenue_gross < 0
having count(*) > 0

union all

-- T3: No duplicate order_ids within a tenant (grain violation)
select 'orders_v1_duplicate_order_per_tenant' as test_name, count(*) as failure_count
from (
    select tenant_id, order_id
    from {{ ref('fact_orders_v1') }}
    group by tenant_id, order_id
    having count(*) > 1
) duplicates
having count(*) > 0

union all

-- T4: order_date must not be in the future
select 'orders_v1_future_order_date' as test_name, count(*) as failure_count
from {{ ref('fact_orders_v1') }}
where order_date > current_date + 1
having count(*) > 0

union all

-- T5: source_system must be 'shopify' (no cross-contamination)
select 'orders_v1_wrong_source_system' as test_name, count(*) as failure_count
from {{ ref('fact_orders_v1') }}
where source_system != 'shopify'
having count(*) > 0

union all

-- ── fact_marketing_spend_v1 ─────────────────────────────────────────────

-- T6: Spend must be non-negative
select 'spend_v1_negative_spend' as test_name, count(*) as failure_count
from {{ ref('fact_marketing_spend_v1') }}
where spend < 0
having count(*) > 0

union all

-- T7: No duplicate records at the grain level
-- Grain: tenant_id + source_system + campaign_id + ad_set_id + ad_id + spend_date
select 'spend_v1_grain_violation' as test_name, count(*) as failure_count
from (
    select tenant_id, source_system, campaign_id,
           coalesce(ad_set_id, ''), spend_date
    from {{ ref('fact_marketing_spend_v1') }}
    group by tenant_id, source_system, campaign_id,
             coalesce(ad_set_id, ''), spend_date
    having count(*) > 1
) duplicates
having count(*) > 0

union all

-- T8: Valid tenant_id in tenant registry
select 'spend_v1_invalid_tenant' as test_name, count(*) as failure_count
from {{ ref('fact_marketing_spend_v1') }} s
left join {{ ref('_tenant_airbyte_connections') }} t
    on s.tenant_id = t.tenant_id
where s.tenant_id is not null
    and t.tenant_id is null
having count(*) > 0

union all

-- T9: spend_date must not be in the future
select 'spend_v1_future_spend_date' as test_name, count(*) as failure_count
from {{ ref('fact_marketing_spend_v1') }}
where spend_date > current_date + 1
having count(*) > 0

union all

-- ── fact_campaign_performance_v1 ────────────────────────────────────────

-- T10: Spend must be non-negative
select 'perf_v1_negative_spend' as test_name, count(*) as failure_count
from {{ ref('fact_campaign_performance_v1') }}
where spend < 0
having count(*) > 0

union all

-- T11: attributed_revenue should not be negative (platform-reported value)
select 'perf_v1_negative_attributed_revenue' as test_name, count(*) as failure_count
from {{ ref('fact_campaign_performance_v1') }}
where attributed_revenue < 0
having count(*) > 0

union all

-- T12: No duplicate records at the grain level
-- Grain: tenant_id + source_system + campaign_id + ad_set_id + campaign_date
select 'perf_v1_grain_violation' as test_name, count(*) as failure_count
from (
    select tenant_id, source_system, campaign_id,
           coalesce(ad_set_id, ''), campaign_date
    from {{ ref('fact_campaign_performance_v1') }}
    group by tenant_id, source_system, campaign_id,
             coalesce(ad_set_id, ''), campaign_date
    having count(*) > 1
) duplicates
having count(*) > 0

union all

-- T13: Valid tenant_id in tenant registry
select 'perf_v1_invalid_tenant' as test_name, count(*) as failure_count
from {{ ref('fact_campaign_performance_v1') }} p
left join {{ ref('_tenant_airbyte_connections') }} t
    on p.tenant_id = t.tenant_id
where p.tenant_id is not null
    and t.tenant_id is null
having count(*) > 0

union all

-- T14: campaign_date must not be in the future
select 'perf_v1_future_campaign_date' as test_name, count(*) as failure_count
from {{ ref('fact_campaign_performance_v1') }}
where campaign_date > current_date + 1
having count(*) > 0

union all

-- ── Cross-model: Hybrid Revenue Truth Policy ────────────────────────────

-- T15: fact_orders_v1 source_system must only be 'shopify'
--      fact_campaign_performance_v1 source_system must NOT be 'shopify'
--      This enforces the hybrid revenue truth boundary.
select 'hybrid_revenue_boundary_violated' as test_name, count(*) as failure_count
from {{ ref('fact_campaign_performance_v1') }}
where source_system = 'shopify'
having count(*) > 0
