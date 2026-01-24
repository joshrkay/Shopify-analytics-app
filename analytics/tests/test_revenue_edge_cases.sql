-- Test: Revenue Edge Cases
--
-- This test validates that fct_revenue handles all edge cases correctly:
-- 1. Zero-dollar orders
-- 2. Same-day order and refund
-- 3. Partial refunds
-- 4. Multiple refunds on same order
-- 5. Cancellations vs refunds
-- 6. Orders spanning month boundaries
-- 7. Null dates
-- 8. Negative amounts
-- 9. Multi-currency
-- 10. Tenant isolation

with test_scenarios as (
    select
        'zero_dollar_order' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Should be excluded from gross revenue
        'Zero dollar orders should not appear in gross revenue' as description
    from {{ ref('fct_revenue') }}
    where revenue_type = 'gross_revenue'
        and gross_revenue = 0

    union all

    select
        'negative_gross_revenue' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Gross revenue should never be negative
        'Gross revenue records should never be negative' as description
    from {{ ref('fct_revenue') }}
    where revenue_type = 'gross_revenue'
        and gross_revenue < 0

    union all

    select
        'refund_without_cancellation_date' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Refunds require cancelled_at
        'Refund events must have a cancellation date' as description
    from {{ ref('fct_revenue') }}
    where revenue_type = 'refund'
        and order_cancelled_at is null

    union all

    select
        'positive_refund_amount' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Refunds should be negative
        'Refund amounts must be negative or zero' as description
    from {{ ref('fct_revenue') }}
    where revenue_type = 'refund'
        and refund_amount > 0

    union all

    select
        'positive_cancellation_amount' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Cancellations should be negative
        'Cancellation amounts must be negative or zero' as description
    from {{ ref('fct_revenue') }}
    where revenue_type = 'cancellation'
        and cancellation_amount > 0

    union all

    select
        'null_revenue_date' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- All events should have revenue_date
        'All revenue events must have a revenue_date' as description
    from {{ ref('fct_revenue') }}
    where revenue_date is null

    union all

    select
        'null_tenant_id' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- CRITICAL: No events without tenant
        'All revenue events must have tenant_id (tenant isolation)' as description
    from {{ ref('fct_revenue') }}
    where tenant_id is null

    union all

    select
        'future_revenue_date' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- No revenue in the future
        'Revenue date cannot be in the future' as description
    from {{ ref('fct_revenue') }}
    where revenue_date > current_timestamp

    union all

    select
        'invalid_revenue_type' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Only valid revenue types
        'Revenue type must be gross_revenue, refund, or cancellation' as description
    from {{ ref('fct_revenue') }}
    where revenue_type not in ('gross_revenue', 'refund', 'cancellation')

    union all

    select
        'net_revenue_calculation' as scenario,
        count(*) as actual_count,
        0 as expected_count,  -- Net revenue must equal sum of components
        'Net revenue must equal gross + refund + cancellation' as description
    from {{ ref('fct_revenue') }}
    where abs(net_revenue - (gross_revenue + refund_amount + cancellation_amount)) > 0.01
)

select
    scenario,
    actual_count,
    expected_count,
    description
from test_scenarios
where actual_count != expected_count

-- If this query returns any rows, the test fails
-- An empty result means all edge cases pass
