-- Test: CAC & nCAC Edge Cases
--
-- This test validates that fct_cac handles all edge cases correctly:
-- 1. Zero new customers returns CAC = 0 (not NULL or infinity)
-- 2. nCAC >= CAC (net customers are subset of all customers)
-- 3. Net new customers <= All new customers
-- 4. Customer retention rate between 0-100%
-- 5. Multi-currency CAC calculated separately
-- 6. Tenant isolation
-- 7. Platform filtering (only meta_ads, google_ads)

with test_scenarios as (
    select
        'null_cac_with_data' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'CAC should never be NULL (should be 0 if no customers)' as description
    from {{ ref('fct_cac') }}
    where cac is null
        and (total_spend > 0 or new_customers > 0)

    union all

    select
        'null_ncac_with_data' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'nCAC should never be NULL (should be 0 if no net customers)' as description
    from {{ ref('fct_cac') }}
    where ncac is null
        and (total_spend > 0 or net_new_customers > 0)

    union all

    select
        'infinite_cac' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'CAC should never be infinity' as description
    from {{ ref('fct_cac') }}
    where cac = 'Infinity'::numeric
        or ncac = 'Infinity'::numeric

    union all

    select
        'negative_cac' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'CAC cannot be negative' as description
    from {{ ref('fct_cac') }}
    where cac < 0
        or ncac < 0

    union all

    select
        'net_customers_exceeds_all' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Net new customers cannot exceed all new customers' as description
    from {{ ref('fct_cac') }}
    where net_new_customers > new_customers

    union all

    select
        'ncac_less_than_cac' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'nCAC should be >= CAC (fewer customers = higher cost per customer)' as description
    from {{ ref('fct_cac') }}
    where ncac < cac
        and ncac > 0
        and cac > 0  -- Only compare when both are meaningful

    union all

    select
        'negative_spend' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Ad spend cannot be negative' as description
    from {{ ref('fct_cac') }}
    where total_spend < 0

    union all

    select
        'negative_new_customers' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'New customer count cannot be negative' as description
    from {{ ref('fct_cac') }}
    where new_customers < 0
        or net_new_customers < 0

    union all

    select
        'null_tenant_id' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'All CAC records must have tenant_id (tenant isolation)' as description
    from {{ ref('fct_cac') }}
    where tenant_id is null

    union all

    select
        'invalid_platform' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Platform must be meta_ads or google_ads' as description
    from {{ ref('fct_cac') }}
    where platform not in ('meta_ads', 'google_ads')

    union all

    select
        'null_currency' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Currency cannot be null' as description
    from {{ ref('fct_cac') }}
    where currency is null

    union all

    select
        'invalid_period_type' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period type must be daily, weekly, monthly, or all_time' as description
    from {{ ref('fct_cac') }}
    where period_type not in ('daily', 'weekly', 'monthly', 'all_time')

    union all

    select
        'future_period' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Period start cannot be in the future' as description
    from {{ ref('fct_cac') }}
    where period_start > current_timestamp

    union all

    select
        'retention_rate_out_of_bounds' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'Customer retention rate must be between 0 and 100%' as description
    from {{ ref('fct_cac') }}
    where customer_retention_rate_pct < 0
        or customer_retention_rate_pct > 100

    union all

    select
        'cac_calculation_error' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'CAC calculation should match formula when customers > 0' as description
    from {{ ref('fct_cac') }}
    where new_customers > 0
        and abs(cac - (total_spend / new_customers)) > 0.01

    union all

    select
        'ncac_calculation_error' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'nCAC calculation should match formula when net customers > 0' as description
    from {{ ref('fct_cac') }}
    where net_new_customers > 0
        and abs(ncac - (total_spend / net_new_customers)) > 0.01

    union all

    select
        'zero_customers_non_zero_cac' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'When new_customers = 0, CAC must be 0' as description
    from {{ ref('fct_cac') }}
    where new_customers = 0
        and cac != 0

    union all

    select
        'zero_net_customers_non_zero_ncac' as scenario,
        count(*) as actual_count,
        0 as expected_count,
        'When net_new_customers = 0, nCAC must be 0' as description
    from {{ ref('fct_cac') }}
    where net_new_customers = 0
        and ncac != 0
)

select
    scenario,
    actual_count,
    expected_count,
    description
from test_scenarios
where actual_count != expected_count

-- If this query returns any rows, the test fails
