# Channel Taxonomy

This document defines the channel taxonomy used across the Shopify Analytics Platform. The system maintains both platform-specific channels (as reported by each source) and canonical channels (standardized for cross-platform analysis).

## Dual Channel Structure

Each record in staging models contains:
- **platform_channel**: The original channel value from the source platform
- **canonical_channel**: A normalized channel from the standard taxonomy

This approach allows:
- Preservation of granular platform-specific data
- Consistent cross-platform reporting and comparison
- Flexible analysis at either level of detail

## Canonical Channels

The following canonical channels are used across all platforms:

| Channel | Description | Example Sources |
|---------|-------------|-----------------|
| `paid_social` | Paid advertising on social platforms | Meta Ads (Facebook/Instagram), TikTok Ads, Snapchat Ads |
| `paid_search` | Paid search advertising | Google Ads Search, Bing Ads |
| `display` | Display/banner advertising | Google Display Network, Meta Audience Network |
| `video` | Video advertising | YouTube Ads, TikTok TopView, Meta Video |
| `shopping` | Product/catalog advertising | Google Shopping, Meta Catalog, Amazon Sponsored Products |
| `email` | Email marketing | Klaviyo campaigns, flows |
| `organic_social` | Unpaid social media traffic | GA4 organic social |
| `organic_search` | Unpaid search engine traffic | GA4 organic search |
| `direct` | Direct website visits | Shopify web store, typed URLs |
| `referral` | Referral traffic from other sites | GA4 referral |
| `affiliate` | Affiliate marketing traffic | GA4 affiliate |
| `sms` | SMS/text marketing | Klaviyo SMS |
| `push` | Push notifications | Klaviyo push |
| `marketplace` | Marketplace channels | Amazon, Meta Marketplace |
| `other` | Unclassified traffic | Default fallback |

## Platform-Specific Mappings

### Meta Ads (Facebook/Instagram)

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `facebook_feed` | `paid_social` |
| `instagram_feed` | `paid_social` |
| `facebook_stories` | `paid_social` |
| `instagram_stories` | `paid_social` |
| `facebook_reels` | `paid_social` |
| `instagram_reels` | `paid_social` |
| `messenger_inbox` | `paid_social` |
| `audience_network` | `paid_social` |
| `facebook_marketplace` | `marketplace` |
| `video` | `video` |
| `in_stream_video` | `video` |
| `audience_network_classic` | `display` |
| *(default)* | `paid_social` |

### Google Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `search` | `paid_search` |
| `search_network` | `paid_search` |
| `display` | `display` |
| `display_network` | `display` |
| `video` | `video` |
| `youtube` | `video` |
| `shopping` | `shopping` |
| `google_shopping` | `shopping` |
| `discovery` | `paid_social` |
| `demand_gen` | `paid_social` |
| `performance_max` | `paid_search` |
| *(default)* | `paid_search` |

### TikTok Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `tiktok_feed` | `paid_social` |
| `in_feed` | `paid_social` |
| `for_you` | `paid_social` |
| `spark_ads` | `paid_social` |
| `topview` | `video` |
| `brand_takeover` | `video` |
| `pangle` | `display` |
| *(default)* | `paid_social` |

### Pinterest Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `browse` | `paid_social` |
| `home_feed` | `paid_social` |
| `search` | `paid_search` |
| `pinterest_search` | `paid_search` |
| `shopping` | `shopping` |
| `catalog` | `shopping` |
| `video` | `video` |
| *(default)* | `paid_social` |

### Snapchat Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `snap_ads` | `paid_social` |
| `story_ads` | `paid_social` |
| `spotlight` | `video` |
| `discover` | `display` |
| `collection` | `shopping` |
| `dynamic_ads` | `shopping` |
| *(default)* | `paid_social` |

### Amazon Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `sponsored_products` | `shopping` |
| `sponsored_brands` | `paid_search` |
| `headline_search` | `paid_search` |
| `sponsored_display` | `display` |
| `dsp` | `display` |
| `video` | `video` |
| `streaming_tv` | `video` |
| *(default)* | `marketplace` |

### Klaviyo

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `email` | `email` |
| `campaign` | `email` |
| `flow` | `email` |
| `automation` | `email` |
| `sms` | `sms` |
| `text` | `sms` |
| `push` | `push` |
| `mobile_push` | `push` |
| *(default)* | `email` |

### Google Analytics 4

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `organic search` | `organic_search` |
| `paid search` | `paid_search` |
| `cpc` | `paid_search` |
| `organic social` | `organic_social` |
| `paid social` | `paid_social` |
| `email` | `email` |
| `display` | `display` |
| `video` | `video` |
| `referral` | `referral` |
| `direct` | `direct` |
| `(direct)` | `direct` |
| `(none)` | `direct` |
| `affiliate` | `affiliate` |
| *(default)* | `other` |

### Shopify

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `online_store` | `direct` |
| `web` | `direct` |
| `pos` | `direct` |
| `draft_orders` | `direct` |
| `shopify_inbox` | `direct` |
| *(default)* | `direct` |

### ReCharge

All ReCharge subscription charges are mapped to `direct` as they represent recurring customer relationships.

## Implementation

Channel mapping is implemented in the `map_canonical_channel` macro located at:
```
analytics/macros/channel_mapping.sql
```

Usage in staging models:
```sql
{{ map_canonical_channel("'meta_ads'", 'platform_channel') }} as canonical_channel
```

## Extending the Taxonomy

When adding new platforms or channels:

1. Add the platform-specific mappings to `macros/channel_mapping.sql`
2. Update this documentation with the new mappings
3. If a new canonical channel is needed, add it to:
   - The `canonical_channels` var in `dbt_project.yml`
   - The table above
4. Run `dbt test` to verify `accepted_values` tests pass

## Best Practices

1. **Always preserve platform_channel**: Even when creating aggregations, keep the original platform channel available for drill-down analysis.

2. **Use canonical_channel for cross-platform reports**: When comparing performance across platforms, always use the canonical channel.

3. **Default carefully**: When a platform channel can't be mapped, use the most common channel for that platform as the default.

4. **Case insensitivity**: Channel mapping is case-insensitive. Both `Search` and `search` map to the same canonical channel.
