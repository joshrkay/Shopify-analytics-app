# Channel Taxonomy

This document defines the mapping between platform-specific channels and canonical channels
used for cross-platform reporting and analysis.

## Overview

The channel taxonomy provides two levels of classification:

1. **platform_channel**: The original channel classification from each data source
2. **canonical_channel**: A normalized classification for cross-platform analysis

## Canonical Channels

| Canonical Channel | Description | Example Sources |
|------------------|-------------|-----------------|
| `paid_social` | Paid advertising on social platforms | Meta Ads, TikTok Ads, Pinterest Ads, Snap Ads |
| `paid_search` | Paid search advertising | Google Ads Search, Amazon Sponsored Products |
| `organic_social` | Unpaid social media traffic | GA4 organic social |
| `organic_search` | Unpaid search engine traffic | GA4 organic search |
| `email` | Email marketing | Klaviyo email campaigns |
| `sms` | SMS marketing | Klaviyo SMS |
| `affiliate` | Affiliate marketing traffic | GA4 affiliate |
| `referral` | Non-affiliate referral traffic | GA4 referral |
| `direct` | Direct traffic (no referrer) | GA4 direct, Recharge |
| `display` | Display advertising | Google Display Network, Amazon DSP |
| `video` | Video advertising | YouTube Ads |
| `shopping` | Shopping/catalog ads | Google Shopping, Meta Shopping |
| `other` | Unclassified channels | Fallback |

## Platform-Specific Mappings

### Meta Ads

| Platform Channel (Objective) | Canonical Channel |
|------------------------------|-------------------|
| LINK_CLICKS | paid_social |
| POST_ENGAGEMENT | paid_social |
| VIDEO_VIEWS | video |
| REACH | paid_social |
| BRAND_AWARENESS | paid_social |
| CONVERSIONS | paid_social |
| CATALOG_SALES | shopping |
| PRODUCT_CATALOG_SALES | shopping |
| *default* | paid_social |

### Google Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| SEARCH | paid_search |
| SEARCH_NETWORK | paid_search |
| DISPLAY | display |
| DISPLAY_NETWORK | display |
| GDN | display |
| VIDEO | video |
| YOUTUBE | video |
| SHOPPING | shopping |
| GOOGLE_SHOPPING | shopping |
| PERFORMANCE_MAX | paid_search |
| DISCOVERY | display |
| DEMAND_GEN | display |
| *default* | paid_search |

### TikTok Ads

| Platform Channel (Objective) | Canonical Channel |
|-----------------------------|-------------------|
| TRAFFIC | paid_social |
| CONVERSIONS | paid_social |
| APP_INSTALL | paid_social |
| REACH | paid_social |
| VIDEO_VIEWS | paid_social |
| CATALOG_SALES | shopping |
| *default* | paid_social |

### Pinterest Ads

| Platform Channel (Objective) | Canonical Channel |
|-----------------------------|-------------------|
| AWARENESS | paid_social |
| CONSIDERATION | paid_social |
| CONVERSIONS | paid_social |
| CATALOG_SALES | shopping |
| *default* | paid_social |

### Snapchat Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| *all* | paid_social |

### Amazon Ads

| Platform Channel (Campaign Type) | Canonical Channel |
|---------------------------------|-------------------|
| SPONSORED_PRODUCTS | paid_search |
| SP | paid_search |
| SPONSORED_BRANDS | paid_search |
| SB | paid_search |
| SPONSORED_DISPLAY | display |
| SD | display |
| DSP | display |
| *default* | paid_search |

### Klaviyo

| Platform Channel (Message Type) | Canonical Channel |
|--------------------------------|-------------------|
| EMAIL | email |
| SMS | sms |
| *default* | email |

### GA4

GA4 uses Google's Default Channel Grouping. We map these directly:

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| Organic Search | organic_search |
| Organic Social | organic_social |
| Paid Search | paid_search |
| Paid Social | paid_social |
| Email | email |
| SMS | sms |
| Affiliates | affiliate |
| Referral | referral |
| Direct | direct |
| Display | display |
| Video | video |
| *default* | other |

### Recharge

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| subscription | direct |

Subscription commerce is classified as "direct" because subscriptions represent
a direct relationship with the store, not acquisition through a marketing channel.

### Shopify Orders (UTM-based)

When orders have UTM parameters, we map based on source patterns:

| UTM Pattern | Canonical Channel |
|------------|-------------------|
| facebook, instagram, meta | paid_social |
| google, gclid | paid_search |
| tiktok | paid_social |
| klaviyo, email | email |
| sms | sms |
| *null/empty* | direct |
| *other* | other |

## Implementation

The channel mapping is implemented in the macro:
`analytics/macros/map_canonical_channel.sql`

```sql
{{ map_canonical_channel('source_name', 'platform_channel_column') }}
```

### Example Usage

```sql
select
    platform_channel,
    {{ map_canonical_channel("'meta_ads'", 'objective') }} as canonical_channel
from stg_meta_ads_daily
```

## Adding New Channels

When adding a new data source:

1. Identify the platform-specific channel field
2. Document the mapping in this file
3. Update the `map_canonical_channel` macro
4. Add tests for the new mappings

## Best Practices

1. **Always store both levels**: Keep `platform_channel` for granular analysis
   and `canonical_channel` for cross-platform reporting

2. **Use canonical_channel for rollups**: When aggregating across platforms,
   always group by `canonical_channel`

3. **Document edge cases**: Platform behaviors change; document any special
   handling in the source model

4. **Test accepted values**: Schema tests should validate that `canonical_channel`
   only contains values from the defined taxonomy
