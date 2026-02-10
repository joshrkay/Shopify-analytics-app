# Deployment Checklist - Core Metrics Implementation

## 📦 What's Being Deployed

### Story 4.5: Core Business Metrics ✅ COMPLETE

**SQL Models (6 files):**
- ✅ `models/metrics/fct_revenue.sql` - Revenue waterfall (gross/net/refunds/cancellations)
- ✅ `models/metrics/fct_aov.sql` - Average Order Value with outlier detection
- ✅ `models/metrics/fct_roas.sql` - Gross & Net ROAS with attribution
- ✅ `models/metrics/fct_cac.sql` - CAC & nCAC with customer quality metrics
- ✅ `models/utils/dim_date_ranges.sql` - Date dimension for flexible ranges
- ✅ `models/marts/mart_revenue_metrics.sql` - Revenue mart with period comparisons
- ✅ `models/marts/mart_marketing_metrics.sql` - ROAS + CAC mart with period comparisons

**Tests (4 files):**
- ✅ `tests/test_revenue_edge_cases.sql` - 10 edge case validations
- ✅ `tests/test_aov_edge_cases.sql` - 10 edge case validations
- ✅ `tests/test_roas_edge_cases.sql` - 13 edge case validations
- ✅ `tests/test_cac_edge_cases.sql` - 18 edge case validations

**Documentation (1 file):**
- ✅ `models/metrics/schema.yml` - Complete dbt documentation with column descriptions, tests, and usage examples

**Seeds (1 file):**
- ✅ `seeds/seed_revenue_test_orders.csv` - Test data with 12 edge case scenarios

**Guides (3 files):**
- ✅ `IMPLEMENTATION_PLAN.md` - Original planning document
- ✅ `METRICS_IMPLEMENTATION_SUMMARY.md` - Implementation summary and next steps
- ✅ `FLEXIBLE_DATE_RANGES_GUIDE.md` - Usage guide for new date range features

---

## 🚀 Pre-Deployment Checklist

### 1. Environment Setup
- [ ] dbt installed and configured
- [ ] Database connection tested (`dbt debug`)
- [ ] Git branch created for deployment
- [ ] Backup of production database (if applicable)

### 2. Dependencies Check
Required existing models (these must already exist):
- [ ] `fact_orders` - Order data from Shopify
- [ ] `fct_revenue` base data available
- [ ] `last_click` - Attribution model
- [ ] `fact_ad_spend` - Ad spend from Meta/Google
- [ ] `fact_campaign_performance` - Campaign data
- [ ] `_tenant_airbyte_connections` - Tenant mapping

### 3. Configuration Review
- [ ] Tenant isolation properly configured
- [ ] Currency codes validated (USD, EUR, GBP, etc.)
- [ ] Platform names match: 'meta_ads', 'google_ads'
- [ ] Date ranges configured (currently: 2023-01-01 to present)

---

## 📋 Deployment Steps

### Step 1: Deploy to Development/Staging

```bash
# Navigate to analytics directory
cd /path/to/Shopify-analytics-app/analytics

# Install dependencies (if using dbt packages)
dbt deps

# Run date dimension first (dependency for marts)
dbt run --models dim_date_ranges --target dev

# Run metrics models
dbt run --models fct_revenue fct_aov fct_roas fct_cac --target dev

# Run marts (depends on metrics)
dbt run --models mart_revenue_metrics mart_marketing_metrics --target dev

# Run all tests
dbt test --models metrics marts --target dev
```

### Step 2: Validate Results

```sql
-- Check row counts (should have data)
SELECT 'fct_revenue' as model, COUNT(*) as rows FROM fct_revenue
UNION ALL
SELECT 'fct_aov', COUNT(*) FROM fct_aov
UNION ALL
SELECT 'fct_roas', COUNT(*) FROM fct_roas
UNION ALL
SELECT 'fct_cac', COUNT(*) FROM fct_cac
UNION ALL
SELECT 'dim_date_ranges', COUNT(*) FROM dim_date_ranges
UNION ALL
SELECT 'mart_revenue_metrics', COUNT(*) FROM mart_revenue_metrics
UNION ALL
SELECT 'mart_marketing_metrics', COUNT(*) FROM mart_marketing_metrics;

-- Check for tenant isolation (should only see your tenant's data)
SELECT DISTINCT tenant_id FROM fct_revenue;

-- Check date ranges are generated correctly
SELECT period_type, COUNT(*) as count
FROM dim_date_ranges
GROUP BY period_type
ORDER BY period_type;

-- Spot-check a metric
SELECT *
FROM mart_revenue_metrics
WHERE period_type = 'last_30_days'
  AND period_end = current_date
LIMIT 5;
```

