# ID Normalization

This document describes the ID normalization strategy used across the Shopify Analytics Platform to create stable, deterministic identifiers for cross-platform analysis.

## Overview

The platform uses **Option B: Generated Internal IDs** with platform IDs retained as attributes. This approach:

- Creates stable, reproducible internal IDs using MD5 hashing
- Preserves original platform IDs for reference and debugging
- Enables efficient joins across different source systems
- Supports multi-tenant isolation

## ID Generation Formula

All internal IDs are generated using the following formula:

```
internal_id = prefix + '_' + md5(tenant_id + '|' + source + '|' + platform_id)
```

Where:
- **prefix**: Entity type identifier (e.g., 'acc', 'cmp', 'adg', 'ad')
- **tenant_id**: The tenant identifier for multi-tenant isolation
- **source**: The platform/source identifier (e.g., 'meta_ads', 'google_ads')
- **platform_id**: The original ID from the source platform
- **'|'**: Pipe delimiter to prevent collision

### Why MD5?

- **Deterministic**: Same inputs always produce the same output
- **Fixed length**: Always 32 characters
- **Good distribution**: Minimizes collision risk
- **Performant**: Fast to compute, efficient for indexing

### Why Pipe Delimiter?

The pipe delimiter prevents ID collisions between different concatenation patterns:

Without delimiter:
- `tenant='abc', source='def', id='123'` → `'abcdef123'`
- `tenant='ab', source='cdef', id='123'` → `'abcdef123'` (collision!)

With delimiter:
- `tenant='abc', source='def', id='123'` → `'abc|def|123'`
- `tenant='ab', source='cdef', id='123'` → `'ab|cdef|123'` (no collision)

## ID Types

### Account IDs

**Internal Format**: `acc_<32-char-md5-hash>`

**Generation**:
```sql
{{ generate_internal_account_id('tenant_id', "'meta_ads'", 'platform_account_id') }}
```

**Example**:
- Platform: Meta Ads
- Tenant ID: `tenant_123`
- Platform Account ID: `act_456789`
- Internal Account ID: `acc_a1b2c3d4e5f6...` (32 chars)

### Campaign IDs

**Internal Format**: `cmp_<32-char-md5-hash>`

**Generation**:
```sql
{{ generate_internal_campaign_id('tenant_id', "'google_ads'", 'platform_campaign_id') }}
```

**Example**:
- Platform: Google Ads
- Tenant ID: `tenant_123`
- Platform Campaign ID: `12345678901`
- Internal Campaign ID: `cmp_f1e2d3c4b5a6...` (32 chars)

### Ad Group IDs

**Internal Format**: `adg_<32-char-md5-hash>`

**Generation**:
```sql
{{ generate_internal_adgroup_id('tenant_id', "'tiktok_ads'", 'platform_adgroup_id') }}
```

### Ad IDs

**Internal Format**: `ad_<32-char-md5-hash>`

**Generation**:
```sql
{{ generate_internal_ad_id('tenant_id', "'snap_ads'", 'platform_ad_id') }}
```

## Dimension Tables

The platform maintains two dimension tables for ID mapping:

### dim_ad_accounts

Maps platform account IDs to internal account IDs across all platforms.

| Column | Description |
|--------|-------------|
| `account_surrogate_key` | Primary key for the dimension row |
| `tenant_id` | Tenant identifier |
| `source` | Platform identifier |
| `platform_account_id` | Original platform account ID |
| `internal_account_id` | Generated internal account ID |
| `account_display_name` | Human-readable name |
| `account_status` | active/inactive/dormant |
| `last_seen_at` | Last activity timestamp |

### dim_campaigns

Maps platform campaign IDs to internal campaign IDs across all platforms.

| Column | Description |
|--------|-------------|
| `campaign_surrogate_key` | Primary key for the dimension row |
| `tenant_id` | Tenant identifier |
| `source` | Platform identifier |
| `platform_account_id` | Parent account ID |
| `internal_account_id` | Parent internal account ID |
| `platform_campaign_id` | Original platform campaign ID |
| `internal_campaign_id` | Generated internal campaign ID |
| `campaign_name` | Campaign name from platform |
| `objective` | Campaign objective |
| `canonical_channel` | Normalized channel |
| `campaign_status` | active/paused/inactive/archived |
| `first_seen_at` | First activity date |
| `last_seen_at` | Last activity date |

## Usage in Staging Models

Every staging model includes both platform and internal IDs:

```sql
-- Platform IDs (original)
platform_account_id,
platform_campaign_id,
platform_adgroup_id,
platform_ad_id,

-- Internal IDs (generated)
{{ generate_internal_account_id('tenant_id', "'meta_ads'", 'platform_account_id') }} as internal_account_id,
{{ generate_internal_campaign_id('tenant_id', "'meta_ads'", 'platform_campaign_id') }} as internal_campaign_id,
{{ generate_internal_adgroup_id('tenant_id', "'meta_ads'", 'platform_adgroup_id') }} as internal_adgroup_id,
{{ generate_internal_ad_id('tenant_id', "'meta_ads'", 'platform_ad_id') }} as internal_ad_id,
```

## Joining Across Platforms

Internal IDs enable efficient cross-platform analysis:

```sql
-- Aggregate spend by internal campaign across platforms
SELECT
    internal_campaign_id,
    SUM(spend) as total_spend
FROM {{ ref('stg_ads_daily_union') }}
GROUP BY 1
```

## Multi-Tenant Isolation

The tenant_id is always included in the hash input, ensuring:

1. **Complete isolation**: Same platform ID for different tenants produces different internal IDs
2. **No cross-tenant joins**: Internal IDs are tenant-scoped by design
3. **Audit trail**: Internal ID can be traced back to tenant + source + platform ID

## Collision Probability

MD5 produces a 128-bit hash. Given:
- ~1 million unique combinations per tenant
- 1000 tenants
- 10 platforms per tenant

Total combinations: ~10 billion

Probability of collision: Effectively zero (< 10^-18)

## Macro Reference

Located in `analytics/macros/generate_internal_id.sql`:

| Macro | Description |
|-------|-------------|
| `generate_internal_id(tenant_id, source, platform_id)` | Base ID generation |
| `generate_internal_account_id(...)` | Account ID with 'acc_' prefix |
| `generate_internal_campaign_id(...)` | Campaign ID with 'cmp_' prefix |
| `generate_internal_adgroup_id(...)` | Ad group ID with 'adg_' prefix |
| `generate_internal_ad_id(...)` | Ad ID with 'ad_' prefix |
| `generate_composite_key(tenant_id, *fields)` | Multi-field composite key |

## Best Practices

1. **Always include tenant_id**: Even for single-tenant deployments, include tenant_id for future scalability.

2. **Use source constants**: Pass source as a string literal (e.g., `"'meta_ads'"`) to ensure consistency.

3. **Preserve platform IDs**: Always keep the original platform IDs for debugging and API lookups.

4. **Use dimension tables**: Join through dimension tables for enriched data like campaign names.

5. **Index internal IDs**: Internal IDs should be indexed in downstream tables for performance.

## Troubleshooting

### Different IDs for Same Entity

Check that:
- `tenant_id` is consistent (not null)
- `source` string is exactly the same (case-sensitive)
- `platform_id` hasn't changed format (e.g., trailing spaces)

### Debugging an Internal ID

To find the source of an internal ID:
```sql
SELECT *
FROM {{ ref('dim_campaigns') }}
WHERE internal_campaign_id = 'cmp_a1b2c3d4e5f6...'
```
