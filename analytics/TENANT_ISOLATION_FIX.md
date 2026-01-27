# Tenant Isolation Security Fix

## Problem

The previous implementation used `LIMIT 1` to select a tenant_id for all records from a source type (e.g., Shopify). This caused a **critical security vulnerability** in multi-tenant environments:

- If multiple tenants have active Shopify connections, ALL orders/refunds would be assigned to the first tenant found
- This results in cross-tenant data leakage
- Tenant A could see Tenant B's data and vice versa

## Solution

The fix implements proper tenant isolation by:

1. **Extracting connection identifier** from the data source (schema name, table metadata, etc.)
2. **Joining** the extracted identifier to `_tenant_airbyte_connections` table
3. **Mapping** each record to its correct tenant via the `airbyte_connection_id`

### Implementation Strategy

The current implementation uses **Schema-based Isolation** (Strategy 1), which is the most common Airbyte setup pattern:

```sql
-- Extract connection identifier from current_schema()
case
    when current_schema() ~ '^airbyte_raw_[a-zA-Z0-9-]+$'
        then regexp_replace(current_schema(), '^airbyte_raw_', '')
    when current_schema() ~ '^[a-zA-Z0-9-]+_raw$'
        then regexp_replace(current_schema(), '_raw$', '')
    when current_schema() ~ '^[a-zA-Z0-9-]+_[a-zA-Z0-9-]+_raw$'
        then split_part(current_schema(), '_', 2)
    else current_schema()
end as connection_identifier
```

Then join to tenant mapping:
```sql
left join {{ ref('_tenant_airbyte_connections') }} t
    on t.airbyte_connection_id = connection_identifier
    and t.source_type = 'shopify'
    and t.status = 'active'
    and t.is_enabled = true
```

## Alternative Strategies

If your Airbyte setup uses a different pattern, modify the `connection_identifier` extraction:

### Strategy 2: Connection ID in Metadata

If Airbyte adds connection_id to the raw data (requires custom normalization):

```sql
orders_with_connection as (
    select
        ord.*,
        ord.order_data->>'_airbyte_connection_id' as connection_identifier
    from orders_normalized ord
)
```

### Strategy 3: Table Name Prefixes

If connection ID is in the table name (e.g., `_airbyte_raw_conn123_shopify_orders`):

```sql
orders_with_connection as (
    select
        ord.*,
        -- Extract from current table name via pg_catalog
        split_part(
            (select relname from pg_class 
             where oid = (select tableoid from raw_orders limit 1)),
            '_',
            4
        ) as connection_identifier
    from orders_normalized ord
)
```

### Strategy 4: Destination Namespace

If Airbyte is configured with custom namespace per connection:

```sql
orders_with_connection as (
    select
        ord.*,
        -- Extract from namespace in _airbyte_data
        ord.order_data->>'_airbyte_namespace' as connection_identifier
    from orders_normalized ord
)
```

## Verification

To verify tenant isolation is working:

1. Check that each record has a non-null `tenant_id`:
   ```sql
   select tenant_id, count(*)
   from {{ ref('stg_shopify_orders') }}
   group by tenant_id;
   ```

2. Verify no records are dropped (compare before/after counts)

3. Test with multiple active connections:
   - Create two Shopify connections for different tenants
   - Sync data from both
   - Verify each tenant only sees their own data

## Files Changed

- `analytics/models/staging/shopify/stg_shopify_orders.sql`
- `analytics/models/staging/shopify/stg_shopify_refunds.sql`
- `analytics/macros/get_tenant_id.sql`

## Security Impact

This fix prevents:
- Cross-tenant data leakage
- Unauthorized access to other tenants' analytics data
- Compliance violations (GDPR, SOC 2, etc.)

## Testing Recommendations

1. Unit tests for connection identifier extraction
2. Integration tests with multiple tenant connections
3. Data quality tests to verify no NULL tenant_ids
4. Security tests to verify cross-tenant access is blocked
