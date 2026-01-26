# dbt Models

This directory contains dbt models for the Shopify Analytics app.

## Directory Structure

- `staging/`: Staging models that clean and prepare raw data
- `facts/`: Fact tables for analytics

## Backfill Support

All models should support backfill parameters using the `backfill_date_range` macro.

### Example Model Pattern

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

### Usage

Models are automatically parameterized when backfill variables are provided:

- `backfill_start_date`: Filter records where `created_at >= start_date`
- `backfill_end_date`: Filter records where `created_at <= end_date`
- `tenant_id`: Filter records where `tenant_id = tenant_id`

If variables are not provided (null/empty), models run normally without date/tenant filtering.

## Models to Update

The following models need to be updated to support backfill parameters:

1. Staging models (in `staging/` directory)
2. Fact models (in `facts/` directory)

Each model should:
- Use incremental materialization where appropriate
- Include the `backfill_date_range` macro in WHERE clause
- Ensure tenant_id filtering is applied when tenant_id variable is provided
