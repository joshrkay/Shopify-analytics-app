# Implementation Plan: dbt Staging Models for Multi-Tenant Shopify Analytics

## Executive Summary

This plan outlines the implementation of dbt staging models to normalize raw data from multiple sources (Shopify, ad platforms, analytics) into consistent schemas for downstream canonical facts and reporting.

---

## 1. Current State Analysis

### 1.1 Existing Infrastructure

| Component | Status | Location |
|-----------|--------|----------|
| dbt project | ✅ Exists | `analytics/` |
| packages.yml | ✅ Exists | `analytics/packages.yml` (dbt_utils v1.1.1) |
| Staging models | ⚠️ Partial | 4 models exist (see below) |
| Macros | ⚠️ Partial | 4 macros exist (no channel mapping) |
| Dimension tables | ❌ Missing | Need dim_ad_accounts, dim_campaigns |
| Documentation | ❌ Missing | No docs/ folder |

### 1.2 Existing Staging Models

| Model | File | Status |
|-------|------|--------|
| stg_shopify_orders | `models/staging/shopify/stg_shopify_orders.sql` | ✅ Exists (views) |
| stg_shopify_customers | `models/staging/shopify/stg_shopify_customers.sql` | ✅ Exists |
| stg_meta_ads | `models/staging/ads/stg_meta_ads.sql` | ⚠️ Needs enhancement |
| stg_google_ads | `models/staging/ads/stg_google_ads.sql` | ⚠️ Needs enhancement |

### 1.3 Missing Components (Required by Story)

**Staging Models to Create:**
- `stg_shopify_refunds` - NEW
- `stg_tiktok_ads_daily` - NEW
- `stg_pinterest_ads_daily` - NEW
- `stg_snap_ads_daily` - NEW
- `stg_amazon_ads_daily` - NEW
- `stg_klaviyo_events_daily` - NEW
- `stg_ga4_daily` - NEW
- `stg_recharge_daily` - NEW

**Existing Models to Enhance:**
- `stg_meta_ads` → Rename to `stg_meta_ads_daily`, add channel mapping + internal IDs
- `stg_google_ads` → Rename to `stg_google_ads_daily`, add channel mapping + internal IDs

### 1.4 Freshness SLAs (From Story 7.6 - `backend/src/models/dq_models.py:100-118`)

| Source | Warning | High | Critical |
|--------|---------|------|----------|
| Shopify Orders/Refunds | 120 min | 240 min | 480 min |
| Recharge | 120 min | 240 min | 480 min |
| Meta/Google/TikTok/Pinterest/Snap/Amazon Ads | 1440 min | 2880 min | 5760 min |
| Klaviyo/GA4 | 1440 min | 2880 min | 5760 min |

---

## 2. Architecture Decisions (Locked)

### 2.1 ID Normalization Strategy (Option B)

**Pattern (existing in codebase):**
```sql
md5(concat(tenant_id, '|', source, '|', platform_id)) as internal_id
```

**Rationale:**
- Deterministic: Same input → same output
- Collision-resistant across tenants
- Already used in `fact_ad_spend.sql:110` and `fact_orders.sql`

### 2.2 Incremental Strategy (Option A)

**Pattern:**
```sql
{% if is_incremental() %}
    and airbyte_emitted_at > (
        select coalesce(max(ingested_at), '1970-01-01'::timestamp with time zone)
               - interval '{{ var("lookback_days", 3) }} days'
        from {{ this }}
    )
{% endif %}
```

**Rationale:**
- Handles late-arriving data with configurable lookback
- Matches existing pattern in `fact_ad_spend.sql:37-43`

### 2.3 Channel Taxonomy

| canonical_channel | platform_channels |
|-------------------|-------------------|
| `paid_social` | meta_ads, tiktok_ads, snap_ads, pinterest_ads |
| `paid_search` | google_ads (search network) |
| `paid_shopping` | google_ads (shopping), amazon_ads |
| `paid_display` | google_ads (display network) |
| `paid_video` | google_ads (youtube), tiktok_ads (video) |
| `email` | klaviyo |
| `organic_search` | ga4 (organic) |
| `organic_social` | ga4 (social) |
| `direct` | ga4 (direct) |
| `referral` | ga4 (referral) |
| `subscription` | recharge |

