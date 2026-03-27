# Airbyte Cloud Connections Runbook

## Production Connection Inventory

| Connection | Airbyte ID | Source → Destination | Schema | Status |
|---|---|---|---|---|
| Shopify → MarkInsight DB | `f87a1906-6cf4-482d-8667-cbadc65f8401` | Shopify (`98a06836`) → Postgres (`0fa4796b`) | `airbyte_raw` (orders, customers) | Active |
| Facebook Marketing → MarkInsight DB | `8bb25ebb-7497-4a7b-80b5-437e35c561f3` | Facebook (`959d55ca`) → Postgres (`0fa4796b`) | `airbyte_google_ads` (ads_insights) | Active |
| Google Ads → MarkInsight DB | `516b10d7-99ce-45fe-8cbe-0066e7670b23` | Google Ads (`af6b2268`) → Postgres (`0fa4796b`) | `airbyte_google_ads` (account_performance_report) | Failing |

**Workspace ID:** `6a588966-273f-46d6-89b7-846597667768`

## Quick Health Check

```bash
# Run the health check script (requires env vars)
export AIRBYTE_CLOUD_CLIENT_ID=c867d271-d5b9-4d35-aaa6-a4b5aa713238
export AIRBYTE_CLOUD_CLIENT_SECRET=<secret>
export AIRBYTE_CLOUD_WORKSPACE_ID=6a588966-273f-46d6-89b7-846597667768

python scripts/check_airbyte_health.py
```

## Debugging a Failed Sync

### 1. Get the error from the API

```bash
# Get OAuth token
TOKEN=$(curl -s -X POST https://api.airbyte.com/v1/applications/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "<CLIENT_ID>", "client_secret": "<CLIENT_SECRET>"}' | jq -r '.access_token')

# List jobs for a connection (most recent first)
curl -s "https://api.airbyte.com/v1/jobs?connectionId=<CONNECTION_ID>&limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {status, startTime, rowsSynced, duration}'
```

### 2. Check the Airbyte Cloud UI

1. Go to https://cloud.airbyte.com
2. Select workspace "MarkInsight"
3. Click Connections → select the failing connection
4. Click "Job History" tab → expand the failed job → "Logs"

### 3. Common failure patterns

| Error | Cause | Fix |
|---|---|---|
| `AUTHENTICATION_ERROR` | OAuth token expired | Re-authenticate via app OAuth flow or Airbyte UI |
| `PERMISSION_DENIED` | API credentials revoked | Re-authorize the ad account in the source platform |
| `RATE_LIMIT` | Too many API calls | Reduce sync frequency or batch size |
| `CONNECTION_TIMEOUT` | Network issue | Retry; check Render DB connectivity |

## Fixing Google Ads Sync

Google Ads syncs fail most often due to expired OAuth credentials or missing developer token.

### Re-authenticate via Airbyte Cloud UI

1. Go to Airbyte Cloud → Sources → "Google Ads"
2. Click "Edit" → "Re-authenticate"
3. Complete the Google OAuth flow with an account that has access to the ad account
4. Save and trigger a manual sync

### Change schedule from Manual to Automatic

```bash
# Via API:
curl -X PATCH "https://api.airbyte.com/v1/connections/<CONNECTION_ID>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"schedule": {"scheduleType": "cron", "cronExpression": "0 0 * * *"}}'
```

Or in the Airbyte Cloud UI: Connection → Settings → Schedule → "Every 24 hours"

### Required environment variables

The Google Ads source requires these in the backend for OAuth-initiated connections:

- `GOOGLE_CLIENT_ID` — Google OAuth app client ID
- `GOOGLE_CLIENT_SECRET` — Google OAuth app secret
- `GOOGLE_ADS_DEVELOPER_TOKEN` — Google Ads API developer token (from Google Ads Manager)

## Schema Architecture (Destinations V2)

Airbyte Cloud uses **Destinations V2** with typed columns:

- **No `_airbyte_data` JSONB blob** — fields are typed columns directly
- **Metadata columns:** `_airbyte_raw_id`, `_airbyte_extracted_at`, `_airbyte_meta`
- **Schema naming:** determined by connection's `namespaceFormat` setting

Current schema layout:
```
airbyte_raw/
  orders          ← Shopify orders (typed columns: id, name, email, created_at, ...)
  customers       ← Shopify customers (typed columns: id, email, first_name, ...)

airbyte_google_ads/
  ads_insights            ← Facebook Marketing data (despite schema name)
  account_performance_report  ← Google Ads data (created on first successful sync)
```

**Why Facebook data is in `airbyte_google_ads`:** The PostgreSQL destination's default namespace was configured as `airbyte_google_ads`, and all connections sharing that destination inherit the same namespace unless overridden per-connection.

## Checking the Database

```bash
# Connect to Render DB
psql $DATABASE_URL

# List all Airbyte tables
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('airbyte_raw', 'airbyte_google_ads')
ORDER BY table_schema, table_name;

# Check row counts
SELECT 'airbyte_raw.orders' as tbl, count(*) FROM airbyte_raw.orders
UNION ALL SELECT 'airbyte_raw.customers', count(*) FROM airbyte_raw.customers
UNION ALL SELECT 'airbyte_google_ads.ads_insights', count(*) FROM airbyte_google_ads.ads_insights;

# Check latest sync timestamps
SELECT max(_airbyte_extracted_at) as latest FROM airbyte_raw.orders;
```

## Tenant Mapping

dbt staging models join to `platform.tenant_airbyte_connections` for tenant isolation. Verify the mapping:

```sql
SELECT source_type, connection_name, status, is_enabled,
       configuration->>'shop_domain' as shop_domain,
       configuration->>'account_id' as account_id,
       configuration->>'customer_id' as customer_id
FROM platform.tenant_airbyte_connections
WHERE status = 'active';
```

If this table is empty, run the `seed_tenant_airbyte_connections.sql` migration.

## Sync Modes for Time Series

For time series reporting, connections MUST use incremental sync modes that preserve history:

| Mode | Behavior | Time Series? |
|---|---|---|
| `incremental_deduped_history` | Appends new data, deduplicates by PK | Yes |
| `incremental_append` | Appends all new data (may have duplicates) | Yes |
| `full_refresh_overwrite` | Drops and recreates table each sync | **No** — destroys history |
| `full_refresh_overwrite_deduped` | Drops and recreates with dedup | **No** — destroys history |

**Google Ads was configured as `full_refresh_overwrite`** — this must be changed to `incremental_deduped_history` via the Airbyte Cloud UI (Connection → Replication → stream settings).

Shopify and Facebook Marketing are already on `incremental_deduped_history`.

## Post-Migration: Full dbt Rebuild

After deploying V1→V2 migration changes, run a one-time full rebuild:

```bash
# On Render shell:
cd /app && bash scripts/dbt_full_rebuild.sh

# Locally:
bash scripts/dbt_full_rebuild.sh
```

This clears stale incremental data from prior V1 runs and rebuilds all models from V2 tables. After the rebuild, the hourly cron (`markinsight-dbt-incremental`) handles ongoing incremental updates.
