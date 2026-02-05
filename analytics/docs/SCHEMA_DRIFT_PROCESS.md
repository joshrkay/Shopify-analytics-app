# Schema Drift Detection & Approval Process

## What is Schema Drift?

Schema drift occurs when a data source (e.g. Shopify, Meta Ads) adds new fields
to its API responses. Airbyte ingests these into the raw layer automatically.
However, using new fields in staging or downstream models without review can
break dashboards, invalidate metrics, or expose PII.

**Rule:** New columns in raw tables are allowed. They cannot be used in
staging or canonical models without explicit approval.

## How It Works

```
Raw Layer (allowed)          Staging Layer (gated)
========================     ========================
_airbyte_raw_shopify_orders  stg_shopify_orders
  _airbyte_data (JSONB)        order_id        <-- must be in allowlist
    -> new_field appears        new_field       <-- BLOCKED until approved
```

1. **Allowlist files** in `analytics/governance/` define which columns each
   staging model is permitted to output.
2. **A dbt macro** (`macros/assert_columns_approved.sql`) reads the allowlist
   at compile time and compares it against the actual columns in the database.
3. **A dbt test** (`tests/test_schema_drift_guard.sql`) calls the macro for
   every governed model. If any column exists in the model but not in the
   allowlist, the test fails with a clear error message.

## Allowlist Files

| Source    | Allowlist File                                |
|-----------|-----------------------------------------------|
| Shopify   | `governance/approved_columns_shopify.yml`     |
| Facebook  | `governance/approved_columns_facebook.yml`    |
| Google    | `governance/approved_columns_google.yml`      |
| TikTok    | `governance/approved_columns_tiktok.yml`      |
| Email     | `governance/approved_columns_email.yml`       |

Each file has this structure:

```yaml
source: shopify

models:
  stg_shopify_orders:
    - tenant_id
    - order_id
    - order_name
    # ... every approved column
```

## Step-by-Step: Adding a New Column

### Scenario
A new field `discount_codes` has appeared in Shopify order data. You want to
use it in `stg_shopify_orders`.

### Steps

**1. Confirm the column exists in raw data**

```sql
-- Check if the field is present in the raw JSONB
SELECT _airbyte_data->>'discount_codes'
FROM airbyte_raw._airbyte_raw_shopify_orders
LIMIT 5;
```

**2. Add the column to the staging model SQL**

Edit `analytics/models/staging/shopify/stg_shopify_orders.sql` and add the
column extraction logic in the appropriate CTE.

**3. Add the column to the allowlist**

```bash
# Open the allowlist file
cd analytics
nano governance/approved_columns_shopify.yml
```

Add the column name under the correct model:

```yaml
models:
  stg_shopify_orders:
    - tenant_id
    - order_id
    # ... existing columns ...
    - discount_codes    # <-- ADD THIS LINE
```

**4. Add the column to the schema.yml contract**

Edit `analytics/models/staging/schema.yml` and add the column definition:

```yaml
- name: discount_codes
  description: Discount codes applied to the order
```

**5. Run the drift guard test locally**

```bash
cd analytics
dbt test -s test_schema_drift_guard
```

Expected output on success:
```
Completed successfully
Done. PASS=1 WARN=0 ERROR=0 SKIP=0 TOTAL=1
```

If it fails, the output will show exactly which column is unapproved:
```
FAIL 1
model_name: stg_shopify_orders
unapproved_column: discount_codes
allowlist_file: governance/approved_columns_shopify.yml
error_message: SCHEMA DRIFT DETECTED: Column "discount_codes" in model
  "stg_shopify_orders" is not in the approved allowlist...
```

**6. Commit and open a PR**

```bash
git checkout -b feat/add-discount-codes-to-shopify
git add governance/approved_columns_shopify.yml
git add models/staging/shopify/stg_shopify_orders.sql
git add models/staging/schema.yml
git commit -m "feat: add discount_codes to stg_shopify_orders allowlist"
git push -u origin feat/add-discount-codes-to-shopify
```

**7. Get approval and merge**

The PR requires review from the Analytics Tech Lead. The reviewer checks:
- [ ] Column has a clear business purpose
- [ ] No PII exposure (email, phone, address without hashing)
- [ ] Column is documented in schema.yml
- [ ] Allowlist file is updated
- [ ] dbt test passes

## Running the Drift Guard

```bash
# Run only the schema drift test
dbt test -s test_schema_drift_guard

# Run all tests (drift guard is included)
dbt test
```

## Troubleshooting

### "Column X is not in the approved allowlist"

This is the expected failure when drift is detected. Follow the steps above
to add the column to the allowlist via PR.

### "Relation does not exist"

The model has not been materialized yet. Run `dbt run -s <model_name>` first,
then re-run the test.

### "No columns found for model X"

The allowlist YAML may have a typo in the model name. Verify the model name
in the allowlist matches the dbt model name exactly.

## FAQ

**Q: Does this block raw data ingestion?**
No. Raw tables are not governed by this check. Airbyte can ingest any columns
into `_airbyte_data`. The gate only applies to staging and downstream models.

**Q: What if a column is renamed?**
Remove the old name and add the new name in the allowlist. Both changes go
through the same PR review process.

**Q: Can I temporarily bypass the check?**
No. The test runs as part of `dbt test` in CI. Bypassing it would require
disabling the test, which violates the project's `.cursorrules` policy
("no disabling tests").

**Q: Who approves allowlist changes?**
The Analytics Tech Lead, per the sign-off rules in
`config/governance/pre_deploy_validation.yaml`.
