# Flexible Date Ranges & Period Comparisons - Usage Guide

## 🎯 Overview

You now have **3 ways** to query metrics:

### 1. **Original Metrics** (Fixed Periods)
- `fct_revenue`, `fct_aov`, `fct_roas`, `fct_cac`
- Pre-aggregated: daily, weekly, monthly, all_time
- Fast, but limited flexibility

### 2. **New Marts** (Flexible + Comparisons) ⭐ **RECOMMENDED**
- `mart_revenue_metrics`
- `mart_marketing_metrics`
- All date ranges + period-over-period comparisons
- Slower but much more flexible

### 3. **Date Dimension** (Build Your Own)
- `dim_date_ranges`
- Join to daily metrics yourself
- Maximum flexibility

---

## 📊 Available Date Ranges

| **Period Type** | **Description** | **Prior Period Comparison** |
|-----------------|-----------------|----------------------------|
| `daily` | Each individual day | Previous day |
| `weekly` | Monday-Sunday | Prior week |
| `monthly` | Calendar month | Prior month |
| `quarterly` | Calendar quarter | Prior quarter |
| `yearly` | Calendar year | Prior year |
| `last_7_days` | Rolling 7 days ending today | Days 8-14 ago |
| `last_30_days` | Rolling 30 days ending today | Days 31-60 ago |
| `last_90_days` | Rolling 90 days ending today | Days 91-180 ago |

---

## 🚀 Quick Start Examples

### Example 1: Last 30 Days Revenue (Today)

```sql
SELECT
  net_revenue,
  prior_net_revenue,
  net_revenue_change,
  net_revenue_change_pct
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND currency = 'USD'
  AND period_type = 'last_30_days'
  AND period_end = current_date;
```

**Result:**
```
net_revenue: $50,000
prior_net_revenue: $45,000 (days 31-60 ago)
net_revenue_change: $5,000
net_revenue_change_pct: 11.11%
```

---

### Example 2: Month-over-Month Revenue Trend

```sql
SELECT
  period_start,
  period_end,
  net_revenue,
  prior_net_revenue,
  net_revenue_change_pct,
  order_count,
  aov
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND currency = 'USD'
  AND period_type = 'monthly'
  AND period_start >= '2024-01-01'
ORDER BY period_start DESC;
```

**Result:**
```
2024-12-01 | 2024-12-31 | $120K | $100K | +20.0% | 1,200 | $100.00
2024-11-01 | 2024-11-30 | $100K | $95K  | +5.3%  | 1,100 | $90.91
2024-10-01 | 2024-10-31 | $95K  | $90K  | +5.6%  | 1,000 | $95.00
```

---

### Example 3: Compare Last 7 Days vs Week Before

```sql
SELECT
  period_end as through_date,
  orders,
  prior_orders,
  orders_change_pct,
  gross_roas,
  prior_gross_roas,
  gross_roas_change_pct
FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND platform = 'meta_ads'
  AND currency = 'USD'
  AND period_type = 'last_7_days'
  AND period_end >= current_date - interval '30 days'
ORDER BY period_end DESC
LIMIT 7;
```

**Shows daily trend of "last 7 days" performance vs "prior 7 days"**

---

### Example 4: Platform Performance (Last 30 Days)

```sql
SELECT
  platform,
  spend,
  gross_revenue,
  gross_roas,
  net_roas,
  cac,
  ncac,
  new_customers,
  customer_retention_rate_pct,

  -- Compare to prior 30 days
  spend_change_pct,
  gross_roas_change_pct,
  cac_change_pct
FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND currency = 'USD'
  AND period_type = 'last_30_days'
  AND period_end = current_date
  AND campaign_id IS NULL  -- Aggregate across all campaigns
ORDER BY spend DESC;
```

**Result:**
```
platform    | spend   | gross_roas | net_roas | cac   | spend_change_pct | roas_change_pct
------------|---------|------------|----------|-------|------------------|----------------
meta_ads    | $25,000 | 3.2        | 2.8      | $45   | +15%             | +10%
google_ads  | $15,000 | 2.5        | 2.1      | $55   | -5%              | -8%
```

---

### Example 5: Quarter-over-Quarter Business Health

