-- Test: Verify tenant mapping configuration for multi-tenant Shopify support
--
-- This test validates that tenant mapping is properly configured:
-- 1. Each active Shopify connection must have a shop_domain configured
-- 2. No duplicate shop_domains (would cause ambiguous tenant mapping)
--
-- Returns rows only when there's a problem (test fails if any rows returned)

-- Test 1: Active Shopify connections must have shop_domain configured
select 'missing_shop_domain' as test_name, airbyte_connection_id
from {{ ref('_tenant_airbyte_connections') }}
where source_type in ('shopify', 'source-shopify')
    and status = 'active'
    and is_enabled = true
    and (shop_domain is null or shop_domain = '')

union all

-- Test 2: No duplicate shop_domains across tenants (would cause ambiguous mapping)
select 'duplicate_shop_domain' as test_name, shop_domain as airbyte_connection_id
from {{ ref('_tenant_airbyte_connections') }}
where source_type in ('shopify', 'source-shopify')
    and status = 'active'
    and is_enabled = true
    and shop_domain is not null
    and shop_domain != ''
group by shop_domain
having count(distinct tenant_id) > 1