---

## 3. File-by-File Implementation Plan

### 3.1 Configuration Files

#### 3.1.1 `analytics/dbt_project.yml` - MODIFY

**Changes:**
- Add vars for `lookback_days` per source
- Add vars for freshness thresholds (read from config, not hardcoded)
- Add new model paths for dimensions

**Lines to modify:** 49-55

```yaml
vars:
  tenant_isolation_enforced: true
  airbyte_raw_schema: airbyte_raw
  platform_schema: platform
  # Lookback windows per source (days)
  lookback_days_default: 3
  lookback_days_shopify: 3
  lookback_days_ads: 7
  lookback_days_analytics: 3
  # Freshness thresholds read from dq_models.py (in minutes)
  # Do NOT hardcode - use get_freshness_threshold() macro
```

**Risk:** LOW - Additive only, no breaking changes

---

#### 3.1.2 `analytics/packages.yml` - NO CHANGE

Already includes `dbt_utils v1.1.1`. No additional packages required.

---

### 3.2 Macros

#### 3.2.1 `analytics/macros/generate_internal_id.sql` - NEW

**Purpose:** Deterministic internal ID generation for accounts and campaigns

**Interface:**
```sql
{{ generate_internal_id(tenant_id, source, platform_id) }}
-- Returns: md5(concat(tenant_id, '|', source, '|', platform_id))
```

**Justification:** Removes duplication from staging models; currently repeated inline in each model.

---

#### 3.2.2 `analytics/macros/map_canonical_channel.sql` - NEW

**Purpose:** Map platform_channel to canonical_channel

**Interface:**
```sql
{{ map_canonical_channel(platform, campaign_objective, network_type) }}
-- Returns: canonical_channel string
```

**Logic:**
```sql
case
    when platform in ('meta_ads', 'tiktok_ads', 'snap_ads', 'pinterest_ads') then 'paid_social'
    when platform = 'google_ads' and network_type = 'SEARCH' then 'paid_search'
    when platform = 'google_ads' and network_type = 'SHOPPING' then 'paid_shopping'
    when platform = 'google_ads' and network_type = 'DISPLAY' then 'paid_display'
    when platform = 'google_ads' and network_type = 'YOUTUBE_WATCH' then 'paid_video'
    when platform = 'amazon_ads' then 'paid_shopping'
    when platform = 'klaviyo' then 'email'
    when platform = 'recharge' then 'subscription'
    when platform = 'ga4' then
        case
            when channel_grouping = 'Organic Search' then 'organic_search'
            when channel_grouping = 'Organic Social' then 'organic_social'
            when channel_grouping = 'Direct' then 'direct'
            when channel_grouping = 'Referral' then 'referral'
            else 'other'
        end
    else 'other'
end
```

---

#### 3.2.3 `analytics/macros/get_lookback_interval.sql` - NEW

**Purpose:** Get lookback interval for incremental models

**Interface:**
```sql
{{ get_lookback_interval(source_type) }}
-- Returns: interval expression (e.g., "interval '3 days'")
```

---

#### 3.2.4 `analytics/macros/get_freshness_threshold.sql` - NEW

**Purpose:** Get freshness threshold from dbt vars (populated from backend config)

**Interface:**
```sql
{{ get_freshness_threshold(source_type, severity) }}
-- Returns: threshold in minutes
```

**Note:** Values come from `var('freshness_thresholds')`, NOT hardcoded.

---

### 3.3 Dimension Tables

#### 3.3.1 `analytics/models/dimensions/dim_ad_accounts.sql` - NEW