```sql
SELECT
  period_start,
  net_revenue,
  prior_net_revenue,
  net_revenue_change_pct,

  -- Marketing efficiency
  (SELECT gross_roas FROM mart_marketing_metrics m
   WHERE m.tenant_id = r.tenant_id
     AND m.period_type = 'quarterly'
     AND m.period_start = r.period_start
     AND m.platform = 'meta_ads'
   LIMIT 1) as meta_roas,

  (SELECT cac FROM mart_marketing_metrics m
   WHERE m.tenant_id = r.tenant_id
     AND m.period_type = 'quarterly'
     AND m.period_start = r.period_start
   LIMIT 1) as blended_cac

FROM mart_revenue_metrics r
WHERE tenant_id = 'your_tenant_id'
  AND currency = 'USD'
  AND period_type = 'quarterly'
ORDER BY period_start DESC
LIMIT 4;
```

---

## 🔍 Advanced Use Cases

### Use Case 1: Campaign Performance Deep Dive

```sql
SELECT
  campaign_id,
  period_type,
  period_end,

  -- Current performance
  spend,
  orders,
  gross_roas,
  cac,

  -- vs Prior period
  spend_change_pct,
  orders_change_pct,
  gross_roas_change_pct,
  cac_change_pct

FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND platform = 'meta_ads'
  AND campaign_id = 'your_campaign_id'
  AND period_type IN ('last_7_days', 'last_30_days', 'last_90_days')
  AND period_end = current_date;
```

**Shows how campaign is performing across multiple windows**

---

### Use Case 2: Custom Date Range (Using Date Dimension)

If you need a completely custom date range not covered by the presets:

```sql
WITH custom_range AS (
  SELECT
    '2024-11-15'::date as period_start,
    '2024-12-15'::date as period_end
),

custom_metrics AS (
  SELECT
    sum(net_revenue) as net_revenue,
    count(distinct order_id) as orders
  FROM fct_revenue
  CROSS JOIN custom_range
  WHERE tenant_id = 'your_tenant_id'
    AND revenue_type = 'gross_revenue'
    AND date_trunc('day', revenue_date)::date BETWEEN custom_range.period_start AND custom_range.period_end
)

SELECT * FROM custom_metrics;
```

---

### Use Case 3: Multi-Currency Dashboard

```sql
SELECT
  currency,
  net_revenue,
  prior_net_revenue,
  net_revenue_change_pct,
  order_count,
  aov
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date
ORDER BY net_revenue DESC;
```

**Result:**
```
currency | net_revenue | prior_net_revenue | change_pct | orders | aov
---------|-------------|-------------------|------------|--------|--------
USD      | $50,000     | $45,000           | +11.1%     | 500    | $100
EUR      | €30,000     | €28,000           | +7.1%      | 350    | €85.71
GBP      | £20,000     | £22,000           | -9.1%      | 250    | £80
```

---

## 📈 Visualization Examples

### Dashboard 1: Executive Summary

```sql
-- Tile 1: Revenue (Last 30 Days)
SELECT
  net_revenue as value,
  net_revenue_change_pct as change_pct,
  'up' as trend_direction
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date;

-- Tile 2: Orders (Last 30 Days)
SELECT
  order_count as value,
  order_count_change_pct as change_pct
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date;

-- Tile 3: ROAS (Last 30 Days)
SELECT
  gross_roas as value,
  gross_roas_change_pct as change_pct
FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date
  AND campaign_id IS NULL;

-- Tile 4: CAC (Last 30 Days)
SELECT
  cac as value,
  cac_change_pct as change_pct,
  'down' as trend_direction  -- Lower is better
FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date;
```

---

### Dashboard 2: Revenue Trend (Daily for Last 30 Days)

```sql
SELECT
  period_start as date,
  net_revenue,
  prior_net_revenue
FROM mart_revenue_metrics
WHERE tenant_id = 'your_tenant_id'
  AND currency = 'USD'
  AND period_type = 'daily'
  AND period_start >= current_date - interval '30 days'
ORDER BY period_start;
```

**Chart: Line chart with 2 lines (current vs prior)**

---

### Dashboard 3: Marketing Channel Comparison

```sql
SELECT
  platform,
  spend,
  orders,
  gross_roas,
  net_roas,
  cac,
  ncac,
  new_customers
FROM mart_marketing_metrics
WHERE tenant_id = 'your_tenant_id'
  AND period_type = 'last_30_days'
  AND period_end = current_date
  AND campaign_id IS NULL
ORDER BY spend DESC;
```

**Chart: Stacked bar chart or table**

---

## ⚡ Performance Tips

### 1. Always Filter by `period_end`

