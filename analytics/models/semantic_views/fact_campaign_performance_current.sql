{{
    config(
        materialized='view',
        schema='semantic',
        tags=['semantic', 'governed', 'campaigns']
    )
}}

-- fact_campaign_performance_current - Governed semantic view for campaign data
--
-- This view is the ONLY entry point downstream consumers (Superset, AI marts)
-- should use for campaign performance data. It hides physical table names,
-- version changes, and internal columns.
--
-- Current target: fact_campaign_performance v1 (registered 2025-06-01)
--
-- Column contract: Only approved columns are exposed. Deprecated columns
-- (platform) and internal columns (airbyte_record_id, ingested_at) are
-- intentionally excluded.
--
-- To repoint to a new version:
--   1. Open a change request via config/governance/change_requests.yaml
--   2. Update this SQL to ref() the new model
--   3. Verify column contract still holds (dbt test -s fact_campaign_performance_current)
--   4. Get approval from Analytics Tech Lead
--
-- See: canonical/schema_registry.yml

select
    id,
    tenant_id,
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
    currency,
    dbt_updated_at
from {{ ref('fact_campaign_performance') }}
where tenant_id is not null