**Schema:**
```sql
tenant_id           VARCHAR NOT NULL
source              VARCHAR NOT NULL  -- 'meta_ads', 'google_ads', etc.
platform_account_id VARCHAR NOT NULL  -- Original platform ID
internal_account_id VARCHAR NOT NULL  -- md5(tenant_id|source|platform_account_id)
account_name        VARCHAR           -- If available from source
currency            VARCHAR(3)
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

**Primary Key:** `internal_account_id`
**Unique:** `(tenant_id, source, platform_account_id)`

**Tests:**
- not_null: tenant_id, source, platform_account_id, internal_account_id
- unique: internal_account_id

---

#### 3.3.2 `analytics/models/dimensions/dim_campaigns.sql` - NEW

**Schema:**
```sql
tenant_id             VARCHAR NOT NULL
source                VARCHAR NOT NULL
platform_campaign_id  VARCHAR NOT NULL
internal_campaign_id  VARCHAR NOT NULL  -- md5(tenant_id|source|platform_campaign_id)
internal_account_id   VARCHAR NOT NULL  -- FK to dim_ad_accounts
campaign_name         VARCHAR
objective             VARCHAR           -- Campaign objective
status                VARCHAR           -- active, paused, deleted
created_at            TIMESTAMP
updated_at            TIMESTAMP
```

**Primary Key:** `internal_campaign_id`

**Tests:**
- not_null: tenant_id, source, platform_campaign_id, internal_campaign_id
- unique: internal_campaign_id
- relationships: internal_account_id → dim_ad_accounts.internal_account_id

---

#### 3.3.3 `analytics/models/dimensions/schema.yml` - NEW

Define tests and documentation for both dimension tables.

---

### 3.4 Staging Models - Commerce

#### 3.4.1 `analytics/models/staging/shopify/stg_shopify_orders.sql` - MODIFY

**Changes Required:**
- Add `report_date` (date grain field) from `created_at`
- Add `platform_channel` = 'shopify'
- Add `canonical_channel` = 'store' (direct purchases)
- Existing model is already views, NOT incremental - no change to materialization

**Columns to Add:**
```sql
created_at::date as report_date,
'shopify' as platform_channel,
'store' as canonical_channel
```

**Risk:** LOW - Additive columns only

---

#### 3.4.2 `analytics/models/staging/shopify/stg_shopify_refunds.sql` - NEW

**Source:** `_airbyte_raw_shopify_orders` (refunds are nested in order data)

**Schema:**
```sql
tenant_id             VARCHAR NOT NULL
refund_id             VARCHAR NOT NULL  -- Primary key
order_id              VARCHAR NOT NULL  -- FK to orders
report_date           DATE NOT NULL     -- refund processed date
refund_amount         NUMERIC
refund_line_items     INTEGER           -- count of items refunded
reason                VARCHAR
note                  VARCHAR
currency              VARCHAR(3)
platform_channel      VARCHAR           -- 'shopify'
canonical_channel     VARCHAR           -- 'store'
airbyte_record_id     VARCHAR
airbyte_emitted_at    TIMESTAMP
```

**Extraction Logic:**
```sql
-- Extract from refunds_json array in stg_shopify_orders
jsonb_array_elements(refunds_json::jsonb) as refund
```

**Tests:**
- not_null: tenant_id, refund_id, order_id, report_date
- unique: refund_id (per tenant)
- relationships: order_id → stg_shopify_orders.order_id

---

#### 3.4.3 `analytics/models/staging/recharge/stg_recharge_daily.sql` - NEW

**Source:** `_airbyte_raw_recharge_subscriptions` (to be added to sources)

**Schema:**
```sql
tenant_id             VARCHAR NOT NULL
report_date           DATE NOT NULL
subscription_id       VARCHAR NOT NULL
customer_id           VARCHAR
status                VARCHAR           -- active, cancelled, expired
plan_type             VARCHAR
price                 NUMERIC
currency              VARCHAR(3)
next_charge_date      DATE
platform_channel      VARCHAR           -- 'recharge'
canonical_channel     VARCHAR           -- 'subscription'
airbyte_record_id     VARCHAR
airbyte_emitted_at    TIMESTAMP
```

**PII Exclusions:** No names, emails, addresses, payment details

---

### 3.5 Staging Models - Advertising

#### 3.5.1 `analytics/models/staging/ads/stg_meta_ads_daily.sql` - RENAME & MODIFY

**Current:** `stg_meta_ads.sql`
**New:** `stg_meta_ads_daily.sql`

**Changes:**
1. Rename file
2. Add `report_date` alias for `date`
3. Add `platform_channel` = 'meta_ads'
4. Add `canonical_channel` via macro
5. Add `platform_account_id` (alias for ad_account_id)
6. Add `internal_account_id` via generate_internal_id macro
7. Add `platform_campaign_id` (alias for campaign_id)
8. Add `internal_campaign_id` via generate_internal_id macro
9. Add `conversion_value` (if available, else 0)
10. Add derived metrics: cpm, cpc, ctr, cpa, roas_platform

**Derived Metrics:**
```sql
-- CPM: cost per thousand impressions
case when impressions > 0 then (spend / impressions) * 1000 else 0 end as cpm,

