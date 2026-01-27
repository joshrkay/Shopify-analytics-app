{{
    config(
        materialized='table',
        schema='dimensions',
        unique_key='internal_campaign_id'
    )
}}

{#
    Dimension table for campaigns across all advertising platforms.

    This model creates a unified view of all campaigns with:
    - tenant_id for multi-tenant isolation
    - source for platform identification
    - platform_campaign_id as the original platform ID
    - internal_campaign_id as a deterministic hash for cross-platform joins
    - internal_account_id linking to dim_ad_accounts

    Internal ID generation: md5(tenant_id || '|' || source || '|' || platform_campaign_id)
#}

with meta_campaigns as (
    select distinct
        tenant_id,
        'meta_ads' as source,
        ad_account_id as platform_account_id,
        campaign_id as platform_campaign_id,
        campaign_name,
        objective as campaign_objective,
        null as campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_meta_ads_daily') }}
    where campaign_id is not null
),

google_campaigns as (
    select distinct
        tenant_id,
        'google_ads' as source,
        ad_account_id as platform_account_id,
        campaign_id as platform_campaign_id,
        campaign_name,
        null as campaign_objective,
        network as campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_google_ads_daily') }}
    where campaign_id is not null
),

tiktok_campaigns as (
    select distinct
        tenant_id,
        'tiktok_ads' as source,
        platform_account_id,
        platform_campaign_id,
        campaign_name,
        campaign_objective,
        null as campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_tiktok_ads_daily') }}
    where platform_campaign_id is not null
),

pinterest_campaigns as (
    select distinct
        tenant_id,
        'pinterest_ads' as source,
        platform_account_id,
        platform_campaign_id,
        campaign_name,
        campaign_objective,
        null as campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_pinterest_ads_daily') }}
    where platform_campaign_id is not null
),

snap_campaigns as (
    select distinct
        tenant_id,
        'snap_ads' as source,
        platform_account_id,
        platform_campaign_id,
        campaign_name,
        campaign_objective,
        null as campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_snap_ads_daily') }}
    where platform_campaign_id is not null
),

amazon_campaigns as (
    select distinct
        tenant_id,
        'amazon_ads' as source,
        platform_account_id,
        platform_campaign_id,
        campaign_name,
        null as campaign_objective,
        campaign_type,
        currency,
        airbyte_emitted_at as last_seen_at
    from {{ ref('stg_amazon_ads_daily') }}
    where platform_campaign_id is not null
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

-- Deduplicate and get latest info per campaign
campaigns_deduped as (
    select
        tenant_id,
        source,
        platform_account_id,
        platform_campaign_id,
        -- Get most recent values
        first_value(campaign_name) over (
            partition by tenant_id, source, platform_campaign_id
            order by last_seen_at desc
        ) as campaign_name,
        first_value(campaign_objective) over (
            partition by tenant_id, source, platform_campaign_id
            order by last_seen_at desc
        ) as campaign_objective,
        first_value(campaign_type) over (
            partition by tenant_id, source, platform_campaign_id
            order by last_seen_at desc
        ) as campaign_type,
        first_value(currency) over (
            partition by tenant_id, source, platform_campaign_id
            order by last_seen_at desc
        ) as currency,
        max(last_seen_at) as last_seen_at,
        min(last_seen_at) as first_seen_at
    from all_campaigns
    group by
        tenant_id, source, platform_account_id, platform_campaign_id,
        campaign_name, campaign_objective, campaign_type, currency, last_seen_at
)

select distinct
    {{ generate_internal_campaign_id('tenant_id', 'source', 'platform_campaign_id') }} as internal_campaign_id,
    {{ generate_internal_account_id('tenant_id', 'source', 'platform_account_id') }} as internal_account_id,
    tenant_id,
    source,
    platform_account_id,
    platform_campaign_id,
    campaign_name,
    campaign_objective,
    campaign_type,
    currency,
    first_seen_at,
    last_seen_at,
    current_timestamp as updated_at
from campaigns_deduped
