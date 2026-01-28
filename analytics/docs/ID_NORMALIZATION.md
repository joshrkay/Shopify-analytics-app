# ID Normalization (Option B)

This document describes the ID normalization strategy implemented in the Shopify Analytics dbt models. We use **Option B: Internal Normalized IDs** to enable consistent cross-platform joins while preserving original platform identifiers.

## Overview

### The Problem

Each advertising platform uses its own ID formats and schemes:

| Platform | Account ID Format | Campaign ID Format |
|----------|------------------|-------------------|
| Meta Ads | `act_123456789012` | `23842573891230123` |
| Google Ads | `123-456-7890` | `12345678901` |
| TikTok Ads | `7012345678901234567` | `1234567890123456789` |
| Pinterest | `549755813888` | `630215278423` |
| Snapchat | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` | `campaign-uuid` |
| Amazon | `ENTITYABCDEF123` | `SP123456789` |

These incompatible formats make cross-platform analysis difficult.

### Option B Solution

We generate **internal normalized IDs** that:

1. Are deterministic (same inputs always produce same output)
2. Are unique across tenants, platforms, and entities
3. Can be used for consistent joins across platforms
4. Preserve original platform IDs as attributes for debugging

## Implementation

### The `generate_internal_id` Macro

```sql
{% macro generate_internal_id(tenant_id, source, platform_id) %}
case
    when {{ tenant_id }} is null or {{ source }} is null or {{ platform_id }} is null
    then null
    else md5(
        cast({{ tenant_id }} as text) || '|' ||
        cast({{ source }} as text) || '|' ||
        cast({{ platform_id }} as text)
    )
end
{% endmacro %}
```

The macro generates an MD5 hash of `tenant_id|source|platform_id`, producing a 32-character hexadecimal string.

### Example

Given:
- tenant_id: `tenant_abc`
- source: `meta_ads`
- platform_id: `act_123456789012`

The internal ID would be:
```
md5('tenant_abc|meta_ads|act_123456789012') = 'a1b2c3d4e5f6789012345678abcdef01'
```

## Generated ID Columns

### Staging Models

Each staging model generates these internal IDs:

| Column | Generated From | Purpose |
|--------|---------------|---------|
| `internal_account_id` | `tenant_id + source + ad_account_id` | Cross-platform account joins |
| `internal_campaign_id` | `tenant_id + source + campaign_id` | Cross-platform campaign joins |

Example from `stg_meta_ads.sql`:

```sql
select
    -- Platform IDs (original)
    ad_account_id,
    campaign_id,

    -- Internal IDs (normalized)
    {{ generate_internal_id('tenant_id', 'source', 'ad_account_id') }} as internal_account_id,
    {{ generate_internal_id('tenant_id', 'source', 'campaign_id') }} as internal_campaign_id,

    -- ...other columns
```

### Dimension Tables

Dimension tables (`dim_ad_accounts`, `dim_campaigns`) union all platforms and provide the mapping between platform IDs and internal IDs:

```sql
-- dim_ad_accounts
select
    tenant_id,
    source,                    -- e.g., 'meta_ads', 'google_ads'
    platform_account_id,       -- Original platform ID
    internal_account_id,       -- Normalized ID for joins
    currency,
    first_seen_at,
    last_seen_at
from all_accounts
```

## Usage Patterns

### Cross-Platform Account Analysis

```sql
-- Compare spend across all ad accounts
with account_spend as (
    select
        internal_account_id,
        sum(spend) as total_spend
    from {{ ref('stg_meta_ads') }}
    group by 1

    union all

    select
        internal_account_id,
        sum(spend) as total_spend
    from {{ ref('stg_google_ads') }}
    group by 1
)
select
    a.source,
    a.platform_account_id,
    s.total_spend
from account_spend s
join {{ ref('dim_ad_accounts') }} a
    on s.internal_account_id = a.internal_account_id
