# Raw Warehouse Layer Schema Documentation

> **Version**: 1.0.0
> **Last Updated**: 2026-01-26
> **Status**: Production Ready

## Overview

The raw warehouse layer stores source-system data with minimal transformation, serving as the foundation for downstream analytics and reporting. This layer implements strict multi-tenant isolation using PostgreSQL Row-Level Security (RLS).

## Architecture Decisions (Locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Warehouse** | PostgreSQL | Existing infrastructure, RLS support, proven reliability |
| **Tenant Isolation** | Shared tables + RLS | Cost-effective, simpler operations, proven security model |
| **Table Naming** | Source-prefixed domain tables | Clear data lineage (`raw_shopify_orders`, `raw_meta_ads_insights`) |
| **Data Retention** | 13 months | Balance between analytics depth and storage costs |
| **PII Policy** | Minimal (IDs + metrics only) | Compliance, reduced risk, storage efficiency |
| **Indexing** | `(tenant_id, extracted_at)` | Optimized for tenant-scoped time-series queries |

## Schema Structure

### Tables

```
raw.
├── raw_shopify_orders        # Shopify order data (IDs + metrics)
├── raw_shopify_customers     # Customer reference data (ID only, no PII)
├── raw_shopify_products      # Product catalog data
├── raw_meta_ads_insights     # Meta (Facebook/Instagram) Ads performance
├── raw_google_ads_campaigns  # Google Ads campaign performance
├── raw_pipeline_runs         # Pipeline execution tracking
├── raw_rls_audit_log         # RLS event audit trail
├── retention_config          # Retention job configuration
└── retention_audit_log       # Retention cleanup audit trail
```

### Required Columns (All Raw Tables)

Every raw table MUST include these columns:

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | `VARCHAR(255) NOT NULL` | Tenant identifier from JWT `org_id` - RLS enforced |
| `source_account_id` | `VARCHAR(255) NOT NULL` | Source system account (shop_id, ad_account_id, etc.) |
| `extracted_at` | `TIMESTAMP WITH TIME ZONE NOT NULL` | When data was extracted from source API |
| `loaded_at` | `TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()` | When data was loaded into warehouse |
| `run_id` | `VARCHAR(255) NOT NULL` | Pipeline run identifier for traceability |

### Data Types

- **Primary Keys**: `VARCHAR(255)` with UUID default
- **Timestamps**: `TIMESTAMP WITH TIME ZONE`
- **Money**: `BIGINT` in cents (Shopify/Meta) or micros (Google Ads)
- **Percentages**: `NUMERIC(10, 6)` for CTR, conversion rates
- **Flexible Data**: `JSONB` for raw API responses

## Security Model

### Row-Level Security (RLS)

All raw tables enforce RLS to ensure complete tenant isolation:

```sql
-- Set tenant context before any query
SET app.tenant_id = 'tenant-123';

-- All queries automatically filtered by tenant_id
SELECT * FROM raw.raw_shopify_orders;  -- Only returns tenant-123 data
```

### Roles

| Role | Purpose | Permissions |
|------|---------|-------------|
| `raw_query_role` | Application queries | SELECT only, RLS enforced |
| `raw_admin_role` | Data loading | Full CRUD, bypasses RLS |
| `raw_retention_role` | Cleanup jobs | SELECT + DELETE, bypasses RLS |

### Security Guarantees

1. **No cross-tenant data access**: Query role physically cannot see other tenants' data
2. **No data without context**: Empty/invalid tenant context returns zero rows
3. **SQL injection protected**: Parameterized tenant context via session variables
4. **Audited access**: All RLS events logged for security monitoring

## Table Details

### raw_shopify_orders

Shopify order data with PII removed. Stores IDs and metrics only.

```sql
-- Key columns (beyond required)
shopify_order_id VARCHAR(255) NOT NULL   -- Shopify's order ID
order_number VARCHAR(50)                  -- Human-readable order number
financial_status VARCHAR(50)              -- paid, pending, refunded, etc.
total_price_cents BIGINT                  -- Total in cents
shopify_customer_id VARCHAR(255)          -- Customer ID reference (no PII)
order_created_at TIMESTAMP WITH TIME ZONE -- Order creation time
```

