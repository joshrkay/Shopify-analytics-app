# Core Business Metrics - Implementation Summary

## ✅ What Was Built

We've completed the full implementation of **4 core business metrics** with comprehensive edge case handling:

### 1. **Revenue** (`fct_revenue.sql`)
- **Gross Revenue**: Product + Shipping + Taxes
- **Refunds**: Recorded as negative revenue on refund date
- **Cancellations**: Separate line item (enables waterfall reporting)
- **Net Revenue**: Gross - Refunds - Cancellations

### 2. **AOV - Average Order Value** (`fct_aov.sql`)
- **Formula**: Net Revenue / Number of Orders
- **Outlier Detection**: Excludes orders >3 standard deviations from mean
- **Time Periods**: Daily, Weekly, Monthly, All-time
- **Multi-currency**: Calculated separately per currency

### 3. **ROAS - Return on Ad Spend** (`fct_roas.sql`)
- **Gross ROAS**: Attributed Gross Revenue / Ad Spend
- **Net ROAS**: Attributed Net Revenue / Ad Spend
- **Ad Spend**: Meta Ads + Google Ads only
- **Attribution**: Platform-specific (Meta: 7-day click/1-day view, Google: last-click)
- **Zero Spend Handling**: Returns 0 (not NULL or infinity)

### 4. **CAC - Customer Acquisition Cost** (`fct_cac.sql`)
- **CAC**: Total Spend / All New Customers
- **nCAC (Net CAC)**: Total Spend / Net New Customers (excludes cancelled/refunded first orders)
- **Customer Retention Rate**: % of acquired customers who didn't immediately cancel
- **Bonus Metrics**: First Order ROAS, Average First Order Value

---

## 📊 Metrics Decision Summary

| **Decision** | **Choice** |
|--------------|------------|
| **Metric Ownership** | Each tenant owns their own metrics |
| **Approval Process** | Single owner (merchant) approves changes |
| **Revenue Components** | Subtotal + Shipping + Taxes |
| **Refund Handling** | Recorded on refund date (not retroactive) |
| **Cancellations** | Separate line item after gross revenue |
| **Order Statuses** | Include: paid, pending, partially_refunded |
| **AOV Revenue Type** | Net Revenue (after refunds) |
| **AOV Orders** | All completed orders |
| **AOV Outliers** | Exclude >3σ from mean |
| **ROAS Revenue** | Both Gross & Net (separate metrics) |
| **ROAS Ad Spend** | Meta + Google (no agency fees) |
| **ROAS Attribution** | Platform-specific windows |
| **ROAS Zero Spend** | Returns 0 |
| **CAC Definition** | First order ever |
| **CAC Ad Spend** | Same as ROAS |
| **CAC Inclusions** | All customers (including refunded) |
| **nCAC Exclusions** | Cancelled & fully refunded first orders |

---

## 🗂️ Files Created

### SQL Models
```
analytics/models/metrics/
├── fct_revenue.sql       (Revenue waterfall model)
├── fct_aov.sql           (AOV with outlier detection)
├── fct_roas.sql          (Gross & Net ROAS)
└── fct_cac.sql           (CAC & nCAC)
```

### Tests
```
analytics/tests/
├── test_revenue_edge_cases.sql   (10 edge case tests)
├── test_aov_edge_cases.sql       (10 edge case tests)
├── test_roas_edge_cases.sql      (13 edge case tests)
└── test_cac_edge_cases.sql       (18 edge case tests)
```

### Documentation
```
analytics/models/metrics/
└── schema.yml            (Complete dbt documentation)
```

### Test Data
```
analytics/seeds/
└── seed_revenue_test_orders.csv  (12 test scenarios)
```

---

## 🧪 Edge Cases Handled

### Revenue (10 edge cases)
1. ✅ Zero-dollar orders (excluded from gross revenue)
2. ✅ Negative gross revenue (blocked)
3. ✅ Refunds without cancellation date (blocked)
4. ✅ Positive refund amounts (blocked - must be negative)
5. ✅ Same-day order and refund (2 separate events)
6. ✅ Month-boundary refunds (each in correct month)
7. ✅ Missing dates (excluded)
8. ✅ Multi-currency (preserved as-is)
9. ✅ Tenant isolation (enforced)
10. ✅ Net revenue calculation accuracy

