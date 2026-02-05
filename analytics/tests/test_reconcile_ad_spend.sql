-- Reconciliation test: Ad Platform Spend
--
-- Validates that spend totals in fact_marketing_spend_v1 match the
-- aggregated staging sources (Meta, Google, TikTok, Snapchat) within
-- a configurable tolerance.
--
-- fact_marketing_spend_v1 unions spend from all four platforms with
-- filters: tenant_id is not null, date is not null, spend is not null.
-- This test replicates those filters on the staging side so the
-- comparison is apples-to-apples.
--
-- Tolerance: var('reconciliation_tolerance_pct', 1.0)  →  ±1 % by default.
-- Returns rows only when a metric exceeds tolerance (empty = pass).

{% set tolerance = var('reconciliation_tolerance_pct', 1.0) %}

with fact_date_range as (
    select
        min(spend_date) as min_date,
        max(spend_date) as max_date
    from {{ ref('fact_marketing_spend_v1') }}
),

fact_totals as (
    select
        coalesce(sum(spend), 0)        as total_spend,
        coalesce(sum(impressions), 0)  as total_impressions,
        coalesce(sum(clicks), 0)       as total_clicks,
        count(*)                       as row_count
    from {{ ref('fact_marketing_spend_v1') }}
),

-- Replicate the same filters that fact_marketing_spend_v1 applies per platform
staging_meta as (
    select spend, impressions, clicks, date
    from {{ ref('stg_facebook_ads_performance') }}
    where tenant_id is not null and date is not null and spend is not null
),

staging_google as (
    select spend, impressions, clicks, date
    from {{ ref('stg_google_ads_performance') }}
    where tenant_id is not null and date is not null and spend is not null
),

staging_tiktok as (
    select spend, impressions, clicks, date
    from {{ ref('stg_tiktok_ads_performance') }}
    where tenant_id is not null and date is not null and spend is not null
),

staging_snapchat as (
    select spend, impressions, clicks, date
    from {{ ref('stg_snapchat_ads') }}
    where tenant_id is not null and date is not null and spend is not null
),

staging_unified as (
    select spend, impressions, clicks, date from staging_meta
    union all
    select spend, impressions, clicks, date from staging_google
    union all
    select spend, impressions, clicks, date from staging_tiktok
    union all
    select spend, impressions, clicks, date from staging_snapchat
),

staging_totals as (
    select
        coalesce(sum(u.spend), 0)        as total_spend,
        coalesce(sum(u.impressions), 0)  as total_impressions,
        coalesce(sum(u.clicks), 0)       as total_clicks,
        count(*)                         as row_count
    from staging_unified u
    cross join fact_date_range dr
    where u.date >= dr.min_date
      and u.date <= dr.max_date
),

comparison as (
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
        'impressions' as metric,
        s.total_impressions as staging_total,
        f.total_impressions as fact_total,
        s.total_impressions - f.total_impressions as abs_diff,
        case
            when s.total_impressions = 0 and f.total_impressions = 0 then 0
            when s.total_impressions = 0 then 100
            else abs(s.total_impressions - f.total_impressions)
                 / s.total_impressions * 100
        end as pct_diff,
        s.row_count as staging_rows,
        f.row_count as fact_rows,
        {{ tolerance }} as tolerance_pct
    from staging_totals s
    cross join fact_totals f

    union all

    select
        'clicks' as metric,
        s.total_clicks as staging_total,
        f.total_clicks as fact_total,
        s.total_clicks - f.total_clicks as abs_diff,
        case
            when s.total_clicks = 0 and f.total_clicks = 0 then 0
            when s.total_clicks = 0 then 100
            else abs(s.total_clicks - f.total_clicks)
                 / s.total_clicks * 100
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
