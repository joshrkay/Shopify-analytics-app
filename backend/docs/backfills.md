# dbt Backfills Guide

This guide explains how to run dbt backfills for historical data reprocessing and tenant-scoped data rebuilds.

## Overview

dbt backfills allow you to:
- Reprocess historical data for specific date ranges
- Rebuild analytics for specific tenants
- Fix data quality issues by re-running transformations

All backfill executions are logged to the `backfill_executions` table for audit purposes.

## Prerequisites

1. **Database Access**: Ensure `DATABASE_URL` environment variable is set
2. **dbt Configuration**: dbt profiles.yml must be configured (see `analytics/profiles.yml`)
3. **Model Support**: All models must use the `backfill_date_range` macro (see below)

## Running Backfills

### Basic Usage

Run a backfill for a specific date range:

```bash
python -m scripts.run_dbt_backfill \
    --start-date 2024-01-01 \
    --end-date 2024-01-31
```

### Tenant-Scoped Backfills

Run a backfill for a specific tenant:

```bash
python -m scripts.run_dbt_backfill \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --tenant-id tenant-123
```

**Security Note**: Tenant-scoped backfills ensure data isolation. The `tenant_id` filter is applied at the SQL level to prevent cross-tenant data access.

### Selective Model Backfills

Run backfills for specific models only:

```bash
python -m scripts.run_dbt_backfill \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --models staging+ facts+
```

Or specific models:

```bash
python -m scripts.run_dbt_backfill \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --models staging.fact_orders staging.fact_customers
```

## Command-Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--start-date` | Yes | Start date for backfill (YYYY-MM-DD format) |
| `--end-date` | Yes | End date for backfill (YYYY-MM-DD format) |
| `--tenant-id` | No | Tenant ID for tenant-scoped backfill |
| `--models` | No | Space-separated list of models to backfill (dbt selection syntax) |
| `--database-url` | No | Database URL (overrides DATABASE_URL env var) |

## Date Range Best Practices

1. **Small Increments**: For large date ranges, consider running backfills in smaller chunks (e.g., monthly or weekly)
2. **Validation**: Always validate results after backfills, especially for critical fact tables
3. **Idempotency**: Backfills use incremental materialization - safe to re-run if needed
4. **Time Windows**: Avoid backfilling very recent data (last 24 hours) as it may be incomplete

### Example: Monthly Backfill

```bash
# Backfill January 2024
python -m scripts.run_dbt_backfill \
    --start-date 2024-01-01 \
    --end-date 2024-01-31

# Backfill February 2024
python -m scripts.run_dbt_backfill \
    --start-date 2024-02-01 \
    --end-date 2024-02-29
```

## Audit Logging

All backfill executions are logged to the `backfill_executions` table with:

- Execution ID (UUID)
- Tenant ID (if tenant-scoped)
- Date range (start_date, end_date)
- Models executed
- Status (running, completed, failed)
- Duration (seconds)
- Records processed (if available)
- Error message (if failed)

### Querying Backfill History

```sql
-- View recent backfills
SELECT 
    id,
    tenant_id,
    start_date,
    end_date,
    status,
    duration_seconds,
    created_at
FROM backfill_executions
ORDER BY created_at DESC
LIMIT 10;

-- View failed backfills
SELECT *
FROM backfill_executions
WHERE status = 'failed'
ORDER BY created_at DESC;
```

## Troubleshooting

### Common Issues

#### 1. dbt Connection Errors

**Error**: `Connection refused` or `Authentication failed`

**Solution**: 
- Verify `DATABASE_URL` is set correctly
- Check dbt `profiles.yml` configuration
- Ensure database is accessible from your network

#### 2. Date Range Validation Errors

**Error**: `start_date must be <= end_date`

**Solution**: Ensure start_date is before or equal to end_date

#### 3. Model Compilation Errors

**Error**: `Compilation error in model X`

**Solution**:
- Run `dbt compile` manually to see detailed errors
- Check that models use the `backfill_date_range` macro correctly
- Verify SQL syntax in affected models

#### 4. Tenant Isolation Errors

**Error**: Unexpected data in tenant-scoped backfill

**Solution**:
- Verify `tenant_id` parameter is correct
- Check that source tables have proper tenant_id filtering
- Review model SQL to ensure tenant_id is applied at all joins

### Debugging Steps

1. **Test Connection**:
   ```bash
   cd analytics
   dbt debug
   ```

2. **Compile Models**:
   ```bash
   cd analytics
   dbt compile --vars '{"backfill_start_date": "2024-01-01", "backfill_end_date": "2024-01-31"}'
   ```

3. **Dry Run**:
   ```bash
   dbt run --select staging+ --vars '{"backfill_start_date": "2024-01-01", "backfill_end_date": "2024-01-31"}' --dry-run
   ```

## Safety Considerations

### Idempotency

Backfills are designed to be idempotent:
- Uses incremental materialization
- Safe to re-run if interrupted
- No duplicate records created on re-run

### Data Integrity

- Backfills do not delete existing data
- They append or update based on incremental logic
- Always verify results after large backfills

### Performance

- Large date ranges may take significant time
- Consider running during off-peak hours
- Monitor database performance during backfills

### Tenant Isolation

- Tenant-scoped backfills enforce strict isolation
- Cross-tenant data access is prevented at SQL level
- Always verify tenant_id filtering in model SQL

## Model Implementation

Models must support backfill parameters using the `backfill_date_range` macro:

```sql
{{ config(materialized='incremental') }}

SELECT 
    id,
    tenant_id,
    created_at,
    -- other columns
FROM {{ ref('source_table') }}
WHERE 1=1
  {{ backfill_date_range(var('backfill_start_date'), var('backfill_end_date'), var('tenant_id')) }}
```

The macro automatically:
- Filters by date range if `backfill_start_date` and `backfill_end_date` are provided
- Filters by tenant if `tenant_id` is provided
- Returns empty string (no filtering) if variables are null/empty

## Related Documentation

- [dbt Project Configuration](../analytics/dbt_project.yml)
- [Backfill Macro](../analytics/macros/backfill.sql)
- [BackfillExecution Model](../src/models/backfill_execution.py)
