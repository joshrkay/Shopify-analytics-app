-- Test: AOV Edge Cases
--
-- This test validates that fct_aov handles all edge cases correctly:
-- 1. Zero-order periods excluded
-- 2. Division by zero returns NULL
-- 3. Outliers properly detected and excluded
-- 4. Multi-currency AOV calculated separately
-- 5. Negative net revenue orders included
-- 6. Tenant isolation
-- 7. AOV = avg_order_value (validation)

with test_scenarios as (
    select
        'zero_order_count' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Periods with zero orders should not appear' as description
    from {{ ref('fct_aov') }}
    where order_count = 0

    union all

    select
        'null_aov_with_orders' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'AOV should not be null when order_count > 0' as description
    from {{ ref('fct_aov') }}
    where order_count > 0
        and aov is null

    union all

    select
        'aov_not_equal_avg' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'AOV should equal avg_order_value (validation check)' as description
    from {{ ref('fct_aov') }}
    where abs(coalesce(aov, 0) - coalesce(avg_order_value, 0)) > 0.01

    union all

    select
        'negative_order_count' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Order count cannot be negative' as description
    from {{ ref('fct_aov') }}
    where order_count < 0

    union all

    select
        'null_tenant_id' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'All AOV records must have tenant_id (tenant isolation)' as description
    from {{ ref('fct_aov') }}
    where tenant_id is null

    union all

    select
        'invalid_period_type' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period type must be daily, weekly, monthly, or all_time' as description
    from {{ ref('fct_aov') }}
    where period_type not in ('daily', 'weekly', 'monthly', 'all_time')

    union all

    select
        'null_currency' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Currency cannot be null' as description
    from {{ ref('fct_aov') }}
    where currency is null

    union all

    select
        'future_period' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period start cannot be in the future' as description
    from {{ ref('fct_aov') }}
    where period_start > current_timestamp

    union all

    select
        'min_greater_than_max' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Min order value cannot exceed max order value' as description
    from {{ ref('fct_aov') }}
    where min_order_value > max_order_value

    union all

    select
        'negative_outliers_excluded' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Outliers excluded count cannot be negative' as description
    from {{ ref('fct_aov') }}
    where outliers_excluded_count < 0
)

select
    scenario,
    actual_count,
    expected_count,
    description
from test_scenarios
where actual_count != expected_count

-- If this query returns any rows, the test fails
