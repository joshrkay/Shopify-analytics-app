# Metric Definitions

This document defines the canonical metrics used across the Shopify Analytics Platform. All staging models and downstream fact tables should use these standardized definitions.

## Commerce Metrics

### revenue_gross
**Definition**: Total order value before any deductions.
**Formula**: `total_price` from Shopify order
**Unit**: Currency (as reported by source)
**Notes**: Includes taxes, shipping, and discounts. This is the "headline" revenue number.

### revenue_net
**Definition**: Net revenue after discounts but before refunds.
**Formula**: `revenue_gross - total_discounts`
**Unit**: Currency
**Notes**: Refunds are tracked separately in `stg_shopify_refunds`. For true net revenue, subtract refunds from this value.

### orders
**Definition**: Count of valid orders.
**Formula**: `COUNT(*)` where `is_valid_order = true`
**Valid Order Criteria**:
- `financial_status` in ('paid', 'partially_paid', 'authorized', 'partially_refunded')
**Notes**: Cancelled and refunded orders are excluded from the count.

### units_sold
**Definition**: Total quantity of line items sold.
**Formula**: `SUM(line_item.quantity)` across all line items in an order
**Unit**: Integer
**Notes**: Counts individual items, not SKUs.

### refunds_count
**Definition**: Number of refund transactions.
**Formula**: `COUNT(*)` from refunds array per order
**Unit**: Integer
**Notes**: One order can have multiple partial refunds.

### refunds_amount
**Definition**: Total monetary value of refunds.
**Formula**: `SUM(refund.amount)` from refund transactions
**Unit**: Currency
**Notes**: Available in `stg_shopify_refunds` model.

### aov (Average Order Value)
**Definition**: Average revenue per order.
**Formula**: `revenue_gross / orders`
**Unit**: Currency
**Notes**:
- Returns NULL if orders = 0
- Outlier detection may be applied in downstream models

### new_vs_returning_revenue
**Definition**: Revenue split by customer type.
**Formula**:
- New customer: `orders_count = 1` for the customer at order time
- Returning customer: `orders_count > 1`
**Notes**: Only derivable if customer order history is available without PII.

## Marketing Metrics

### spend
**Definition**: Total advertising spend.
**Formula**: Direct from ad platform API
**Unit**: Currency
**Platform-specific handling**:
- Meta Ads: Direct spend value
- Google Ads: `cost_micros / 1,000,000`
- Pinterest: `spend_in_micro_dollar / 1,000,000`
- Snapchat: `spend / 1,000,000` (micros)

### impressions
**Definition**: Number of times an ad was displayed.
**Formula**: Direct from ad platform API
**Unit**: Integer
**Notes**: Platform-specific definitions may vary slightly.

### clicks
**Definition**: Number of clicks on an ad.
**Formula**: Direct from ad platform API
**Unit**: Integer
**Platform-specific handling**:
- Snapchat: Uses "swipes" as the click equivalent

### conversions
**Definition**: Number of conversion events attributed to ads.
**Formula**: Platform-reported conversions
**Unit**: Numeric (can be fractional for data-driven attribution)
**Notes**: Attribution windows vary by platform:
- Meta: 7-day click, 1-day view
- Google: Up to 90-day click
- TikTok: 7-day click
- Amazon: 14-day attribution

### conversion_value
**Definition**: Total revenue value attributed to conversions.
**Formula**: Platform-reported conversion value
**Unit**: Currency
**Notes**: May differ from Shopify revenue due to attribution differences.

### cpm (Cost Per Mille)
**Definition**: Cost per 1,000 impressions.
**Formula**: `(spend / impressions) * 1000`
**Unit**: Currency
**Notes**: Returns NULL if impressions = 0.

### cpc (Cost Per Click)
**Definition**: Average cost per click.
**Formula**: `spend / clicks`
**Unit**: Currency
**Notes**: Returns NULL if clicks = 0.

### ctr (Click-Through Rate)
**Definition**: Percentage of impressions that resulted in clicks.
**Formula**: `(clicks / impressions) * 100`
**Unit**: Percentage (e.g., 2.5 = 2.5%)
**Notes**: Returns NULL if impressions = 0.

### cpa (Cost Per Acquisition)
**Definition**: Average cost per conversion.
**Formula**: `spend / conversions`
**Unit**: Currency
**Notes**: Returns NULL if conversions = 0.

### roas_platform (Platform ROAS)
**Definition**: Return on ad spend as reported by the platform.
**Formula**: `conversion_value / spend`
**Unit**: Ratio (e.g., 3.5 = $3.50 revenue per $1 spent)
**Notes**:
- Returns NULL if spend = 0
- Based on platform-attributed conversions, not Shopify revenue

## Blended Metrics

### mer (Marketing Efficiency Ratio)
**Definition**: Total revenue divided by total marketing spend.
**Formula**: `SUM(shopify_revenue) / SUM(spend)`
**Unit**: Ratio
**Notes**:
- Calculated at aggregate level, not per-row
- Uses actual Shopify revenue, not platform-attributed

### blended_roas
**Definition**: Return on ad spend using actual Shopify revenue.
**Formula**: `SUM(shopify_revenue) / SUM(spend)`
**Unit**: Ratio
**Notes**:
- Equivalent to MER
- More accurate than platform ROAS for true business performance
- Includes all revenue, not just attributed

## Email/SMS Metrics (Klaviyo)

### sends
**Definition**: Number of emails/SMS messages sent.
**Formula**: `COUNT(*)` where event in ('received email', 'sent sms')
**Unit**: Integer

### opens
**Definition**: Number of email opens.
**Formula**: `COUNT(*)` where event = 'opened email'
**Unit**: Integer
**Notes**: Not applicable to SMS.

### open_rate
**Definition**: Percentage of sends that were opened.
**Formula**: `(opens / sends) * 100`
**Unit**: Percentage

## Analytics Metrics (GA4)

### sessions
**Definition**: Number of sessions.
**Formula**: Direct from GA4
**Unit**: Integer

### users
**Definition**: Number of unique users.
**Formula**: Direct from GA4
**Unit**: Integer

### new_users
**Definition**: Number of first-time users.
**Formula**: Direct from GA4
**Unit**: Integer

### pageviews
**Definition**: Number of page views.
**Formula**: Direct from GA4
**Unit**: Integer

## Subscription Metrics (ReCharge)

### successful_charges
**Definition**: Number of successful subscription charges.
**Formula**: `COUNT(*)` where status in ('success', 'paid')
**Unit**: Integer

### failed_charges
**Definition**: Number of failed subscription charges.
**Formula**: `COUNT(*)` where status in ('error', 'failed', 'refunded')
**Unit**: Integer

### new_subscriptions
**Definition**: Number of new subscription sign-ups.
**Formula**: `COUNT(*)` where charge_type = 'checkout'
**Unit**: Integer

---

## Data Quality Notes

1. **Currency Handling**: All monetary values should be in the original currency. Cross-currency aggregation requires conversion in downstream models.

2. **Null Handling**: Division-based metrics (CPM, CPC, CTR, CPA, ROAS) return NULL when the denominator is 0 or NULL, not infinity or error.

3. **Fractional Values**: Conversions may be fractional (e.g., 1.5) when using data-driven attribution models.

4. **Time Zones**: All timestamps are normalized to UTC. Date grain is in UTC.

5. **Lookback Windows**: Incremental models use configurable lookback windows to handle late-arriving data. See `dbt_project.yml` for source-specific settings.