-- CPC: cost per click
case when clicks > 0 then spend / clicks else 0 end as cpc,

-- CTR: click-through rate
case when impressions > 0 then (clicks::numeric / impressions) * 100 else 0 end as ctr,

-- CPA: cost per acquisition
case when conversions > 0 then spend / conversions else 0 end as cpa,

-- ROAS: return on ad spend (platform-reported)
case when spend > 0 then conversion_value / spend else 0 end as roas_platform
```

**Incremental Logic:**
```sql
{% if is_incremental() %}
    and airbyte_emitted_at > (
        select coalesce(max(airbyte_emitted_at), '1970-01-01'::timestamp)
               - {{ get_lookback_interval('meta_ads') }}
        from {{ this }}
    )
{% endif %}
```

---

#### 3.5.2 `analytics/models/staging/ads/stg_google_ads_daily.sql` - RENAME & MODIFY

**Current:** `stg_google_ads.sql`
**New:** `stg_google_ads_daily.sql`

**Changes:** Same as Meta Ads, plus:
- Map `network` field to determine canonical_channel (search/shopping/display/video)
- Handle `cost_micros` → dollars conversion (already exists)

---

#### 3.5.3 `analytics/models/staging/ads/stg_tiktok_ads_daily.sql` - NEW

**Source:** `_airbyte_raw_tiktok_ads` (to be added)

**Schema (matches canonical contract):**
```sql
tenant_id             VARCHAR NOT NULL
report_date           DATE NOT NULL
source                VARCHAR           -- 'tiktok_ads'
platform_channel      VARCHAR           -- 'tiktok_ads'
canonical_channel     VARCHAR           -- 'paid_social' or 'paid_video'
platform_account_id   VARCHAR NOT NULL
internal_account_id   VARCHAR NOT NULL
platform_campaign_id  VARCHAR NOT NULL
internal_campaign_id  VARCHAR NOT NULL
spend                 NUMERIC
impressions           INTEGER
clicks                INTEGER
conversions           NUMERIC
conversion_value      NUMERIC
cpm                   NUMERIC           -- derived
cpc                   NUMERIC           -- derived
ctr                   NUMERIC           -- derived
cpa                   NUMERIC           -- derived
roas_platform         NUMERIC           -- derived
currency              VARCHAR(3)
campaign_name         VARCHAR
objective             VARCHAR
airbyte_record_id     VARCHAR
airbyte_emitted_at    TIMESTAMP
```

---

#### 3.5.4 `analytics/models/staging/ads/stg_pinterest_ads_daily.sql` - NEW

**Source:** `_airbyte_raw_pinterest_ads`

**Schema:** Same as canonical contract (see 3.5.3)

**Pinterest-specific fields to map:**
- `pin_promotion_id` → ad_id
- `campaign_daily_spend_cap` → (metadata)

---

#### 3.5.5 `analytics/models/staging/ads/stg_snap_ads_daily.sql` - NEW

**Source:** `_airbyte_raw_snap_ads`

**Schema:** Same as canonical contract

**Snap-specific fields:**
- `swipe_up_percent` → ctr equivalent
- `video_views` → (additional metric)

---

#### 3.5.6 `analytics/models/staging/ads/stg_amazon_ads_daily.sql` - NEW

**Source:** `_airbyte_raw_amazon_ads`

**Schema:** Same as canonical contract

**Amazon-specific fields:**
- `acos` (advertising cost of sales) → derived metric
- `product_ads` vs `sponsored_brands` → ad_type

---

### 3.6 Staging Models - Marketing & Analytics

#### 3.6.1 `analytics/models/staging/klaviyo/stg_klaviyo_events_daily.sql` - NEW

**Source:** `_airbyte_raw_klaviyo_events`

**Schema:**
```sql
tenant_id             VARCHAR NOT NULL
report_date           DATE NOT NULL
event_id              VARCHAR NOT NULL
event_type            VARCHAR           -- 'Received Email', 'Opened Email', 'Clicked Email', etc.
campaign_id           VARCHAR
flow_id               VARCHAR
list_id               VARCHAR
platform_channel      VARCHAR           -- 'klaviyo'
canonical_channel     VARCHAR           -- 'email'
-- Aggregated metrics (daily grain)
sends                 INTEGER
opens                 INTEGER
clicks                INTEGER
bounces               INTEGER
unsubscribes          INTEGER
conversions           INTEGER
conversion_value      NUMERIC
airbyte_record_id     VARCHAR
airbyte_emitted_at    TIMESTAMP
```

**PII Exclusions:** No email addresses, recipient names, or profile data beyond IDs

---

#### 3.6.2 `analytics/models/staging/ga4/stg_ga4_daily.sql` - NEW

**Source:** `_airbyte_raw_ga4_events`

**Schema:**
```sql
tenant_id             VARCHAR NOT NULL
report_date           DATE NOT NULL
source                VARCHAR           -- 'ga4'
platform_channel      VARCHAR           -- traffic source (e.g., 'google', 'facebook')
canonical_channel     VARCHAR           -- mapped via channel_grouping
session_source        VARCHAR
session_medium        VARCHAR
session_campaign      VARCHAR
channel_grouping      VARCHAR           -- GA4's default channel grouping
sessions              INTEGER
users                 INTEGER
new_users             INTEGER
page_views            INTEGER
transactions          INTEGER
revenue               NUMERIC
engagement_rate       NUMERIC
bounce_rate           NUMERIC
airbyte_record_id     VARCHAR
airbyte_emitted_at    TIMESTAMP
```

**Channel Mapping:**
- Use GA4's `channel_grouping` to derive `canonical_channel`

---

### 3.7 Schema Files

#### 3.7.1 `analytics/models/staging/schema.yml` - MODIFY

**Add:**
1. Source definitions for new raw tables:
   - `_airbyte_raw_shopify_refunds` (or extract from orders)
   - `_airbyte_raw_tiktok_ads`
   - `_airbyte_raw_pinterest_ads`
   - `_airbyte_raw_snap_ads`
   - `_airbyte_raw_amazon_ads`
   - `_airbyte_raw_klaviyo_events`
   - `_airbyte_raw_ga4_events`
   - `_airbyte_raw_recharge_subscriptions`

2. Model definitions with tests for all new staging models:
   - not_null: tenant_id, report_date, internal IDs
   - accepted_values: canonical_channel
   - relationships: internal_account_id → dim_ad_accounts
   - relationships: internal_campaign_id → dim_campaigns

3. Freshness tests using configurable thresholds:
```yaml
freshness:
  warn_after: {count: "{{ var('freshness_warn_' ~ source_type, 1440) }}", period: minute}
  error_after: {count: "{{ var('freshness_error_' ~ source_type, 2880) }}", period: minute}
