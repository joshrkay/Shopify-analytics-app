# Metric Definitions

This document defines all standardized metrics used across the Shopify Analytics dbt models. These definitions ensure consistency across all data sources and platforms.

## Core Advertising Metrics

### Spend
- **Definition**: Total advertising spend in the account's local currency
- **Column**: `spend`
- **Type**: `numeric`
- **Unit**: Currency (see `currency` column)
- **Sources**: All ad platforms (Meta, Google, TikTok, Pinterest, Snap, Amazon)
- **Notes**:
  - Pinterest and Snap provide spend in micro-dollars (millionths); models convert to dollars
  - Google Ads provides `cost_micros`; models convert to dollars
  - Always positive or zero

### Impressions
- **Definition**: Number of times an ad was displayed to users
- **Column**: `impressions`
- **Type**: `integer`
- **Unit**: Count
- **Sources**: All ad platforms
- **Notes**: Always positive or zero; capped at 2,147,483,647

### Clicks
- **Definition**: Number of clicks on an ad
- **Column**: `clicks`
- **Type**: `integer`
- **Unit**: Count
- **Sources**: All ad platforms
- **Notes**: Always positive or zero

### Conversions
- **Definition**: Number of conversion events attributed to an ad
- **Column**: `conversions`
- **Type**: `numeric`
- **Unit**: Count (can be fractional due to attribution models)
- **Sources**: All ad platforms
- **Notes**: Platform-specific attribution windows and models apply

### Conversion Value
- **Definition**: Total monetary value of conversions attributed to an ad
- **Column**: `conversion_value`
- **Type**: `numeric`
- **Unit**: Currency (see `currency` column)
- **Sources**: All ad platforms
- **Notes**: Uses platform-reported values; may differ from actual revenue

## Derived Advertising Metrics

### CPM (Cost Per Mille)
- **Definition**: Cost per 1,000 impressions
- **Column**: `cpm`
- **Formula**: `(spend / impressions) * 1000`
- **Type**: `numeric`
- **Unit**: Currency
- **Notes**: NULL when impressions = 0

### CPC (Cost Per Click)
- **Definition**: Cost per click
- **Column**: `cpc`
- **Formula**: `spend / clicks`
- **Type**: `numeric`
- **Unit**: Currency
- **Notes**: NULL when clicks = 0; falls back to platform-provided `average_cpc` when available

### CTR (Click-Through Rate)
- **Definition**: Percentage of impressions that resulted in clicks
- **Column**: `ctr`
- **Formula**: `(clicks / impressions) * 100`
- **Type**: `numeric`
- **Unit**: Percentage (0-100)
- **Notes**: NULL when impressions = 0; falls back to platform-provided CTR when available

### CPA (Cost Per Acquisition)
- **Definition**: Cost per conversion
- **Column**: `cpa`
- **Formula**: `spend / conversions`
- **Type**: `numeric`
- **Unit**: Currency
- **Notes**: NULL when conversions = 0

### ROAS Platform (Return on Ad Spend)
- **Definition**: Platform-reported return on ad spend
- **Column**: `roas_platform`
- **Formula**: `conversion_value / spend`
- **Type**: `numeric`
- **Unit**: Ratio (e.g., 3.5 = $3.50 revenue per $1 spent)
- **Notes**: NULL when spend = 0; uses platform-reported conversion values

## Shopify Commerce Metrics

### Revenue (Total Price)
- **Definition**: Total order value including taxes
- **Column**: `total_price`
- **Type**: `numeric`
- **Unit**: Currency
- **Source**: stg_shopify_orders
- **Notes**: Includes taxes; see `subtotal_price` for pre-tax value

### Subtotal Price
- **Definition**: Order value before taxes
- **Column**: `subtotal_price`
- **Type**: `numeric`
- **Unit**: Currency
- **Source**: stg_shopify_orders

### Total Tax
- **Definition**: Total tax amount on order
- **Column**: `total_tax`
- **Type**: `numeric`
- **Unit**: Currency
- **Source**: stg_shopify_orders

### Refund Amount
- **Definition**: Total refunded value
- **Column**: `refund_amount`
- **Type**: `numeric`
- **Unit**: Currency
- **Source**: stg_shopify_refunds
- **Notes**: Prefers transaction-based amount; falls back to line items + adjustments

## Email/SMS Marketing Metrics (Klaviyo)