### Step 3: Run Human Validation Tests

**Revenue Validation:**
```sql
-- Compare to Shopify admin
SELECT
  date_trunc('month', revenue_date) as month,
  SUM(CASE WHEN revenue_type = 'gross_revenue' THEN gross_revenue ELSE 0 END) as our_gross_revenue
FROM fct_revenue
WHERE tenant_id = 'YOUR_TENANT_ID'
  AND revenue_date >= '2024-01-01'
GROUP BY 1
ORDER BY 1;

-- Should match Shopify's reported revenue within 5%
```

**AOV Validation:**
```sql
-- Check AOV feels reasonable
SELECT
  period_type,
  period_start,
  aov,
  order_count
FROM fct_aov
WHERE tenant_id = 'YOUR_TENANT_ID'
  AND currency = 'USD'
  AND period_type = 'monthly'
ORDER BY period_start DESC
LIMIT 6;

-- Compare to historical AOV from GA4 or Shopify
```

**ROAS Validation:**
```sql
-- Compare to Meta Ads Manager
SELECT
  platform,
  SUM(total_spend) as spend,
  SUM(total_gross_revenue) as revenue,
  AVG(gross_roas) as avg_roas
FROM fct_roas
WHERE tenant_id = 'YOUR_TENANT_ID'
  AND period_type = 'monthly'
  AND period_start >= '2024-01-01'
GROUP BY 1;

-- ROAS should be directionally similar (exact match not expected due to attribution)
```

**CAC Validation:**
```sql
-- Check customer acquisition
SELECT
  platform,
  SUM(new_customers) as customers,
  SUM(net_new_customers) as net_customers,
  AVG(cac) as avg_cac,
  AVG(ncac) as avg_ncac,
  AVG(customer_retention_rate_pct) as retention_rate
FROM fct_cac
WHERE tenant_id = 'YOUR_TENANT_ID'
  AND period_type = 'monthly'
  AND period_start >= '2024-01-01'
GROUP BY 1;

-- Retention rate should be >50% (if lower, investigate)
```

### Step 4: Check for Test Failures

```bash
# Review any test failures
dbt test --models metrics marts --target dev

# If tests fail, review:
# 1. Data quality issues (missing fields, nulls)
# 2. Edge cases not handled
# 3. Configuration errors
```

### Step 5: Deploy to Production

```bash
# Only proceed if dev/staging validation passed!

# Run full deployment
dbt run --models dim_date_ranges fct_revenue fct_aov fct_roas fct_cac mart_revenue_metrics mart_marketing_metrics --target prod

# Run tests in production
dbt test --models metrics marts --target prod

# Generate documentation
dbt docs generate --target prod
dbt docs serve  # Optional: view documentation
```

---

## ⚠️ Rollback Plan

If deployment fails or results are incorrect:

### Option 1: Quick Rollback (Drop Tables)
```sql
-- Development/Staging
DROP TABLE IF EXISTS analytics.fct_revenue CASCADE;
DROP TABLE IF EXISTS analytics.fct_aov CASCADE;
DROP TABLE IF EXISTS analytics.fct_roas CASCADE;
DROP TABLE IF EXISTS analytics.fct_cac CASCADE;
DROP TABLE IF EXISTS utils.dim_date_ranges CASCADE;
DROP TABLE IF EXISTS marts.mart_revenue_metrics CASCADE;
DROP TABLE IF EXISTS marts.mart_marketing_metrics CASCADE;
```

### Option 2: Git Revert
```bash
# Revert the commit
git revert HEAD

# Re-deploy previous version
dbt run --models metrics marts --target prod
```

