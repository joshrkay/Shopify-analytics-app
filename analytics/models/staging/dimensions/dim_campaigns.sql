{{
    config(
        materialized='table',
        schema='staging'
    )
}}

{#
    Dimension table for campaigns across all advertising platforms.

    This model creates a normalized view of all marketing campaigns
    with deterministic internal IDs for cross-platform analysis.

    Internal ID generation:
    - Formula: 'cmp_' + md5(tenant_id + '|' + source + '|' + platform_campaign_id)
    - This creates a stable, reproducible ID for each unique campaign

    See docs/ID_NORMALIZATION.md for detailed documentation.
#}

with meta_campaigns as (
    select distinct
        tenant_id,
        'meta_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_meta_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

google_campaigns as (
    select distinct
        tenant_id,
        'google_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_google_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

tiktok_campaigns as (
    select distinct
        tenant_id,
        'tiktok_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_tiktok_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

pinterest_campaigns as (
    select distinct
        tenant_id,
        'pinterest_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_pinterest_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

snap_campaigns as (
    select distinct
        tenant_id,
        'snap_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_snap_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

amazon_campaigns as (
    select distinct
        tenant_id,
        'amazon_ads' as source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,
        campaign_name,
        objective,
        canonical_channel,
        min(report_date) as first_seen_at,
        max(report_date) as last_seen_at,
        max(airbyte_emitted_at) as last_updated_at
    from {{ ref('stg_amazon_ads_daily') }}
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

all_campaigns as (
    select * from meta_campaigns
    union all
    select * from google_campaigns
    union all
    select * from tiktok_campaigns
    union all
    select * from pinterest_campaigns
    union all
    select * from snap_campaigns
    union all
    select * from amazon_campaigns
),

final as (
    select
        -- Surrogate key for this dimension row
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(source, '') || '|' ||
            coalesce(platform_campaign_id, '')
        ) as campaign_surrogate_key,

        -- Core attributes
        tenant_id,
        source,
        platform_account_id,
        internal_account_id,
        platform_campaign_id,
        internal_campaign_id,

        -- Campaign attributes
        campaign_name,
        objective,
        canonical_channel,

        -- Lifecycle tracking
        first_seen_at,
        last_seen_at,
        last_updated_at,

        -- Derived status
        case
            when last_seen_at >= current_date - interval '3 days' then 'active'
            when last_seen_at >= current_date - interval '14 days' then 'paused'
            when last_seen_at >= current_date - interval '30 days' then 'inactive'
            else 'archived'
        end as campaign_status,

        -- Duration
        (last_seen_at - first_seen_at) as campaign_duration_days,

        -- Metadata
        current_timestamp as created_at,
        current_timestamp as updated_at

    from all_campaigns
    where tenant_id is not null
        and platform_campaign_id is not null
)

select * from final