**Note**: Customer names, emails, addresses, and phone numbers are NOT stored.

### raw_meta_ads_insights

Meta (Facebook/Instagram) Ads performance metrics.

```sql
-- Key columns
campaign_id VARCHAR(255)          -- Meta campaign identifier
adset_id VARCHAR(255)             -- Ad set identifier
ad_id VARCHAR(255)                -- Ad identifier
date_start DATE                   -- Insight date range start
impressions BIGINT                -- Total impressions
clicks BIGINT                     -- Total clicks
spend_cents BIGINT                -- Spend in cents
conversions BIGINT                -- Conversion count
roas NUMERIC(10, 4)               -- Return on ad spend
```

### raw_google_ads_campaigns

Google Ads campaign performance metrics.

```sql
-- Key columns
campaign_id VARCHAR(255)          -- Google campaign identifier
campaign_name VARCHAR(500)        -- Campaign display name
metrics_date DATE                 -- Date for metrics
impressions BIGINT                -- Total impressions
clicks BIGINT                     -- Total clicks
cost_micros BIGINT                -- Cost in micros (divide by 1M)
conversions NUMERIC(18, 6)        -- Conversions (can be fractional)
```

## Indexing Strategy

All tables include these indexes for optimal performance:

```sql
-- Primary query pattern: tenant + time range
CREATE INDEX idx_<table>_tenant_extracted
    ON raw.<table>(tenant_id, extracted_at DESC);

-- Source account filtering
CREATE INDEX idx_<table>_tenant_source
    ON raw.<table>(tenant_id, source_account_id);

-- Pipeline tracking
CREATE INDEX idx_<table>_run ON raw.<table>(run_id);
```

## Data Retention

### Policy

- **Retention Period**: 13 months from `extracted_at`
- **Cleanup Schedule**: Daily at 3 AM UTC (recommended)
- **Batch Size**: 10,000 records per batch (configurable)
- **Audit Trail**: All deletions logged in `retention_audit_log`

### Running Cleanup

```sql
-- Preview what would be deleted (dry run)
SELECT * FROM raw.preview_retention_cleanup();

-- Execute cleanup
SELECT * FROM raw.execute_retention_cleanup();

-- Cleanup specific tenant
SELECT * FROM raw.cleanup_tenant_retention(
    'tenant-123',
    'raw_shopify_orders',
    'manual-cleanup-001'
);
```

### Scheduling with pg_cron

```sql
-- Schedule daily cleanup at 3 AM UTC
SELECT cron.schedule(
    'raw-retention-cleanup',
    '0 3 * * *',
    $$SELECT * FROM raw.execute_retention_cleanup()$$
);
```

## Migration Guide

### Initial Setup

Run migrations in order:

```bash
# 1. Create schema and tables
psql $DATABASE_URL -f db/migrations/raw_schema.sql

# 2. Enable RLS policies
psql $DATABASE_URL -f db/rls/raw_rls.sql

# 3. Configure retention
psql $DATABASE_URL -f db/retention/raw_cleanup.sql

# 4. Verify with tests
psql $DATABASE_URL -f db/tests/test_raw_rls_isolation.sql
```

### Application Integration

```python
# Before executing queries, set tenant context
async def set_tenant_context(db: AsyncSession, tenant_id: str):
    await db.execute(text("SET app.tenant_id = :tenant_id"), {"tenant_id": tenant_id})

# Example usage in repository
class RawOrdersRepository:
    async def get_orders(self, tenant_id: str, start_date: date, end_date: date):
        await set_tenant_context(self.db, tenant_id)
        result = await self.db.execute(
            text("""
                SELECT * FROM raw.raw_shopify_orders
                WHERE extracted_at BETWEEN :start AND :end
                ORDER BY order_created_at DESC
            """),
            {"start": start_date, "end": end_date}
        )
        return result.fetchall()
```

### Data Loading (Admin Role)

