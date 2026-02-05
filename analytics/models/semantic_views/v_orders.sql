{{
    config(
        materialized='view',
        schema='semantic'
    )
}}

-- Stable semantic view for orders
--
-- This view provides a stable interface for downstream consumers.
-- Column names here are guaranteed stable even if canonical schema changes.
-- Only consumer-relevant columns are exposed.
--
-- SECURITY: Tenant isolation enforced via tenant_id from canonical layer.

select
    tenant_id,
    id as order_key,
    order_id,
    order_name,
    order_number,
    customer_key,
    source_platform,
    date,
    order_created_at,
    order_updated_at,
    order_cancelled_at,
    order_closed_at,
    revenue_gross,
    revenue_net,
    total_tax,
    currency,
    financial_status,
    fulfillment_status,
    tags
from {{ ref('orders') }}
