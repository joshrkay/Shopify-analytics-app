{{
    config(
        materialized='table',
        schema='staging'
    )
}}

{#
    Dimension table for ad accounts across all platforms.

    This model creates a normalized view of all advertising accounts
    with deterministic internal IDs for cross-platform analysis.

    Internal ID generation:
    - Formula: 'acc_' + md5(tenant_id + '|' + source + '|' + platform_account_id)
    - This creates a stable, reproducible ID for each unique account

    See docs/ID_NORMALIZATION.md for detailed documentation.
#}

with meta_accounts as (
    select distinct
        tenant_id,
        'meta_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_meta_ads_daily') }}
    group by 1, 2, 3, 4
),

google_accounts as (
    select distinct
        tenant_id,
        'google_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_google_ads_daily') }}
    group by 1, 2, 3, 4
),

tiktok_accounts as (
    select distinct
        tenant_id,
        'tiktok_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_tiktok_ads_daily') }}
    group by 1, 2, 3, 4
),

pinterest_accounts as (
    select distinct
        tenant_id,
        'pinterest_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_pinterest_ads_daily') }}
    group by 1, 2, 3, 4
),

snap_accounts as (
    select distinct
        tenant_id,
        'snap_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_snap_ads_daily') }}
    group by 1, 2, 3, 4
),

amazon_accounts as (
    select distinct
        tenant_id,
        'amazon_ads' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_amazon_ads_daily') }}
    group by 1, 2, 3, 4
),

shopify_accounts as (
    select distinct
        tenant_id,
        'shopify' as source,
        platform_account_id,
        internal_account_id,
        max(airbyte_emitted_at) as last_seen_at
    from {{ ref('stg_shopify_orders') }}
    group by 1, 2, 3, 4
),

all_accounts as (
    select * from meta_accounts
    union all
    select * from google_accounts
    union all
    select * from tiktok_accounts
    union all
    select * from pinterest_accounts
    union all
    select * from snap_accounts
    union all
    select * from amazon_accounts
    union all
    select * from shopify_accounts
),

final as (
    select
        -- Surrogate key for this dimension row
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(source, '') || '|' ||
            coalesce(platform_account_id, '')
        ) as account_surrogate_key,

        -- Core attributes
        tenant_id,
        source,
        platform_account_id,
        internal_account_id,

        -- Platform display info (would be enriched from API in production)
        source || ':' || platform_account_id as account_display_name,

        -- Status tracking
        last_seen_at,
        case
            when last_seen_at >= current_date - interval '7 days' then 'active'
            when last_seen_at >= current_date - interval '30 days' then 'inactive'
            else 'dormant'
        end as account_status,

        -- Metadata
        current_timestamp as created_at,
        current_timestamp as updated_at

    from all_accounts
    where tenant_id is not null
        and platform_account_id is not null
)

select * from final
