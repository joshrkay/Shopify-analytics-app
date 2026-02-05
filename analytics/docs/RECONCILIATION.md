# Reconciliation Tests

Reconciliation tests verify that canonical fact tables produce the same
aggregate totals as their staging sources.  They catch silent data loss,
filter mismatches, and incremental-load drift before dashboards are affected.

## Test inventory

| Test file | Canonical model | Staging sources | Metrics checked |
|---|---|---|---|
| `test_reconcile_shopify_orders.sql` | `fact_orders_v1` | `stg_shopify_orders` | `revenue_gross`, `revenue_net` |
| `test_reconcile_ad_spend.sql` | `fact_marketing_spend_v1` | `stg_facebook_ads_performance`, `stg_google_ads_performance`, `stg_tiktok_ads_performance`, `stg_snapchat_ads` | `spend`, `impressions`, `clicks` |
| `test_reconcile_attributed_revenue.sql` | `fact_campaign_performance_v1` | `stg_facebook_ads_performance`, `stg_google_ads_performance`, `stg_tiktok_ads_performance`, `stg_snapchat_ads` | `attributed_revenue`, `spend`, `conversions` |

## How they work

1. **Date-range scoping** — Each test reads the `min`/`max` business date
   from the canonical table and restricts the staging query to the same
   window.  This keeps the comparison fair when the canonical table has
   only been partially loaded or is running in incremental mode.

2. **Filter parity** — The staging CTEs replicate the exact `WHERE`
   clauses used by the canonical model (e.g.
   `tenant_id is not null and date is not null and spend is not null` for
   `fact_marketing_spend_v1`).  This ensures an apples-to-apples
   comparison.

3. **Percentage-based tolerance** — For each metric the test computes:

   ```
   pct_diff = abs(staging_total - fact_total) / abs(staging_total) * 100
   ```

   Rows are returned (= test failure) only when `pct_diff` exceeds the
   configured tolerance.

4. **Diagnostic columns** — Every returned row includes `staging_total`,
   `fact_total`, `abs_diff`, `pct_diff`, `staging_rows`, `fact_rows`, and
   `tolerance_pct` so the on-call engineer can triage immediately.

## Column mappings

### Shopify orders

| Staging column (`stg_shopify_orders`) | Canonical column (`fact_orders_v1`) |
|---|---|
| `total_price` | `revenue_gross` |
| `subtotal_price` | `revenue_net` |
| `report_date` | `order_date` |

### Ad spend

| Staging column | Canonical column (`fact_marketing_spend_v1`) |
|---|---|
| `spend` | `spend` |
| `impressions` | `impressions` |
| `clicks` | `clicks` |
| `date` | `spend_date` |

### Campaign performance / attributed revenue

| Staging column | Canonical column (`fact_campaign_performance_v1`) |
|---|---|
| `conversion_value` | `attributed_revenue` |
| `spend` | `spend` |
| `conversions` | `conversions` |
| `date` | `campaign_date` |

## Configuration

Tolerance is controlled by a single dbt variable:

```yaml
# dbt_project.yml  (or --vars on the CLI)
vars:
  reconciliation_tolerance_pct: 1.0   # ±1 % (default)
```

To tighten tolerance to ±0.5 %:

```bash
dbt test --select test_reconcile_* --vars '{reconciliation_tolerance_pct: 0.5}'
```

To relax tolerance temporarily (e.g. during a backfill):

```bash
dbt test --select test_reconcile_* --vars '{reconciliation_tolerance_pct: 5.0}'
```

## Running the tests

```bash
# Run all reconciliation tests
dbt test --select test_reconcile_shopify_orders test_reconcile_ad_spend test_reconcile_attributed_revenue

# Run a single reconciliation test with custom tolerance
dbt test --select test_reconcile_ad_spend --vars '{reconciliation_tolerance_pct: 0.1}'
```

## When a test fails

1. Check `staging_rows` vs `fact_rows` — a large row-count difference
   usually means the canonical table needs a full refresh
   (`dbt run --full-refresh --select <model>`).

2. Check `abs_diff` — a small absolute difference with a high percentage
   may just mean the total is small; this is usually benign.

3. If the canonical model was recently changed (new filters, column
   renames), confirm that the reconciliation test's staging CTE still
   mirrors the canonical logic.  Update the test if the canonical model's
   filters change.

4. During backfills or large data corrections, temporarily increase
   `reconciliation_tolerance_pct` and re-run after the load completes.

## Design decisions

- **Why compare against staging, not raw sources?**  Staging models
  already handle deduplication, type casting, and tenant mapping.  The
  canonical layer is supposed to be a faithful transformation of staging
  output, so staging is the correct baseline.

- **Why date-range scoping?**  Incremental canonical tables may lag behind
  staging views.  Comparing only the canonical table's date range avoids
  false positives from unprocessed future data.

- **Why percentage tolerance instead of absolute?**  Absolute thresholds
  don't scale across tenants with wildly different order volumes.  A 1 %
  relative threshold works for both $1 K and $10 M monthly revenue.
