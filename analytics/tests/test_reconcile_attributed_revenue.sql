-- Reconciliation test: Attributed Revenue & Conversions
--
-- Validates that attributed_revenue and spend totals in
-- fact_campaign_performance_v1 match the aggregated staging sources
-- (Meta, Google, TikTok, Snapchat) within a configurable tolerance.
--
-- fact_campaign_performance_v1 maps staging conversion_value to
-- attributed_revenue, and passes through spend and conversions.
-- Filters: tenant_id is not null, campaign_id is not null, date is not null.
--
-- Tolerance: var('reconciliation_tolerance_pct', 1.0)  →  ±1 % by default.
-- Returns rows only when a metric exceeds tolerance (empty = pass).

{% set tolerance = var('reconciliation_tolerance_pct', 1.0) %}

with fact_date_range as (
    select
        min(campaign_date) as min_date,
        max(campaign_date) as max_date
    from {{ ref('fact_campaign_performance_v1') }}
),

fact_totals as (
    select
        coalesce(sum(attributed_revenue), 0) as total_attributed_revenue,
        coalesce(sum(spend), 0)              as total_spend,
        coalesce(sum(conversions), 0)        as total_conversions,
        count(*)                             as row_count
    from {{ ref('fact_campaign_performance_v1') }}
),

-- Replicate the same filters that fact_campaign_performance_v1 applies
staging_meta as (
    select conversion_value, spend, conversions, date
    from {{ ref('stg_facebook_ads_performance') }}
    where tenant_id is not null and campaign_id is not null and date is not null
),

staging_google as (
    select conversion_value, spend, conversions, date
    from {{ ref('stg_google_ads_performance') }}
    where tenant_id is not null and campaign_id is not null and date is not null
),

staging_tiktok as (
    select conversion_value, spend, conversions, date
    from {{ ref('stg_tiktok_ads_performance') }}
    where tenant_id is not null and campaign_id is not null and date is not null
),

staging_snapchat as (
    select conversion_value, spend, conversions, date
    from {{ ref('stg_snapchat_ads') }}
    where tenant_id is not null and campaign_id is not null and date is not null
),

staging_unified as (
    select conversion_value, spend, conversions, date from staging_meta
    union all
    select conversion_value, spend, conversions, date from staging_google
    union all
    select conversion_value, spend, conversions, date from staging_tiktok
    union all
    select conversion_value, spend, conversions, date from staging_snapchat
),

staging_totals as (
    select
        coalesce(sum(u.conversion_value), 0) as total_attributed_revenue,
        coalesce(sum(u.spend), 0)            as total_spend,
        coalesce(sum(u.conversions), 0)      as total_conversions,
        count(*)                             as row_count
    from staging_unified u
    cross join fact_date_range dr
    where u.date >= dr.min_date
      and u.date <= dr.max_date
),

comparison as (
    select
        'attributed_revenue' as metric,
        s.total_attributed_revenue as staging_total,
        f.total_attributed_revenue as fact_total,
        s.total_attributed_revenue - f.total_attributed_revenue as abs_diff,
        case
            when s.total_attributed_revenue = 0 and f.total_attributed_revenue = 0 then 0
            when s.total_attributed_revenue = 0 then 100
            else abs(s.total_attributed_revenue - f.total_attributed_revenue)
                 / abs(s.total_attributed_revenue) * 100
        end as pct_diff,
        s.row_count as staging_rows,
        f.row_count as fact_rows,
        {{ tolerance }} as tolerance_pct
    from staging_totals s
    cross join fact_totals f

    union all

    select
        'spend' as metric,
        s.total_spend   as staging_total,
        f.total_spend   as fact_total,
        s.total_spend - f.total_spend as abs_diff,
        case
            when s.total_spend = 0 and f.total_spend = 0 then 0
            when s.total_spend = 0 then 100
            else abs(s.total_spend - f.total_spend)
                 / abs(s.total_spend) * 100
        end as pct_diff,
        s.row_count as staging_rows,
        f.row_count as fact_rows,
        {{ tolerance }} as tolerance_pct
    from staging_totals s
    cross join fact_totals f

    union all

    select
        'conversions' as metric,
        s.total_conversions as staging_total,
        f.total_conversions as fact_total,
        s.total_conversions - f.total_conversions as abs_diff,
        case
            when s.total_conversions = 0 and f.total_conversions = 0 then 0
            when s.total_conversions = 0 then 100
            else abs(s.total_conversions - f.total_conversions)
                 / abs(s.total_conversions) * 100
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