```

---

#### 3.7.2 `analytics/models/dimensions/schema.yml` - NEW

Define tests for dim_ad_accounts and dim_campaigns.

---

### 3.8 Documentation

#### 3.8.1 `analytics/docs/METRIC_DEFINITIONS.md` - NEW

**Content:**
```markdown
# Metric Definitions

## Commerce Metrics
| Metric | Definition | Calculation |
|--------|------------|-------------|
| revenue_gross | Total order value before refunds | SUM(total_price) |
| revenue_net | Total order value after refunds | revenue_gross - refunds_amount |
| orders | Count of completed orders | COUNT(DISTINCT order_id) |
| units_sold | Total items sold | SUM(line_items_quantity) |
| refunds_count | Number of refunds processed | COUNT(DISTINCT refund_id) |
| refunds_amount | Total refund value | SUM(refund_amount) |
| aov | Average order value | revenue_gross / orders |

## Marketing Metrics
| Metric | Definition | Calculation |
|--------|------------|-------------|
| spend | Total ad spend | SUM(spend) |
| impressions | Ad views | SUM(impressions) |
| clicks | Ad clicks | SUM(clicks) |
| conversions | Platform-reported conversions | SUM(conversions) |
| conversion_value | Value of conversions | SUM(conversion_value) |
| cpm | Cost per thousand impressions | (spend / impressions) * 1000 |
| cpc | Cost per click | spend / clicks |
| ctr | Click-through rate (%) | (clicks / impressions) * 100 |
| cpa | Cost per acquisition | spend / conversions |
| roas_platform | Platform ROAS | conversion_value / spend |

