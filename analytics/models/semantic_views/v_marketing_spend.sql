{{
    config(
        materialized='view',
        schema='semantic'
    )
}}

-- Stable semantic view for marketing spend
--
-- This view provides a stable interface for downstream consumers.
-- Column names here are guaranteed stable even if canonical schema changes.
-- Only consumer-relevant columns are exposed.
--
-- SECURITY: Tenant isolation enforced via tenant_id from canonical layer.

select
    tenant_id,
    id as spend_key,
    date,
    source_platform,
    channel,
    ad_account_id,
    campaign_id,
    adset_id,
    ad_id,
    spend,
    currency,
    impressions,
    clicks,
    conversions,
    conversion_value,
    cpm,
    cpc,
    ctr,
    cpa,
    roas
from {{ ref('marketing_spend') }}
