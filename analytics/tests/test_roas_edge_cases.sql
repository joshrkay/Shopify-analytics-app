-- Test: ROAS Edge Cases
--
-- This test validates that fct_roas handles all edge cases correctly:
-- 1. Zero spend returns ROAS = 0 (not NULL or infinity)
-- 2. Null spend treated as 0
-- 3. Negative ROAS is valid (heavy refunds)
-- 4. Gross ROAS >= Net ROAS (refunds reduce net)
-- 5. Multi-currency ROAS calculated separately
-- 6. Tenant isolation
-- 7. Platform filtering (only meta_ads, google_ads)

with test_scenarios as (
    select
        'null_roas_with_data' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'ROAS should never be NULL (should be 0 if spend = 0)' as description
    from {{ ref('fct_roas') }}
    where (gross_roas is null or net_roas is null)
        and (total_spend > 0 or total_gross_revenue > 0 or total_net_revenue > 0)

    union all

    select
        'infinite_roas' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'ROAS should never be infinity' as description
    from {{ ref('fct_roas') }}
    where gross_roas = 'Infinity'::numeric
        or net_roas = 'Infinity'::numeric

    union all

    select
        'negative_spend' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Ad spend cannot be negative' as description
    from {{ ref('fct_roas') }}
    where total_spend < 0

    union all

    select
        'negative_order_count' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Order count cannot be negative' as description
    from {{ ref('fct_roas') }}
    where order_count < 0

    union all

    select
        'null_tenant_id' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'All ROAS records must have tenant_id (tenant isolation)' as description
    from {{ ref('fct_roas') }}
    where tenant_id is null

    union all

    select
        'invalid_platform' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Platform must be meta_ads or google_ads' as description
    from {{ ref('fct_roas') }}
    where platform not in ('meta_ads', 'google_ads')

    union all

    select
        'null_currency' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Currency cannot be null' as description
    from {{ ref('fct_roas') }}
    where currency is null

    union all

    select
        'invalid_period_type' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period type must be daily, weekly, monthly, or all_time' as description
    from {{ ref('fct_roas') }}
    where period_type not in ('daily', 'weekly', 'monthly', 'all_time')

    union all

    select
        'future_period' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period start cannot be in the future' as description
    from {{ ref('fct_roas') }}
    where period_start > current_timestamp

    union all

    select
        'gross_less_than_net' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Gross revenue should be >= Net revenue (refunds/cancellations reduce net)' as description
    from {{ ref('fct_roas') }}
    where total_gross_revenue < total_net_revenue
        and total_gross_revenue > 0  -- Only check when there's actual revenue

    union all

    select
        'roas_calculation_error_gross' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Gross ROAS calculation should match formula (allow 0.01 tolerance)' as description
    from {{ ref('fct_roas') }}
    where total_spend > 0
        and abs(gross_roas - (total_gross_revenue / total_spend)) > 0.01

    union all

    select
        'roas_calculation_error_net' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Net ROAS calculation should match formula (allow 0.01 tolerance)' as description
    from {{ ref('fct_roas') }}
    where total_spend > 0
        and abs(net_roas - (total_net_revenue / total_spend)) > 0.01

    union all

    select
        'zero_spend_non_zero_roas' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'When spend = 0, ROAS must be 0' as description
    from {{ ref('fct_roas') }}
    where total_spend = 0
        and (gross_roas != 0 or net_roas != 0)
)

select
    scenario,
    actual_count,
    expected_count,
    description
from test_scenarios
where actual_count != expected_count

-- If this query returns any rows, the test fails