```python
# Data loading should use admin role (bypasses RLS)
async def load_shopify_orders(orders: list[dict], run_id: str):
    async with admin_db_session() as db:
        for order in orders:
            await db.execute(
                text("""
                    INSERT INTO raw.raw_shopify_orders (
                        tenant_id, source_account_id, extracted_at, run_id,
                        shopify_order_id, order_number, total_price_cents, ...
                    ) VALUES (:tenant_id, :source_account_id, :extracted_at, ...)
                    ON CONFLICT (tenant_id, source_account_id, shopify_order_id)
                    DO UPDATE SET ...
                """),
                order
            )
```

## PII Handling

### What We Store (IDs + Metrics)

- `shopify_order_id` - Order identifier
- `shopify_customer_id` - Customer identifier (for joins)
- `order_number` - Human-readable order number
- Financial totals (price, tax, shipping, discounts)
- Status fields (financial, fulfillment)
- Timestamps

### What We Do NOT Store

- Customer names
- Email addresses
- Physical addresses
- Phone numbers
- IP addresses
- Payment card details
- Any other PII

### Raw Data Field

The `raw_data` JSONB column should contain the API response with PII fields filtered out at extraction time:

```python
def filter_pii_from_order(order: dict) -> dict:
    """Remove PII fields before storing raw_data."""
    pii_fields = [
        'customer', 'email', 'phone', 'billing_address',
        'shipping_address', 'note', 'browser_ip'
    ]
    return {k: v for k, v in order.items() if k not in pii_fields}
```

## Testing

### RLS Isolation Tests

Run the test suite to verify tenant isolation:

```bash
psql $DATABASE_URL -f db/tests/test_raw_rls_isolation.sql
```

Tests verify:

1. Tenant A sees only Tenant A data
2. Tenant B sees only Tenant B data
3. Cross-tenant queries return zero rows
4. Empty tenant context returns zero rows
5. Invalid tenant context returns zero rows
6. SQL injection attempts are blocked
7. Cross-tenant INSERT is blocked

### Adding New Tests

```sql
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    -- Set tenant context
    PERFORM set_config('app.tenant_id', 'test-tenant-001', true);

    -- Run your test query
    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    -- Assert expected result
    IF v_count != expected_value THEN
        RAISE WARNING 'Test failed: expected %, got %', expected_value, v_count;
    END IF;
END $$;
```

## Monitoring

### Key Metrics

| Metric | Query |
|--------|-------|
| Records per tenant | `SELECT tenant_id, COUNT(*) FROM raw.raw_shopify_orders GROUP BY tenant_id` |
| Data age | `SELECT tenant_id, MIN(extracted_at), MAX(extracted_at) FROM raw.raw_shopify_orders GROUP BY tenant_id` |
| Retention backlog | `SELECT * FROM raw.preview_retention_cleanup()` |
| Recent pipeline runs | `SELECT * FROM raw.raw_pipeline_runs WHERE started_at > NOW() - INTERVAL '24 hours'` |

### RLS Audit Events

```sql
SELECT * FROM raw.raw_rls_audit_log
WHERE event_timestamp > NOW() - INTERVAL '1 hour'
ORDER BY event_timestamp DESC;
```

## Troubleshooting

### No Data Returned

1. Check tenant context is set: `SELECT current_setting('app.tenant_id', true)`
2. Verify tenant has data: Query as admin role
3. Check RLS is enabled: `SELECT rowsecurity FROM pg_tables WHERE tablename = 'raw_shopify_orders'`

### Performance Issues

1. Verify indexes exist: `\di raw.*`
2. Check query uses tenant_id filter: `EXPLAIN ANALYZE SELECT ...`
3. Consider partitioning for very large tables

### RLS Policy Issues

```sql
-- Check all policies
SELECT * FROM pg_policies WHERE schemaname = 'raw';

-- Verify policy expressions
SELECT policyname, qual FROM pg_policies
WHERE tablename = 'raw_shopify_orders';
```

## File Reference

| File | Purpose |
|------|---------|
| `db/migrations/raw_schema.sql` | Table definitions and indexes |
| `db/rls/raw_rls.sql` | RLS policies and roles |
| `db/retention/raw_cleanup.sql` | Retention cleanup functions |
| `db/tests/test_raw_rls_isolation.sql` | Security test suite |
| `docs/RAW_SCHEMA.md` | This documentation |

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-26 | Initial release - core tables, RLS, retention |