order by s.total_spend desc
```

### Cross-Platform Campaign Performance

```sql
-- Top campaigns by ROAS across all platforms
with campaign_metrics as (
    select internal_campaign_id, sum(spend) as spend, sum(conversion_value) as value
    from {{ ref('stg_meta_ads') }}
    group by 1

    union all

    select internal_campaign_id, sum(spend) as spend, sum(conversion_value) as value
    from {{ ref('stg_google_ads') }}
    group by 1
)
select
    c.source,
    c.campaign_name,
    cm.spend,
    cm.value,
    case when cm.spend > 0 then cm.value / cm.spend else null end as roas
from campaign_metrics cm
join {{ ref('dim_campaigns') }} c
    on cm.internal_campaign_id = c.internal_campaign_id
where cm.spend > 100
order by roas desc
limit 20
```

### Joining with Dimension Tables

```sql
-- Get account details for a campaign
select
    c.campaign_name,
    c.source,
    a.platform_account_id,
    a.currency
from {{ ref('dim_campaigns') }} c
join {{ ref('dim_ad_accounts') }} a
    on c.internal_account_id = a.internal_account_id
where c.internal_campaign_id = 'a1b2c3d4e5f6789012345678abcdef01'
```

## Properties of Internal IDs

### Determinism

The same inputs will always produce the same internal ID:

```sql
-- These will always produce the same result:
md5('tenant_abc|meta_ads|act_123') = 'xyz...'
md5('tenant_abc|meta_ads|act_123') = 'xyz...'
```

### Uniqueness

IDs are unique across:

1. **Tenants**: Different tenants have different hashes even for same platform IDs
2. **Platforms**: Same ID on different platforms produces different hashes
3. **Entities**: Account IDs and campaign IDs are namespaced by their context

```sql
-- Different tenants = different hashes
md5('tenant_abc|meta_ads|act_123') != md5('tenant_xyz|meta_ads|act_123')

-- Different platforms = different hashes
md5('tenant_abc|meta_ads|123') != md5('tenant_abc|google_ads|123')
```

### Collision Resistance

MD5 produces a 128-bit hash, making collisions extremely unlikely in practice for our use case. With millions of IDs, the probability of collision is negligible.

### NULL Handling

If any input is NULL, the internal ID is NULL:

```sql
-- Returns NULL
{{ generate_internal_id('null', "'meta_ads'", "'act_123'") }}

-- Returns NULL
{{ generate_internal_id("'tenant_abc'", "'meta_ads'", 'null') }}
```

## Comparison with Other Options

### Option A: Unified ID Namespace

Pros:
- Single ID format across all platforms
- Simpler to understand

Cons:
- Requires maintaining a mapping table
- Complex ID generation/lookup logic
- Hard to trace back to original platform

### Option B: Internal Normalized IDs (Chosen)

Pros:
- Deterministic - no lookup required
- Original IDs preserved
- No state management needed
- Works with incremental processing

Cons:
- IDs are not human-readable
- Requires both columns (platform + internal)

### Option C: Composite Keys

Pros:
- Simple concatenation
- Human-readable

Cons:
- Variable length
- String comparison performance
- Potential delimiter conflicts

## Best Practices

1. **Always use internal IDs for joins** between staging models from different platforms

2. **Use platform IDs for debugging** and tracing back to source systems

3. **Include both IDs** in any cross-platform analysis output

4. **Never modify the hash algorithm** - changing the algorithm would break all existing joins

5. **Validate null inputs** - ensure you handle cases where platform IDs might be null

## Testing

The `generate_internal_id` macro is tested in `analytics/tests/macros/test_generate_internal_id.sql`:

```sql
-- Test: Same inputs produce same output
-- Test: Different inputs produce different outputs
-- Test: NULL inputs produce NULL output
-- Test: Output is valid 32-character MD5 hash
```

Run tests with:

```bash
dbt test --select test_generate_internal_id
```
