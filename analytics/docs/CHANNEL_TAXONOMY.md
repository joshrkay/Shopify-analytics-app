# Channel Taxonomy

This document defines the channel taxonomy used to normalize marketing channels across all advertising platforms. The taxonomy provides a consistent way to analyze and compare performance across different platforms and campaign types.

## Overview

The channel taxonomy consists of two levels:

1. **Platform Channel** (`platform_channel`): The raw channel/placement type as reported by the platform
2. **Canonical Channel** (`canonical_channel`): A normalized channel category for cross-platform comparison

## Canonical Channels

| Canonical Channel | Description | Example Platforms |
|-------------------|-------------|-------------------|
| `paid_social` | Paid advertising on social media platforms | Meta (Facebook/Instagram), TikTok, Snapchat, Pinterest |
| `paid_search` | Paid search engine advertising | Google Search, Bing Search |
| `paid_shopping` | Product listing and shopping ads | Google Shopping, Amazon Sponsored Products |
| `paid_display` | Display and banner advertising | Google Display Network |
| `paid_video` | Video advertising | YouTube, TikTok, Meta Video |
| `email` | Email marketing campaigns | Klaviyo Email |
| `sms` | SMS/text message marketing | Klaviyo SMS |
| `push` | Push notifications | Klaviyo Push |
| `organic_social` | Unpaid social media traffic | - |
| `organic_search` | Unpaid search engine traffic | Google Organic, Bing Organic |
| `direct` | Direct traffic (no referrer) | - |
| `referral` | Traffic from other websites | - |
| `affiliate` | Affiliate marketing traffic | - |
| `other` | Unclassified or unknown channels | - |

## Platform-to-Canonical Mappings

### Meta Ads (Facebook/Instagram)

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `facebook` | `paid_social` |
| `instagram` | `paid_social` |
| `messenger` | `paid_social` |
| `audience_network` | `paid_display` |
| `feed` | `paid_social` |
| `stories` | `paid_social` |
| `reels` | `paid_video` |
| `video` | `paid_video` |
| `marketplace` | `paid_shopping` |
| `shop` | `paid_shopping` |
| (default) | `paid_social` |

### Google Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `search` | `paid_search` |
| `display` | `paid_display` |
| `shopping` | `paid_shopping` |
| `video` | `paid_video` |
| `youtube` | `paid_video` |
| `pmax` | `paid_search` |
| `performance_max` | `paid_search` |
| `discovery` | `paid_display` |
| `app` | `paid_display` |
| (default) | `paid_search` |

### TikTok Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `feed` | `paid_social` |
| `in_feed` | `paid_social` |
| `for_you` | `paid_social` |
| `topview` | `paid_video` |
| `branded_effect` | `paid_social` |
| `branded_hashtag` | `paid_social` |
| `spark_ads` | `paid_social` |
| `search` | `paid_search` |
| `shop` | `paid_shopping` |
| `shopping` | `paid_shopping` |
| (default) | `paid_social` |

### Pinterest Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `browse` | `paid_social` |
| `search` | `paid_search` |
| `shopping` | `paid_shopping` |
| `collections` | `paid_shopping` |
| `video` | `paid_video` |
| `carousel` | `paid_social` |
| `app_install` | `paid_social` |
| (default) | `paid_social` |

### Snapchat Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `snap_ads` | `paid_social` |
| `story_ads` | `paid_social` |
| `collection_ads` | `paid_shopping` |
| `dynamic_ads` | `paid_shopping` |
| `commercials` | `paid_video` |
| `lenses` | `paid_social` |
| `filters` | `paid_social` |
| `spotlight` | `paid_video` |
| (default) | `paid_social` |

### Amazon Ads

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `sponsored_products` | `paid_shopping` |
| `sponsored_brands` | `paid_shopping` |
| `sponsored_display` | `paid_display` |
| `video` | `paid_video` |
| `dsp` | `paid_display` |
| `stores` | `paid_shopping` |
| `posts` | `paid_social` |
| (default) | `paid_shopping` |

### Klaviyo

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `email` | `email` |
| `sms` | `sms` |
| `push` | `push` |
| `flow` | `email` |
| `campaign` | `email` |
| (default) | `email` |

### GA4 (Google Analytics 4)

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `organic_search` | `organic_search` |
| `organic_social` | `organic_social` |
| `direct` | `direct` |
| `referral` | `referral` |
| `paid_search` | `paid_search` |
| `paid_social` | `paid_social` |
| `paid_shopping` | `paid_shopping` |
| `display` | `paid_display` |
| `video` | `paid_video` |
| `email` | `email` |
| `sms` | `sms` |
| `affiliate` | `affiliate` |
| `audio` | `other` |
| `cross-network` | `paid_display` |
| (default) | `other` |

### ReCharge

| Platform Channel | Canonical Channel |
|-----------------|-------------------|
| `subscription` | `direct` |
| `checkout` | `direct` |
| `portal` | `direct` |
| (default) | `direct` |

## Using the Macro

The `map_canonical_channel` macro handles the mapping automatically:

```sql
{{ map_canonical_channel('source', 'platform_channel') }} as canonical_channel
```

Where:
- `source` is the platform identifier (e.g., 'meta_ads', 'google_ads')
- `platform_channel` is the raw channel value from the platform

## Adding New Mappings

To add new channel mappings:

1. Edit `analytics/macros/map_canonical_channel.sql`
2. Add a new `when` clause for the source
3. Add the platform channel to canonical channel mappings
4. Update this documentation

## Best Practices

1. **Default Fallbacks**: Each platform has a sensible default when the platform channel is unknown
2. **Case Insensitivity**: All comparisons are lowercase for consistency
3. **Unknown Channels**: Log and monitor 'other' classifications to identify new platform channels that need mapping
4. **Cross-Platform Analysis**: Use `canonical_channel` for comparing performance across platforms

## Query Examples

### Spend by Canonical Channel
```sql
select
    canonical_channel,
    sum(spend) as total_spend
from {{ ref('stg_meta_ads') }}
group by 1
order by 2 desc
```

### Cross-Platform Channel Comparison
```sql
with all_ads as (
    select canonical_channel, spend, clicks, conversions from {{ ref('stg_meta_ads') }}
    union all
    select canonical_channel, spend, clicks, conversions from {{ ref('stg_google_ads') }}
    union all
    select canonical_channel, spend, clicks, conversions from {{ ref('stg_tiktok_ads_daily') }}
)
select
    canonical_channel,
    sum(spend) as total_spend,
    sum(clicks) as total_clicks,
    sum(conversions) as total_conversions,
    case when sum(clicks) > 0 then sum(spend) / sum(clicks) else null end as avg_cpc,
    case when sum(conversions) > 0 then sum(spend) / sum(conversions) else null end as avg_cpa
from all_ads
group by 1
order by 2 desc
```
