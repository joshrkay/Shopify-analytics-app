{{
    config(
        materialized='table',
        schema='utils',
        tags=['utils', 'date']
    )
}}

-- Date Range Dimension Table
--
-- This table generates all possible date ranges for flexible metric reporting:
-- - Standard periods: daily, weekly, monthly, quarterly, yearly, all-time
-- - Rolling windows: last 7/30/90 days
-- - Period-over-period: previous period for comparison
--
-- Usage: Join metrics to this table to get flexible date range aggregations

with date_spine as (
    -- Generate dates for last 2 years + 1 day into future (for "today" calculations)
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2023-01-01' as date)",
        end_date="cast(current_date + interval '1 day' as date)"
    ) }}
),

base_dates as (
    select
        date_day::date as date,
        date_trunc('week', date_day)::date as week_start,
        date_trunc('month', date_day)::date as month_start,
        date_trunc('quarter', date_day)::date as quarter_start,
        date_trunc('year', date_day)::date as year_start
    from date_spine
),

-- Generate all date ranges
date_ranges as (
    -- 1. DAILY (each individual day)
    select
        'daily' as period_type,
        date as period_start,
        date as period_end,
        date - interval '1 day' as prior_period_start,
        date - interval '1 day' as prior_period_end,
        'day_over_day' as comparison_type
    from base_dates

    union all

    -- 2. WEEKLY (Monday-Sunday)
    select distinct
        'weekly' as period_type,
        week_start as period_start,
        week_start + interval '6 days' as period_end,
        week_start - interval '7 days' as prior_period_start,
        week_start - interval '1 day' as prior_period_end,
        'week_over_week' as comparison_type
    from base_dates

    union all

    -- 3. MONTHLY (calendar month)
    select distinct
        'monthly' as period_type,
        month_start as period_start,
        (month_start + interval '1 month' - interval '1 day')::date as period_end,
        (month_start - interval '1 month')::date as prior_period_start,
        (month_start - interval '1 day')::date as prior_period_end,
        'month_over_month' as comparison_type
    from base_dates

    union all

    -- 4. QUARTERLY (calendar quarter)
    select distinct
        'quarterly' as period_type,
        quarter_start as period_start,
        (quarter_start + interval '3 months' - interval '1 day')::date as period_end,
        (quarter_start - interval '3 months')::date as prior_period_start,
        (quarter_start - interval '1 day')::date as prior_period_end,
        'quarter_over_quarter' as comparison_type
    from base_dates

    union all

    -- 5. YEARLY (calendar year)
    select distinct
        'yearly' as period_type,
        year_start as period_start,
        (year_start + interval '1 year' - interval '1 day')::date as period_end,
        (year_start - interval '1 year')::date as prior_period_start,
        (year_start - interval '1 day')::date as prior_period_end,
        'year_over_year' as comparison_type
    from base_dates

    union all

    -- 6. LAST 7 DAYS (rolling)
    select
        'last_7_days' as period_type,
        date - interval '6 days' as period_start,
        date as period_end,
        date - interval '13 days' as prior_period_start,
        date - interval '7 days' as prior_period_end,
        'prior_7_days' as comparison_type
    from base_dates

    union all

    -- 7. LAST 30 DAYS (rolling)
    select
        'last_30_days' as period_type,
        date - interval '29 days' as period_start,
        date as period_end,
        date - interval '59 days' as prior_period_start,
        date - interval '30 days' as prior_period_end,
        'prior_30_days' as comparison_type
    from base_dates

    union all

    -- 8. LAST 90 DAYS (rolling)
    select
        'last_90_days' as period_type,
        date - interval '89 days' as period_start,
        date as period_end,
        date - interval '179 days' as prior_period_start,
        date - interval '90 days' as prior_period_end,
        'prior_90_days' as comparison_type
    from base_dates
)

select
    -- Generate unique ID
    md5(concat(
        period_type, '|',
        period_start::text, '|',
        period_end::text
    )) as date_range_id,

    period_type,
    period_start::date,
    period_end::date,

    -- Period length
    (period_end::date - period_start::date + 1) as period_days,

    -- Prior period (for comparison)
    prior_period_start::date,
    prior_period_end::date,
    (prior_period_end::date - prior_period_start::date + 1) as prior_period_days,

    comparison_type,

    -- Metadata
    current_timestamp as dbt_updated_at

from date_ranges
where period_start >= '2023-01-01'::date  -- Limit historical data
    and period_end <= current_date  -- Don't create future periods

-- Filter to only complete periods (don't include partial ongoing periods)
-- Exception: "last_X_days" periods are always complete up to "today"
