-- Data test: Single connection per source type per tenant
--
-- Email/SMS staging models cannot join on a per-record account identifier
-- (the raw data lacks one). Instead they rely on having at most ONE active
-- connection per source_type. This test fails if that invariant is violated,
-- meaning email/SMS data could be attributed to the wrong tenant.
--
-- Ad platform staging models (Meta, Google, TikTok, Snapchat) use proper
-- account_id JOINs and are not affected by this constraint.
--
-- Returns rows only when there's a problem.

-- Test: No source_type should have more than one active connection
-- across different tenants (for source types that lack per-record identifiers)
select
    source_type,
    count(distinct tenant_id) as tenant_count
from {{ ref('_tenant_airbyte_connections') }}
where source_type in (
    'source-klaviyo',
    'source-shopify',         -- Shopify Email events model
    'source-attentive',
    'source-postscript',
    'source-smsbump'
)
group by source_type
having count(distinct tenant_id) > 1