### Sent
- **Definition**: Number of messages sent
- **Column**: `sent`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Delivered
- **Definition**: Number of messages successfully delivered
- **Column**: `delivered`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Opens / Unique Opens
- **Definition**: Number of times messages were opened
- **Columns**: `opens`, `unique_opens`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Clicks / Unique Clicks
- **Definition**: Number of clicks on links within messages
- **Columns**: `clicks`, `unique_clicks`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Bounces
- **Definition**: Number of messages that bounced
- **Column**: `bounces`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Unsubscribes
- **Definition**: Number of unsubscribe events
- **Column**: `unsubscribes`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Spam Complaints
- **Definition**: Number of spam complaints
- **Column**: `spam_complaints`
- **Type**: `integer`
- **Source**: stg_klaviyo_events_daily

### Revenue (Klaviyo)
- **Definition**: Revenue attributed to email/SMS campaigns
- **Column**: `revenue`
- **Type**: `numeric`
- **Source**: stg_klaviyo_events_daily

## Web Analytics Metrics (GA4)

### Sessions
- **Definition**: Number of user sessions
- **Column**: `sessions`
- **Type**: `integer`
- **Source**: stg_ga4_daily

### Users
- **Definition**: Number of unique users
- **Column**: `users`
- **Type**: `integer`
- **Source**: stg_ga4_daily

### New Users
- **Definition**: Number of first-time users
- **Column**: `new_users`
- **Type**: `integer`
- **Source**: stg_ga4_daily

### Pageviews
- **Definition**: Number of page views
- **Column**: `pageviews`
- **Type**: `integer`
- **Source**: stg_ga4_daily

### Bounce Rate
- **Definition**: Percentage of single-page sessions
- **Column**: `bounce_rate`
- **Type**: `numeric`
- **Unit**: Percentage (0-100)
- **Source**: stg_ga4_daily

### Avg Session Duration
- **Definition**: Average session length in seconds
- **Column**: `avg_session_duration`
- **Type**: `numeric`
- **Unit**: Seconds
- **Source**: stg_ga4_daily

### Transactions
- **Definition**: Number of e-commerce transactions
- **Column**: `transactions`
- **Type**: `integer`
- **Source**: stg_ga4_daily

### Transaction Revenue
- **Definition**: Total e-commerce revenue
- **Column**: `transaction_revenue`
- **Type**: `numeric`
- **Source**: stg_ga4_daily

## Subscription Metrics (ReCharge)

### Active Subscriptions
- **Definition**: Number of active subscriptions
- **Column**: `active_subscriptions`
- **Type**: `integer`
- **Source**: stg_recharge_daily

### New Subscriptions
- **Definition**: Number of new subscriptions created
- **Column**: `new_subscriptions`
- **Type**: `integer`
- **Source**: stg_recharge_daily

### Churned Subscriptions
- **Definition**: Number of cancelled subscriptions
- **Column**: `churned_subscriptions`
- **Type**: `integer`
- **Source**: stg_recharge_daily

### Subscription Revenue
- **Definition**: Revenue from subscription orders
- **Column**: `subscription_revenue`
- **Type**: `numeric`
- **Source**: stg_recharge_daily

### One-Time Revenue
- **Definition**: Revenue from one-time purchases
- **Column**: `one_time_revenue`
- **Type**: `numeric`
- **Source**: stg_recharge_daily

### MRR (Monthly Recurring Revenue)
- **Definition**: Estimated monthly recurring revenue from active subscriptions
- **Column**: `mrr`
- **Type**: `numeric`
- **Source**: stg_recharge_daily

## Standard Columns

All staging models include these standard columns for consistency:

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | `text` | Multi-tenant isolation identifier |
| `report_date` | `date` | Date the metrics apply to |
| `source` | `text` | Platform identifier (e.g., 'meta_ads', 'google_ads') |
| `currency` | `text` | 3-letter ISO currency code (default: 'USD') |
| `airbyte_record_id` | `text` | Airbyte ingestion record ID |
| `airbyte_emitted_at` | `timestamp` | Airbyte ingestion timestamp |

## Data Quality Notes

1. **Currency Handling**: All monetary values are in the source currency. Currency conversion should happen at the mart/reporting layer.

2. **Null vs Zero**:
   - Core metrics (spend, impressions, clicks) default to 0 when NULL
   - Derived metrics (cpm, cpc, ctr, cpa, roas) are NULL when the denominator is 0

3. **Bounds Checking**: All numeric values are bounded to prevent overflow:
   - Monetary values: -999,999,999.99 to 999,999,999.99
   - Integer counts: 0 to 2,147,483,647
   - Percentages: 0 to 100

4. **Attribution**: Conversion metrics use platform-specific attribution models and windows. Cross-platform attribution should be handled at the mart layer.
