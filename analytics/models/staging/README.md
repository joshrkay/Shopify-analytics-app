# Staging Models

Staging models normalize raw Airbyte data into consistent, typed models with tenant isolation.

## Tenant Isolation

All staging models enforce tenant isolation by joining to `_tenant_airbyte_connections` to get `tenant_id`.

### Tenant Mapping Configuration

The tenant mapping strategy depends on your Airbyte setup:

**Option 1: Connection-Specific Schemas**
If Airbyte stores data in schemas like `_airbyte_raw_<connection_id>_shopify_orders`:
- Uncomment the schema extraction logic in staging models
- Extract `connection_id` from `current_schema()` or table metadata
- Join to `_tenant_airbyte_connections` on `airbyte_connection_id`

**Option 2: Single Connection Per Tenant**
If each tenant has exactly one active Shopify connection:
- Use the current implementation (selects first active connection)
- This works for most single-tenant-per-connection setups

**Option 3: Connection ID in Metadata**
If connection_id is stored in Airbyte metadata:
- Extract connection_id from `_airbyte_data` or metadata columns
- Join to `_tenant_airbyte_connections` on `airbyte_connection_id`

### Updating Tenant Mapping

To update the tenant mapping strategy, modify:
- `stg_shopify_orders.sql` - `orders_with_tenant` CTE
- `stg_shopify_customers.sql` - `customers_with_tenant` CTE
- Or use the `get_tenant_id()` macro in `macros/get_tenant_id.sql`

## Models

### `stg_shopify_orders`
- Normalizes Shopify order data
- Handles timestamps (UTC conversion)
- Converts currency fields to numeric
- Normalizes IDs (removes gid:// prefixes)
- Filters by tenant_id

### `stg_shopify_customers`
- Normalizes Shopify customer data
- Handles timestamps (UTC conversion)
- Converts boolean fields
- Normalizes IDs (removes gid:// prefixes)
- Filters by tenant_id

## Tests

All models have comprehensive tests in `schema.yml`:
- `not_null` on primary keys
- `unique` on order_id, customer_id
- `relationships` to tenant mapping
- Tenant isolation regression tests

Run tests:
```bash
dbt test --select staging
```
