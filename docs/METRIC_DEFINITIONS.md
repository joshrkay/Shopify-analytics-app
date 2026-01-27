# Metric Definitions

This document defines all canonical metrics used in the Shopify Analytics Platform.
These definitions ensure consistent calculations across all data sources and reporting layers.

## Commerce Metrics

### revenue_gross

**Definition:** Total revenue before any deductions (refunds, discounts applied at checkout level).

**Formula:**
```
revenue_gross = SUM(order.total_price)
```

**Source:** `stg_shopify_orders.revenue_gross`

**Notes:**
- Includes tax and shipping if included in total_price
- Currency: Original order currency (multi-currency supported)
- Does NOT subtract refunds (see revenue_net)

---

### revenue_net

**Definition:** Revenue after discounts, before refunds.

**Formula:**
```
revenue_net = revenue_gross - total_discounts
```

**Source:** `stg_shopify_orders.revenue_net`

**Notes:**
- Refunds are tracked separately in `stg_shopify_refunds`
- For fully net revenue: `revenue_net - refunds_amount`

---

### orders

**Definition:** Count of orders placed.

**Formula:**
```
orders = COUNT(DISTINCT order_id)
```

**Source:** `stg_shopify_orders`

**Notes:**
- Includes cancelled orders unless filtered
- Filter by `financial_status` for paid orders only

---

### units_sold

**Definition:** Total number of line items (products) sold.

**Formula:**
```
units_sold = SUM(line_items_count)
```

**Source:** `stg_shopify_orders.units_sold`

**Notes:**
- Counts line item quantity, not unique products
- Does not subtract refunded units

---

### refunds_count

**Definition:** Number of refund transactions.

**Formula:**
```
refunds_count = COUNT(DISTINCT refund_id)
```

**Source:** `stg_shopify_refunds`

---

### refunds_amount

**Definition:** Total monetary value of refunds.

**Formula:**
```
refunds_amount = SUM(total_refund_amount)
```

**Source:** `stg_shopify_refunds.total_refund_amount`

**Notes:**
- Includes shipping refunds
- Same currency as original order

---

### aov (Average Order Value)

**Definition:** Average revenue per order.

**Formula:**
```
aov = revenue_gross / orders
```

**Notes:**
- Handle division by zero: return NULL if orders = 0
- Currency-specific (do not mix currencies)

---

### new_vs_returning_revenue

**Definition:** Revenue split by customer type.

**Formula:**
```
new_customer_revenue = SUM(revenue_gross) WHERE customer.orders_count = 1
returning_customer_revenue = SUM(revenue_gross) WHERE customer.orders_count > 1
```

**Notes:**
- Requires joining to customer data
- Only derivable without PII if customer_id is available
- Not exposed if PII-free constraint prevents calculation

---

## Marketing Metrics

### spend

**Definition:** Total advertising spend.

**Formula:**
```
spend = SUM(ad_spend)
```

**Sources:** All `stg_*_ads_daily` models

**Notes:**
- Currency as reported by platform
- Includes all spend regardless of result

---

### impressions

**Definition:** Number of times ads were displayed.

**Formula:**
```
impressions = SUM(impressions)
```

**Sources:** All `stg_*_ads_daily` models

---

### clicks

**Definition:** Number of clicks on ads.

**Formula:**
```
clicks = SUM(clicks)
```

**Sources:** All `stg_*_ads_daily` models

**Notes:**
- Definition varies by platform (link clicks vs all clicks)
- Platform-specific behaviors documented in source models

---

### conversions

**Definition:** Number of conversion events attributed to ads.

**Formula:**
```
conversions = SUM(conversions)
```

**Sources:** All `stg_*_ads_daily` models

**Notes:**
- Attribution window varies by platform:
  - Meta: 7-day click, 1-day view (default)
  - Google: Last-click attribution
  - TikTok: 7-day click, 1-day view
- May not match Shopify orders due to attribution differences