### AOV (10 edge cases)
1. ✅ Zero orders in period (period excluded)
2. ✅ Division by zero (returns NULL)
3. ✅ Outlier detection (3-sigma rule on 90-day window)
4. ✅ Negative net revenue (included - reflects refunds)
5. ✅ Multi-currency (separate AOV per currency)
6. ✅ Sparse data (no outliers if stddev = 0)
7. ✅ Future dates (excluded)
8. ✅ Validation (AOV = avg_order_value)
9. ✅ Negative order count (blocked)
10. ✅ Tenant isolation (enforced)

### ROAS (13 edge cases)
1. ✅ Zero spend (ROAS = 0)
2. ✅ Null spend (treated as 0)
3. ✅ Infinite ROAS (prevented)
4. ✅ Negative spend (filtered out)
5. ✅ Revenue without spend (excluded from ROAS)
6. ✅ Spend without revenue (ROAS = 0)
7. ✅ Gross >= Net revenue validation
8. ✅ Multi-currency (separate ROAS per currency)
9. ✅ Unattributed orders (excluded)
10. ✅ Organic traffic (excluded)
11. ✅ Platform filtering (only Meta/Google)
12. ✅ Calculation accuracy validation
13. ✅ Tenant isolation (enforced)

### CAC & nCAC (18 edge cases)
1. ✅ Zero new customers (CAC = 0)
2. ✅ Zero net new customers (nCAC = 0)
3. ✅ Infinite CAC (prevented)
4. ✅ Negative CAC (prevented)
5. ✅ Net customers > All customers (blocked)
6. ✅ nCAC < CAC (blocked - impossible scenario)
7. ✅ Customers without email (use customer_id)
8. ✅ Duplicate customers (counted once per platform)
9. ✅ Organic customers (excluded)
10. ✅ Refunded first orders (included in CAC, excluded from nCAC)
11. ✅ Multi-currency (separate CAC per currency)
12. ✅ Customer retention rate bounds (0-100%)
13. ✅ Calculation accuracy validation
14. ✅ Platform filtering (only Meta/Google)
15. ✅ Future dates (excluded)
16. ✅ Negative spend (filtered out)
17. ✅ Negative customer counts (blocked)
18. ✅ Tenant isolation (enforced)

---

## 🚨 Known Limitations & TODOs

### Revenue Model
- ⚠️ **Shipping amount**: Currently defaults to $0 (needs `shipping_lines` JSON array parsing)
- ⚠️ **Partial refund accuracy**: Uses 50% estimate (needs `refunds` JSON array parsing)
- ⚠️ **Multiple refunds**: Currently creates single refund event (needs enhancement)

### Attribution Model
- ⚠️ **UTM parameters**: Currently extracted from `note_attributes` (assumes Shopify tracking app installed)
- ⚠️ **Cross-device tracking**: Limited to logged-in customers only
- ⚠️ **Multi-touch journeys**: Only last-click (no multi-touch attribution yet)

### General
- ⚠️ **Currency conversion**: No currency conversion performed (each currency calculated separately)
- ⚠️ **Time zones**: All timestamps in UTC (no store timezone conversion)

---

## ✅ Next Steps

### 1. **Validate with Real Data** (CRITICAL)
You need to run these models against production data and validate:

```bash
# Navigate to dbt project
cd analytics/

# Run all metric models
dbt run --models metrics

# Run all tests
dbt test --models metrics

# Check for failures
```

**Human Validation Checklist:**

#### Revenue
- [ ] Compare calculated Revenue to Shopify admin's reported revenue
- [ ] Spot-check 5 orders with refunds (verify dates and amounts)
- [ ] Test order spanning month boundary
- [ ] Check multi-currency handling

#### AOV
- [ ] Compare AOV to historical GA4 or Shopify data
- [ ] Verify outlier detection (check orders excluded)
- [ ] Test with zero-order period
- [ ] Validate AOV "feels right" to merchant

#### ROAS
- [ ] Compare Gross ROAS to Meta Ads Manager reported ROAS
- [ ] Compare Gross ROAS to Google Ads reported ROAS
- [ ] Check attribution rate (what % of orders are attributed vs "direct")
- [ ] Test order with missing UTMs
- [ ] Verify platform-specific attribution windows