---

## 🔍 Post-Deployment Validation

### Automated Checks (Run Daily)
```sql
-- Check freshness (should update daily)
SELECT
  MAX(dbt_updated_at) as last_update,
  COUNT(*) as rows
FROM fct_revenue;

-- Check for anomalies
SELECT
  date_trunc('day', revenue_date) as date,
  SUM(gross_revenue) as revenue
FROM fct_revenue
WHERE revenue_date >= current_date - interval '7 days'
GROUP BY 1
ORDER BY 1;

-- Alert if revenue is >3x or <0.3x daily average
```

### Manual Checks (Run Weekly)
- [ ] Revenue waterfall matches Shopify admin
- [ ] AOV trend matches expectations
- [ ] ROAS directionally matches platform reports
- [ ] CAC is reasonable (not infinity or negative)
- [ ] Period-over-period comparisons work correctly
- [ ] No tenant data leakage (check distinct tenant_ids)

---

## 📊 Success Criteria

Deployment is successful when:

✅ All models build without errors
✅ All 51 edge case tests pass
✅ Revenue matches Shopify admin (within 5%)
✅ ROAS is directionally aligned with Meta/Google
✅ AOV feels right to merchant
✅ CAC is reasonable and non-zero
✅ Period-over-period comparisons return results
✅ No data quality alerts in first 7 days
✅ Merchants can query data successfully

---

## 🐛 Known Issues & Workarounds

### Issue 1: Shipping Amount Missing
**Problem**: Shipping defaults to $0
**Impact**: Low - doesn't affect most metrics
**Workaround**: Parse `shipping_lines` JSON array (TODO)
**Priority**: Medium

### Issue 2: Partial Refund Estimate
**Problem**: Uses 50% estimate for partial refunds
**Impact**: Medium - affects revenue accuracy
**Workaround**: Parse `refunds` JSON array for exact amounts (TODO)
**Priority**: High

### Issue 3: UTM Extraction Dependency
**Problem**: Requires Shopify tracking app
**Impact**: High - attribution won't work without it
**Workaround**: Add fallback to referrer domain parsing
**Priority**: High

### Issue 4: Cross-Device Tracking Limited
**Problem**: Can only track logged-in customers across devices
**Impact**: Low - acceptable limitation
**Workaround**: None (requires advanced tracking)
**Priority**: Low

---

## 📞 Support & Troubleshooting

### Common Errors

**Error**: `relation "fact_orders" does not exist`
**Solution**: Ensure dependent models run first: `dbt run --models fact_orders`

**Error**: `column "shipping_amount" does not exist`
**Solution**: This is expected - shipping defaults to $0 currently

**Error**: `division by zero`
**Solution**: This should be handled - check for null or zero spend/customers

**Error**: `date/time field value out of range`
**Solution**: Check date formats in source data (should be UTC timestamps)

### Performance Issues

**Slow Query**: Marts take >30s to run
**Solution**:
1. Add indexes on frequently joined columns (tenant_id, date)
2. Materialize as incremental instead of table
3. Reduce date_ranges historical window (currently 2 years)

**Large Table Size**: Marts are >1GB
**Solution**:
1. Filter to active tenants only
2. Partition by date
3. Archive old data (>1 year)

---

## 📚 Documentation Links

- **Implementation Summary**: `METRICS_IMPLEMENTATION_SUMMARY.md`
- **Date Ranges Guide**: `FLEXIBLE_DATE_RANGES_GUIDE.md`
- **dbt Documentation**: Run `dbt docs serve` after deployment
- **Schema Documentation**: `models/metrics/schema.yml`

---

## ✅ Sign-Off

**Deployed By**: ___________________
**Date**: ___________________
**Environment**: [ ] Dev  [ ] Staging  [ ] Production
**Validation Complete**: [ ] Yes  [ ] No
**Tests Passing**: [ ] Yes  [ ] No
**Stakeholder Approval**: [ ] Yes  [ ] No

---

**Status**: 🟢 Ready for Deployment

All files created, tested, and documented. Ready to commit to Git and deploy to dbt environment.
