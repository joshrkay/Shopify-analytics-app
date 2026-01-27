# ID Normalization

This document describes how internal IDs are generated and used for cross-platform
identity resolution in the Shopify Analytics Platform.

## Overview

The platform uses **Option B** for ID normalization:

> Generate internal normalized IDs; keep platform IDs as attributes.

This approach:
- Creates deterministic internal IDs using hashing
- Preserves original platform IDs for debugging and platform-specific queries
- Enables reliable cross-platform joins
- Maintains tenant isolation in ID generation

## ID Generation Formula

Internal IDs are generated using MD5 hashing:

```
internal_id = MD5(tenant_id || '|' || source || '|' || platform_id)
```

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| `tenant_id` | Tenant identifier (UUID) | `abc123-def456-...` |
| `source` | Platform identifier | `meta_ads`, `google_ads` |
| `platform_id` | Original platform ID | `123456789` |
| Delimiter | Separator character | `\|` (pipe) |

### Properties

1. **Deterministic**: Same inputs always produce same output
2. **Unique per tenant**: Includes tenant_id to prevent cross-tenant collisions
3. **Unique per source**: Includes source to prevent cross-platform collisions
4. **Stable**: IDs don't change unless underlying components change
5. **Fixed length**: MD5 produces 32-character hexadecimal string

## Implementation

### Macro: generate_internal_id

Located at: `analytics/macros/generate_internal_id.sql`

```sql
{% macro generate_internal_id(tenant_id, source, platform_id) %}
    md5({{ tenant_id }}::text || '|' || {{ source }}::text || '|' || {{ platform_id }}::text)
{% endmacro %}
```

### Convenience Macros

```sql
-- For ad accounts
{{ generate_internal_account_id('tenant_id', 'source', 'platform_account_id') }}

-- For campaigns
{{ generate_internal_campaign_id('tenant_id', 'source', 'platform_campaign_id') }}

-- For composite keys (multiple columns)
{{ generate_composite_key(['tenant_id', 'report_date', 'campaign_id']) }}
```

## Dimension Tables

### dim_ad_accounts

Maps platform account IDs to internal account IDs.

| Column | Description |
|--------|-------------|
| `internal_account_id` | Generated internal ID (primary key) |
| `tenant_id` | Tenant identifier |
| `source` | Platform (meta_ads, google_ads, etc.) |
| `platform_account_id` | Original platform account ID |
| `currency` | Account currency |
| `first_seen_at` | First observation |
| `last_seen_at` | Most recent observation |

### dim_campaigns

Maps platform campaign IDs to internal campaign IDs.

| Column | Description |
|--------|-------------|
| `internal_campaign_id` | Generated internal ID (primary key) |
| `internal_account_id` | Parent account (foreign key) |
| `tenant_id` | Tenant identifier |
| `source` | Platform |
| `platform_account_id` | Original account ID |
| `platform_campaign_id` | Original campaign ID |
| `campaign_name` | Campaign name |
| `campaign_objective` | Campaign objective/goal |
| `campaign_type` | Campaign type |
| `first_seen_at` | First observation |
| `last_seen_at` | Most recent observation |

## Usage in Staging Models

Each staging model generates internal IDs inline:

```sql
select
    tenant_id,
    platform_account_id,
    platform_campaign_id,
    -- Internal IDs
    {{ generate_internal_account_id('tenant_id', "'meta_ads'", 'platform_account_id') }}
        as internal_account_id,
    {{ generate_internal_campaign_id('tenant_id', "'meta_ads'", 'platform_campaign_id') }}
        as internal_campaign_id,
    ...
from source_data
```

## Cross-Platform Joins

Internal IDs enable joining data across platforms:

```sql
-- Join Meta and Google campaign performance
select
    c.campaign_name,
    m.spend as meta_spend,
    g.spend as google_spend
from dim_campaigns c
left join stg_meta_ads_daily m
    on c.internal_campaign_id = m.internal_campaign_id
left join stg_google_ads_daily g
    on c.internal_campaign_id = g.internal_campaign_id
```

## ID Consistency Guarantees

### Same ID Guaranteed When:
- Same tenant_id
- Same source
- Same platform_id

### Different ID Guaranteed When:
- Different tenant_id (even if same platform_id)
- Different source (even if same platform_id)
- Different platform_id

## Testing

### Relationship Tests

The schema.yml includes relationship tests:

```yaml
- name: internal_campaign_id
  tests:
    - relationships:
        to: ref('dim_campaigns')
        field: internal_campaign_id
        config:
          severity: warn
```

### Uniqueness Tests

Dimension tables have uniqueness tests on internal IDs:

```yaml
- name: internal_account_id
  tests:
    - not_null
    - unique
```

## Migration Considerations

If platform IDs change (rare):
1. Internal IDs will change
2. Historical data will have old internal IDs
3. Use `platform_id` for joins during migration
4. Consider a mapping table for ID transitions

## Edge Cases

### Null Platform IDs

Internal ID generation handles nulls:
- `coalesce(platform_id, '')` prevents null propagation
- Resulting ID is still unique per tenant/source

### ID Collisions

MD5 collision probability is negligible for our use case:
- ~3.7 × 10^38 possible values
- Would need ~2^64 records for 50% collision probability
- Acceptable for analytics purposes

### Case Sensitivity

Platform IDs are case-sensitive:
- `Campaign123` ≠ `campaign123`
- Source names are lowercase by convention

## Best Practices

1. **Always use macros**: Don't manually construct internal IDs

2. **Include both IDs in exports**: When exporting data, include both
   `internal_id` and `platform_id` for debugging

3. **Join on internal IDs**: Use internal IDs for all cross-model joins

4. **Filter by tenant_id**: Always include tenant_id in queries for security

5. **Document platform ID formats**: Each source may have different ID formats
   (numeric, string, UUID, etc.)
