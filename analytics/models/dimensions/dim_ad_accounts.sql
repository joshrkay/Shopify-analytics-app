{{
    config(
        materialized='table',
        schema='dimensions',
        unique_key='internal_account_id'
    )
}}

{#
    Dimension table for ad accounts across all advertising platforms.

    This model creates a unified view of all ad accounts with:
    - tenant_id for multi-tenant isolation
    - source for platform identification
    - platform_account_id as the original platform ID
    - internal_account_id as a deterministic hash for cross-platform joins

    Internal ID generation: md5(tenant_id || '|' || source || '|' || platform_account_id)
#}

with meta_accounts as (
    select distinct
        tenant_id,
        'meta_ads' as source,
        ad_account_id as platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_meta_ads_daily') }}
    where ad_account_id is not null
),

google_accounts as (
    select distinct
        tenant_id,
        'google_ads' as source,
        ad_account_id as platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_google_ads_daily') }}
    where ad_account_id is not null
),

tiktok_accounts as (
    select distinct
        tenant_id,
        'tiktok_ads' as source,
        platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_tiktok_ads_daily') }}
    where platform_account_id is not null
),

pinterest_accounts as (
    select distinct
        tenant_id,
        'pinterest_ads' as source,
        platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_pinterest_ads_daily') }}
    where platform_account_id is not null
),

snap_accounts as (
    select distinct
        tenant_id,
        'snap_ads' as source,
        platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_snap_ads_daily') }}
    where platform_account_id is not null
),

amazon_accounts as (
    select distinct
        tenant_id,
        'amazon_ads' as source,
        platform_account_id,
        campaign_name as sample_campaign_name,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_amazon_ads_daily') }}
    where platform_account_id is not null
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
),

-- Deduplicate and get latest info per account
accounts_deduped as (
    select
        tenant_id,
        source,
        platform_account_id,
        -- Get most recent sample campaign name and currency
        first_value(sample_campaign_name) over (
            partition by tenant_id, source, platform_account_id
            order by last_seen_at desc
        ) as sample_campaign_name,
        first_value(currency) over (
            partition by tenant_id, source, platform_account_id
            order by last_seen_at desc
        ) as currency,
        max(last_seen_at) as last_seen_at,
        min(last_seen_at) as first_seen_at
    from all_accounts
    group by tenant_id, source, platform_account_id, sample_campaign_name, currency, last_seen_at
)

select distinct
    {{ generate_internal_account_id('tenant_id', 'source', 'platform_account_id') }} as internal_account_id,
    tenant_id,
    source,
    platform_account_id,
    currency,
    first_seen_at,
    last_seen_at,
    current_timestamp as updated_at
from accounts_deduped