## Blended Metrics
| Metric | Definition | Calculation |
|--------|------------|-------------|
| mer | Marketing efficiency ratio | revenue_net / total_spend |
| blended_roas | Blended ROAS | shopify_revenue / total_ad_spend |
```

---

#### 3.8.2 `analytics/docs/CHANNEL_TAXONOMY.md` - NEW

**Content:**
```markdown
# Channel Taxonomy

## Platform to Canonical Channel Mapping

| platform_channel | canonical_channel | Notes |
|------------------|-------------------|-------|
| meta_ads | paid_social | Facebook, Instagram |
| tiktok_ads | paid_social | May also be paid_video |
| snap_ads | paid_social | Snapchat |
| pinterest_ads | paid_social | Pinterest |
| google_ads (SEARCH) | paid_search | Search network |
| google_ads (SHOPPING) | paid_shopping | Shopping network |
| google_ads (DISPLAY) | paid_display | Display network |
| google_ads (YOUTUBE) | paid_video | YouTube |
| amazon_ads | paid_shopping | Sponsored products/brands |
| klaviyo | email | Email marketing |
| ga4 (organic search) | organic_search | Google organic |
| ga4 (organic social) | organic_social | Social organic |
| ga4 (direct) | direct | Direct traffic |
| ga4 (referral) | referral | Referral traffic |
| recharge | subscription | Recurring revenue |
| shopify | store | Direct purchases |

## Mapping Logic
See macro: `macros/map_canonical_channel.sql`
```

---

#### 3.8.3 `analytics/docs/ID_NORMALIZATION.md` - NEW

**Content:**
```markdown
# ID Normalization

## Internal ID Generation

All internal IDs are generated using MD5 hashing for deterministic, collision-resistant keys.

### Formula
```sql
md5(concat(tenant_id, '|', source, '|', platform_id))
```

### Examples
| Type | Formula | Example |
|------|---------|---------|
| Account | `md5(tenant_id \| source \| platform_account_id)` | `md5('tenant_123\|meta_ads\|act_456')` |
| Campaign | `md5(tenant_id \| source \| platform_campaign_id)` | `md5('tenant_123\|google_ads\|123456789')` |

### Why MD5?
- Deterministic: Same input always produces same output
- Fixed length: 32-character hex string
- Collision-resistant across tenants (tenant_id included)
- Human-readable: Easier to debug than UUIDs

### Dimension Tables
- `dim_ad_accounts`: Maps platform_account_id → internal_account_id
- `dim_campaigns`: Maps platform_campaign_id → internal_campaign_id