---

### conversion_value

**Definition:** Monetary value of conversions attributed to ads.

**Formula:**
```
conversion_value = SUM(conversion_value)
```

**Sources:** All `stg_*_ads_daily` models

**Notes:**
- As reported by ad platform
- Currency matches ad account currency

---

### cpm (Cost Per Mille)

**Definition:** Cost per 1,000 impressions.

**Formula:**
```
cpm = (spend / impressions) * 1000
```

**Notes:**
- NULL if impressions = 0
- Useful for awareness/reach campaigns

---

### cpc (Cost Per Click)

**Definition:** Average cost per click.

**Formula:**
```
cpc = spend / clicks
```

**Notes:**
- NULL if clicks = 0
- Platform may report average_cpc differently

---

### ctr (Click-Through Rate)

**Definition:** Percentage of impressions that resulted in clicks.

**Formula:**
```
ctr = (clicks / impressions) * 100
```

**Notes:**
- NULL if impressions = 0
- Expressed as percentage (e.g., 2.5 means 2.5%)

---

### cpa (Cost Per Acquisition)

**Definition:** Average cost per conversion.

**Formula:**
```
cpa = spend / conversions
```

**Notes:**
- NULL if conversions = 0
- Also known as cost per conversion

---

### roas_platform (Platform ROAS)

**Definition:** Return on ad spend as reported by ad platform.

**Formula:**
```
roas_platform = conversion_value / spend
```

**Notes:**
- NULL if spend = 0
- Based on platform-attributed conversions
- May differ from blended ROAS

---

## Blended Metrics

### mer (Marketing Efficiency Ratio)

**Definition:** Total revenue divided by total marketing spend.

**Formula:**
```
mer = shopify_revenue / total_ad_spend
```

**Notes:**
- Shopify revenue from `stg_shopify_orders`
- Ad spend from all `stg_*_ads_daily` sources combined
- Higher is better
- Not channel-attributed

---

### blended_roas

**Definition:** Shopify revenue divided by total ad spend (same as MER).

**Formula:**
```
blended_roas = shopify_revenue_gross / SUM(all_platform_spend)
```

**Notes:**
- Accounts for all revenue regardless of attribution
- More conservative than platform ROAS
- Useful for overall marketing efficiency

---

## Email/SMS Metrics

### emails_sent / emails_opened / emails_clicked

**Source:** `stg_klaviyo_events_daily`

**Notes:**
- Aggregated by event type
- Open tracking may be affected by privacy features (Apple MPP)

---

### sms_sent / sms_clicked

**Source:** `stg_klaviyo_events_daily`

**Notes:**
- SMS channel events
- Click tracking via shortened URLs

---

## Subscription Metrics (Recharge)

### new_subscriptions

**Definition:** Number of new subscriptions created.

**Source:** `stg_recharge_daily.new_subscriptions`

---

### churned_subscriptions

**Definition:** Number of subscriptions cancelled.

**Source:** `stg_recharge_daily.churned_subscriptions`

---

### net_subscriptions

**Definition:** Net change in subscription count.

**Formula:**
```
net_subscriptions = new_subscriptions - churned_subscriptions
```

---

### mrr (Monthly Recurring Revenue)

**Definition:** Value of recurring subscription revenue.

**Source:** `stg_recharge_daily.new_subscription_mrr`, `churned_mrr`

---

## Session/Traffic Metrics (GA4)

### sessions

**Definition:** Number of sessions (visits).

**Source:** `stg_ga4_daily.sessions`

---

### users

**Definition:** Number of unique users (pseudo IDs).

**Source:** `stg_ga4_daily.users`

---

### engagement_rate

**Definition:** Percentage of engaged sessions.

**Formula:**
```
engagement_rate = engaged_sessions / sessions
```

---

### conversion_rate

**Definition:** Percentage of sessions that converted.

**Formula:**
```
conversion_rate = (purchases / sessions) * 100
```