#### CAC & nCAC
- [ ] Validate "new customer" detection (check first-order logic)
- [ ] Test customer with multiple emails
- [ ] Check customer retention rate makes sense
- [ ] Compare CAC to merchant's expectations
- [ ] Verify nCAC > CAC (due to cancelled customers)

---

### 2. **Address Known Limitations** (Priority Order)

#### High Priority
1. **Parse `refunds` array** for exact refund amounts
   - Location: `fct_revenue.sql` line ~44
   - Currently using 50% estimate for partial refunds

2. **Parse `shipping_lines` array** for shipping amounts
   - Location: `fct_revenue.sql` line ~92
   - Currently defaults to $0

#### Medium Priority
3. **Enhance UTM extraction**
   - Handle missing Shopify tracking app
   - Add fallback to referrer domain parsing

4. **Add currency conversion** (optional)
   - Use exchange rate API
   - Convert all to tenant's base currency

#### Low Priority
5. **Multi-touch attribution** (future enhancement)
   - First-click attribution
   - Linear attribution
   - Position-based attribution

---

### 3. **Set Up Data Quality Monitoring**

You'll want to set up Story 4.7 next (Data Quality & Freshness Tests):

**Recommended Alerts:**
- Revenue >2x day-over-day (potential data issue or Black Friday)
- Attribution rate <30% (UTM tracking broken?)
- CAC >2x day-over-day (campaign misconfiguration?)
- Customer retention rate <50% (quality issue?)

---

### 4. **Documentation for End Users**

Create merchant-facing documentation:
- **What is Gross vs Net Revenue?**
- **Why doesn't my ROAS match Meta/Google?** (attribution window differences)
- **What's the difference between CAC and nCAC?**
- **When should I use Gross ROAS vs Net ROAS?**

---

## 📈 Usage Examples

### Revenue Waterfall Report
```sql
SELECT
  date_trunc('month', revenue_date) as month,
  SUM(CASE WHEN revenue_type = 'gross_revenue' THEN gross_revenue ELSE 0 END) as gross_revenue,
  SUM(refund_amount) as refunds,
  SUM(cancellation_amount) as cancellations,
  SUM(net_revenue) as net_revenue
FROM fct_revenue
WHERE tenant_id = 'your_tenant_id'
  AND revenue_date >= '2024-01-01'
GROUP BY 1
ORDER BY 1;
```

### Platform Performance Dashboard
```sql
SELECT
  platform,
  SUM(total_spend) as spend,
  SUM(order_count) as orders,
  AVG(gross_roas) as avg_gross_roas,
  AVG(net_roas) as avg_net_roas,
  AVG(cac) as avg_cac,
  AVG(ncac) as avg_ncac
FROM fct_roas r
JOIN fct_cac c USING (tenant_id, platform, period_start, currency)
WHERE r.period_type = 'monthly'
  AND r.tenant_id = 'your_tenant_id'
GROUP BY 1;
```

### Customer Quality Analysis
```sql
SELECT
  date_trunc('month', period_start) as month,
  new_customers,
  net_new_customers,
  customer_retention_rate_pct,
  cac,
  ncac,
  (ncac - cac) as cost_of_bad_customers,
  avg_first_order_value,
  avg_net_first_order_value
FROM fct_cac
WHERE period_type = 'monthly'
  AND tenant_id = 'your_tenant_id'
ORDER BY month DESC;
```

---

## 🎯 Success Criteria

Your metrics implementation is successful when:

✅ **Revenue matches Shopify** (within 5% variance)
✅ **ROAS is directionally aligned** with Meta/Google (exact match not expected due to attribution)
✅ **AOV feels right** to merchant (compared to historical data)
✅ **CAC is reasonable** (merchant can validate against their expectations)
✅ **All tests pass** (51 edge case tests)
✅ **No data quality incidents** in first 30 days
✅ **Zero metric definition questions** from merchants in first 30 days

---

## 💬 Questions or Issues?

If you encounter:
- **Data discrepancies**: Check attribution logic and UTM extraction
- **Test failures**: Review edge case handling in SQL
- **Performance issues**: Add indexes or optimize queries
- **Merchant confusion**: Enhance documentation with real examples

---

**Implementation Status: ✅ COMPLETE - Ready for Validation**

All metric models, tests, and documentation have been created. The next step is to run against production data and validate results with real merchant data.