### Usage in Staging Models
```sql
{{ generate_internal_id('tenant_id', 'source', 'platform_account_id') }} as internal_account_id
```
```

---

## 4. Implementation Order

### Phase 1: Foundation (Must Complete First)

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 1.1 | `macros/generate_internal_id.sql` | NEW | None |
| 1.2 | `macros/map_canonical_channel.sql` | NEW | None |
| 1.3 | `macros/get_lookback_interval.sql` | NEW | None |
| 1.4 | `dbt_project.yml` | MODIFY | None |

### Phase 2: Dimensions (Before Staging Models)

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 2.1 | `models/dimensions/dim_ad_accounts.sql` | NEW | Phase 1 |
| 2.2 | `models/dimensions/dim_campaigns.sql` | NEW | 2.1 |
| 2.3 | `models/dimensions/schema.yml` | NEW | 2.1, 2.2 |

### Phase 3: Sources & Schema (Before Models)

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 3.1 | `models/staging/schema.yml` | MODIFY | Add new source definitions |

### Phase 4: Commerce Staging Models

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 4.1 | `models/staging/shopify/stg_shopify_orders.sql` | MODIFY | Phase 1 |
| 4.2 | `models/staging/shopify/stg_shopify_refunds.sql` | NEW | 4.1 |
| 4.3 | `models/staging/recharge/stg_recharge_daily.sql` | NEW | Phase 1 |

### Phase 5: Advertising Staging Models

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 5.1 | `models/staging/ads/stg_meta_ads_daily.sql` | RENAME+MODIFY | Phase 1, 2 |
| 5.2 | `models/staging/ads/stg_google_ads_daily.sql` | RENAME+MODIFY | Phase 1, 2 |
| 5.3 | `models/staging/ads/stg_tiktok_ads_daily.sql` | NEW | Phase 1, 2 |
| 5.4 | `models/staging/ads/stg_pinterest_ads_daily.sql` | NEW | Phase 1, 2 |
| 5.5 | `models/staging/ads/stg_snap_ads_daily.sql` | NEW | Phase 1, 2 |
| 5.6 | `models/staging/ads/stg_amazon_ads_daily.sql` | NEW | Phase 1, 2 |

### Phase 6: Marketing & Analytics Staging Models

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 6.1 | `models/staging/klaviyo/stg_klaviyo_events_daily.sql` | NEW | Phase 1 |
| 6.2 | `models/staging/ga4/stg_ga4_daily.sql` | NEW | Phase 1 |

### Phase 7: Documentation

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 7.1 | `docs/METRIC_DEFINITIONS.md` | NEW | Phase 4-6 |
| 7.2 | `docs/CHANNEL_TAXONOMY.md` | NEW | Phase 1 |
| 7.3 | `docs/ID_NORMALIZATION.md` | NEW | Phase 2 |

### Phase 8: Tests & Validation

| Order | File | Type | Dependencies |
|-------|------|------|--------------|
| 8.1 | Update `models/staging/schema.yml` | MODIFY | All models |
| 8.2 | Validate all models compile | VERIFY | All phases |
| 8.3 | Run dbt test | VERIFY | 8.2 |

---

## 5. File Count Summary

| Category | New Files | Modified Files | Renamed Files | Total Changes |
|----------|-----------|----------------|---------------|---------------|
| Macros | 3 | 0 | 0 | 3 |
| Dimensions | 2 (+schema) | 0 | 0 | 3 |
| Staging (Commerce) | 2 | 1 | 0 | 3 |
| Staging (Ads) | 4 | 0 | 2 | 6 |
| Staging (Marketing) | 2 | 0 | 0 | 2 |
| Schema | 1 | 1 | 0 | 2 |
| Docs | 3 | 0 | 0 | 3 |
| Config | 0 | 1 | 0 | 1 |
| **TOTAL** | **17** | **3** | **2** | **22** |

---

## 6. Testing Requirements

### 6.1 Required Tests (Per Model)

| Test Type | Applied To | Severity |
|-----------|------------|----------|
| not_null | tenant_id, report_date, internal_*_id | error |
| unique | internal_*_id (within tenant) | error |
| accepted_values | canonical_channel | warn |
| relationships | internal_account_id → dim_ad_accounts | error |
| relationships | internal_campaign_id → dim_campaigns | error |
| freshness | All sources (per SLA) | warn/error |

### 6.2 Test Commands

```bash
# Compile all models (syntax check)
dbt compile

# Run all tests
dbt test

# Run freshness checks
dbt source freshness