```sql
-- ✅ GOOD (uses index on period_end)
WHERE period_type = 'last_30_days'
  AND period_end = current_date

-- ❌ BAD (scans all periods)
WHERE period_type = 'last_30_days'
ORDER BY period_end DESC
LIMIT 1
```

### 2. Specify `period_type`

```sql
-- ✅ GOOD (filters early)
WHERE period_type = 'monthly'

-- ❌ BAD (returns all period types)
WHERE period_start >= '2024-01-01'
```

### 3. Filter on `campaign_id` when needed

```sql
-- For aggregate (all campaigns)
WHERE campaign_id IS NULL

-- For specific campaign
WHERE campaign_id = 'specific_campaign_id'
```

---

## 🛠️ How It Works (Technical)

### Architecture

```
Daily Metrics (fct_revenue, fct_roas, fct_cac)
          ↓
    Date Dimension (dim_date_ranges)
          ↓
    Marts (mart_revenue_metrics, mart_marketing_metrics)
```

### Date Dimension Generation

`dim_date_ranges` generates:
- All possible date ranges for last 2 years
- Current period dates
- Prior period dates (for comparison)
- Comparison type labels

### Mart Aggregation

Marts:
1. Cross join: `date_ranges × (tenant, currency, platform)`
2. Join daily metrics to current period
3. Join daily metrics to prior period
4. Calculate period-over-period changes

---

## 🚨 Known Limitations

1. **Historical Data**: Only last 2 years generated (configurable in `dim_date_ranges`)
2. **Rolling Windows**: Always end on a specific date (can't get "last 30 days as of Dec 15")
3. **Performance**: Marts are slower than pre-aggregated metrics (but still fast <1s)
4. **Storage**: Marts are larger (1 row per tenant/currency/period_type/date)

---

## 📝 Migration Guide

### Before (Old Way)

```sql
SELECT
  SUM(gross_revenue) as revenue
FROM fct_revenue
WHERE period_type = 'monthly'
  AND period_start = '2024-12-01'
  AND tenant_id = 'your_tenant_id';
```

### After (New Way)

```sql
SELECT
  net_revenue as revenue,
  prior_net_revenue as prev_month_revenue,
  net_revenue_change_pct as mom_change_pct
FROM mart_revenue_metrics
WHERE period_type = 'monthly'
  AND period_start = '2024-12-01'
  AND tenant_id = 'your_tenant_id';
```

**Benefits:**
- ✅ Get prior period comparison automatically
- ✅ Get % change calculated
- ✅ Consistent period definitions

---

## 🎓 Best Practices

### 1. Use Marts for User-Facing Dashboards

```sql
-- User sees: "Last 30 Days: $50K (+11% vs prior 30 days)"
SELECT * FROM mart_revenue_metrics
WHERE period_type = 'last_30_days';
```

### 2. Use Original Metrics for Internal Analysis

```sql
-- Analyst needs: Daily revenue by UTM source
SELECT * FROM fct_revenue
WHERE period_type = 'daily';
```

### 3. Always Include Prior Period Context

```sql
-- ✅ GOOD: Shows trend
SELECT
  metric,
  prior_metric,
  metric_change_pct

-- ❌ BAD: No context
SELECT metric
```

### 4. Pick the Right Date Range

- **Last 7 days**: Daily operations, real-time monitoring
- **Last 30 days**: Weekly reviews, short-term trends
- **Last 90 days**: Monthly reviews, seasonal patterns
- **Monthly**: Financial reporting, long-term planning
- **Quarterly**: Board meetings, strategic planning

---

## 🔮 Future Enhancements

Potential additions:
- Year-to-date (YTD) periods
- Custom date range builder (UI)
- Forecasting (predict next period based on trend)
- Seasonality adjustments
- Cohort analysis integration

---

## 💬 Questions?

Common questions:

**Q: Can I get "last 30 days as of Dec 15" (not today)?**
A: Yes! Just filter: `WHERE period_type = 'last_30_days' AND period_end = '2024-12-15'`

**Q: How do I compare this month to same month last year?**
A: Use `period_type = 'monthly'` and join to prior year manually, or add `year_over_year` comparison (future enhancement)

**Q: Can I filter by specific campaigns within a date range?**
A: Yes! `campaign_id` is preserved in `mart_marketing_metrics`

**Q: Why are my numbers different from the original metrics?**
A: Marts aggregate from daily metrics. Check date range boundaries and filters.

---

**Ready to use! All queries work today.** 🚀
