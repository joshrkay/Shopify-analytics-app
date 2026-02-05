{{
    config(
        materialized='view',
        schema='semantic'
    )
}}

-- Stable semantic view for campaign performance
--
-- This view provides a stable interface for downstream consumers.
-- Column names here are guaranteed stable even if canonical schema changes.
-- Only consumer-relevant columns are exposed.
--
-- SECURITY: Tenant isolation enforced via tenant_id from canonical layer.

select
    tenant_id,
    id as campaign_performance_key,
    date,
    source_platform,
    channel,
    ad_account_id,
    campaign_id,
    campaign_name,
    spend,
    impressions,
    clicks,
    conversions,
    ctr,
    cpc,
    cpa,
    currency
from {{ ref('campaign_performance') }}