# Test specific model
dbt test --select stg_meta_ads_daily
```

---

## 7. Risk Assessment

### 7.1 Breaking Changes

| Change | Risk | Mitigation |
|--------|------|------------|
| Rename stg_meta_ads → stg_meta_ads_daily | MEDIUM | Update all refs in fact_ad_spend.sql |
| Rename stg_google_ads → stg_google_ads_daily | MEDIUM | Update all refs in fact_ad_spend.sql |
| Add columns to stg_shopify_orders | LOW | Additive only |

### 7.2 Downstream Impact

**Models that reference staging models:**
- `fact_ad_spend.sql:30` → refs `stg_meta_ads`
- `fact_ad_spend.sql:59` → refs `stg_google_ads`
- `fact_orders.sql` → refs `stg_shopify_orders`
- `fact_campaign_performance.sql` → refs ad staging models

**Required Updates:**
1. Update refs from `stg_meta_ads` → `stg_meta_ads_daily`
2. Update refs from `stg_google_ads` → `stg_google_ads_daily`

### 7.3 PII Compliance

**Excluded from all staging models:**
- Names (first_name, last_name, full_name)
- Email addresses
- Phone numbers
- Physical addresses (street, city, state, zip, country)
- Payment details (card numbers, bank accounts)

**Allowed:**
- IDs (order_id, customer_id, account_id, campaign_id)
- Metrics (spend, revenue, clicks, impressions)
- Dates/timestamps
- Status fields
- Non-PII metadata

---

## 8. Verification Checklist

### 8.1 Pre-Implementation

- [ ] Confirm raw table names match Airbyte output
- [ ] Verify freshness thresholds align with Story 7.6
- [ ] Confirm tenant_airbyte_connections has mappings for all sources

### 8.2 Post-Implementation

- [ ] All models compile: `dbt compile`
- [ ] All tests pass: `dbt test`
- [ ] Freshness checks configured: `dbt source freshness`
- [ ] No PII columns in any staging model
- [ ] Deterministic internal IDs verified
- [ ] Incremental logic handles late-arriving data
- [ ] Documentation complete

### 8.3 CI/CD Integration

- [ ] Add `dbt compile` to CI pipeline
- [ ] Add `dbt test` to CI pipeline
- [ ] Add `dbt source freshness` to scheduled checks
- [ ] Update deployment scripts for renamed models

---

## 9. Open Questions / Blockers

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | Are raw tables for TikTok, Pinterest, Snap, Amazon already in Airbyte? | Data Engineering | PENDING |
| 2 | What is the exact JSON structure for each new source? | Data Engineering | PENDING |
| 3 | Should stg_shopify_refunds be extracted from orders or separate table? | Architect | Recommend: Extract from orders (refunds_json) |
| 4 | Are Klaviyo events pre-aggregated or raw event-level? | Data Engineering | PENDING |
| 5 | GA4 schema - using BigQuery export or API? | Data Engineering | PENDING |

---

## 10. Appendix: Canonical Staging Model Contract

All daily advertising staging models MUST output these columns:

```sql
-- Required columns for stg_*_ads_daily models
tenant_id             VARCHAR NOT NULL  -- Tenant isolation
report_date           DATE NOT NULL     -- Date grain
source                VARCHAR NOT NULL  -- e.g., 'meta_ads', 'google_ads'
platform_channel      VARCHAR NOT NULL  -- Original platform
canonical_channel     VARCHAR NOT NULL  -- Normalized channel
platform_account_id   VARCHAR NOT NULL  -- Original account ID
internal_account_id   VARCHAR NOT NULL  -- md5(tenant|source|account)
platform_campaign_id  VARCHAR NOT NULL  -- Original campaign ID
internal_campaign_id  VARCHAR NOT NULL  -- md5(tenant|source|campaign)
spend                 NUMERIC NOT NULL  -- Ad spend
impressions           INTEGER NOT NULL  -- Impressions
clicks                INTEGER NOT NULL  -- Clicks
conversions           NUMERIC NOT NULL  -- Conversions
conversion_value      NUMERIC NOT NULL  -- Conversion value
cpm                   NUMERIC           -- Derived: (spend/impressions)*1000
cpc                   NUMERIC           -- Derived: spend/clicks
ctr                   NUMERIC           -- Derived: (clicks/impressions)*100
cpa                   NUMERIC           -- Derived: spend/conversions
roas_platform         NUMERIC           -- Derived: conversion_value/spend
currency              VARCHAR(3)        -- Currency code
airbyte_record_id     VARCHAR           -- Airbyte metadata
airbyte_emitted_at    TIMESTAMP         -- Airbyte metadata
```
