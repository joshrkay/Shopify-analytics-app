{{
    config(
        materialized='view',
        schema='semantic',
        tags=['semantic', 'governed', 'orders']
    )
}}

-- fact_orders_current - Governed semantic view for order data
--
-- This view is the ONLY entry point downstream consumers (Superset, AI marts)
-- should use for order data. It hides physical table names, version changes,
-- and internal columns.
--
-- Current target: fact_orders v1 (registered 2025-06-01)
--
-- Column contract: Only approved columns are exposed. Deprecated columns
-- (platform) and internal columns (refunds_json, airbyte_record_id, ingested_at)
-- are intentionally excluded.
--
-- To repoint to a new version:
--   1. Open a change request via config/governance/change_requests.yaml
--   2. Update this SQL to ref() the new model
--   3. Verify column contract still holds (dbt test -s fact_orders_current)
--   4. Get approval from Analytics Tech Lead
--
-- See: canonical/schema_registry.yml

select
    id,
    tenant_id,
    order_id,
    order_name,
    order_number,
    customer_key,
    source_platform,
    order_created_at,
    order_updated_at,
    order_cancelled_at,
    order_closed_at,
    date,
    revenue_gross,
    revenue_net,
    total_tax,
    currency,
    financial_status,
    fulfillment_status,
    tags,
    note,
    dbt_updated_at
from {{ ref('fact_orders') }}
where tenant_id is not null
