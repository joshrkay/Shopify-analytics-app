# Incident Runbook: Data Freshness & Availability

On-call guide for responding to data freshness SLA violations.

See [DATA_FRESHNESS_AND_AVAILABILITY.md](./DATA_FRESHNESS_AND_AVAILABILITY.md) for full system architecture.

---

## Quick Reference

| Alert | Severity | Channel | Response Time |
|---|---|---|---|
| Source STALE > 2 hours | Warning | Slack `#analytics-ops` | Best effort (business hours) |
| Source UNAVAILABLE | Critical | Slack + PagerDuty | Immediate |
| Multi-tenant (>= 3) | Critical (escalated) | Slack + PagerDuty | Immediate |

---

## Triage Flowchart

```
Alert received
    │
    ├─ State: STALE
    │   └─ Is this a single tenant or many?
    │       ├─ Single tenant → Check that tenant's Airbyte connection (Step 1)
    │       └─ Multiple tenants → Likely a platform-wide ingestion issue (Step 2)
    │
    └─ State: UNAVAILABLE
        └─ What is the reason code?
            ├─ never_synced → New tenant, connection not configured (Step 3)
            ├─ sync_failed → Airbyte sync error (Step 4)
            └─ grace_window_exceeded → Extended outage (Step 5)
```

---

## Step 1: Single-Tenant STALE

**Symptoms**: One tenant's source has been STALE for > 2 hours. Warning-level Slack alert.

**Diagnosis**:
1. Query the `data_availability` table for the affected tenant and source:
   ```sql
   SELECT source_type, state, reason, minutes_since_sync,
          last_sync_at, last_sync_status, warn_threshold_minutes,
          error_threshold_minutes, billing_tier
   FROM data_availability
   WHERE tenant_id = '<tenant_id>' AND source_type = '<source>';
   ```
2. Check the Airbyte connection status:
   ```sql
   SELECT source_type, last_sync_at, last_sync_status, is_enabled, status
   FROM tenant_airbyte_connections
   WHERE tenant_id = '<tenant_id>'
     AND source_type ILIKE '%<source_prefix>%';
   ```
3. Review Airbyte job logs for the connection in the Airbyte UI or API.

**Resolution**:
- If the connection is disabled or deleted: Contact the merchant or re-enable.
- If the Airbyte job is queued/running: Wait for completion — the system recovers automatically.
- If the Airbyte job failed: See Step 4.
- If the source API is rate-limited or down: Wait for upstream recovery. Consider extending the SLA threshold temporarily via a config change.

**Recovery verification**: Once `last_sync_at` updates, the next `DataAvailabilityService` evaluation will transition the state back to FRESH automatically. Confirm by re-querying `data_availability`.

---

## Step 2: Multi-Tenant STALE / UNAVAILABLE

**Symptoms**: Alert escalated to critical because >= 3 tenants are affected for the same source. This indicates a platform-level issue rather than a tenant-specific problem.

**Diagnosis**:
1. Count affected tenants:
   ```sql
   SELECT source_type, state, reason, COUNT(DISTINCT tenant_id) as affected_tenants,
          MIN(last_sync_at) as oldest_sync, MAX(last_sync_at) as newest_sync
   FROM data_availability
   WHERE source_type = '<source>' AND state != 'fresh'
   GROUP BY source_type, state, reason;
   ```
2. Check Airbyte instance health — is the Airbyte server running? Are workers healthy?
3. Check upstream API status pages (Shopify status, Meta Business API status, Google Ads API status, etc.)
4. Check for recent infrastructure changes (deployments, config changes, credential rotations).

**Resolution**:
- **Airbyte server down**: Restart the Airbyte server. All pending syncs will resume.
- **Upstream API outage**: No action needed — syncs will recover once the API is back. Post a status update in `#analytics-ops` with ETA if available.
- **Credential rotation**: Check if API keys or OAuth tokens expired. Rotate credentials in Airbyte.
- **Infrastructure issue**: Investigate networking, disk space, memory on Airbyte workers.

---

## Step 3: UNAVAILABLE — `never_synced`

**Symptoms**: A source has never had a successful sync. This usually happens with new tenants or newly configured connections.

**Diagnosis**:
1. Verify the connection exists and is enabled:
   ```sql
   SELECT * FROM tenant_airbyte_connections
   WHERE tenant_id = '<tenant_id>';
   ```
2. Check if the Airbyte connection was created but never triggered.

**Resolution**:
- Trigger the initial sync from the Airbyte UI or API.
- If the connection doesn't exist, the tenant's onboarding may be incomplete — check with the customer success team.
- Once the first sync completes, state will transition directly to FRESH.

---

## Step 4: UNAVAILABLE — `sync_failed`

**Symptoms**: The last Airbyte sync failed AND the data is older than the warn threshold. PagerDuty alert likely fired.

**Diagnosis**:
1. Get the failed sync details:
   ```sql
   SELECT source_type, last_sync_at, last_sync_status,
          airbyte_connection_id
   FROM tenant_airbyte_connections
   WHERE tenant_id = '<tenant_id>'
     AND last_sync_status = 'failed';
   ```
2. Check Airbyte job logs for the specific error:
   - Authentication errors → credential issue
   - Rate limit errors → back off and retry
   - Schema change errors → source schema evolved, update Airbyte catalog
   - Timeout errors → increase sync timeout or reduce sync scope

**Resolution**:
- Fix the root cause (credentials, schema, rate limits).
- Manually trigger a retry from Airbyte.
- The system recovers automatically once the next sync succeeds.

**Important**: Do NOT manually set the state to FRESH. State is always computed from current sync metadata. Manually overriding it will be corrected on the next evaluation cycle.

---

## Step 5: UNAVAILABLE — `grace_window_exceeded`

**Symptoms**: The source has been STALE for so long that it exceeded the error threshold (grace window). This is the most severe ingestion failure mode.

**Diagnosis**:
1. Determine how far behind the source is:
   ```sql
   SELECT source_type, minutes_since_sync,
          error_threshold_minutes,
          minutes_since_sync - error_threshold_minutes as minutes_overdue,
          last_sync_at, billing_tier
   FROM data_availability
   WHERE tenant_id = '<tenant_id>' AND source_type = '<source>';
   ```
2. Follow the same investigation steps as Step 2/Step 4 depending on whether the issue is single-tenant or multi-tenant.

**Resolution**: Same as Step 4. The grace window exceeded state is a severity escalation of the same underlying problem — data isn't arriving.

---

## When Merchants Are Blocked

The system progressively restricts features as data quality degrades:

| State | Merchant experience | Features affected |
|---|---|---|
| FRESH | Normal operation | None |
| STALE | Yellow warning banner: "Data Update in Progress" | AI features show staleness disclaimer |
| UNAVAILABLE | Red critical banner: "Data Temporarily Unavailable" with Retry button | Dashboard queries blocked, AI features disabled, Superset queries paused |

**Merchant cannot self-resolve**: Merchants have no ability to fix ingestion issues. The Retry button triggers a re-evaluation (not a sync). Operator intervention is required for all `sync_failed` and persistent STALE/UNAVAILABLE states.

---

## When Human Intervention Is Required

### Always requires human action:
- **`sync_failed`**: An Airbyte sync error needs diagnosis and a fix (credentials, schema, rate limits).
- **Multi-tenant outage**: Indicates a platform-level problem (Airbyte server, upstream API, infrastructure).
- **`never_synced` for existing tenants**: Onboarding failure — connection was never configured or triggered.

### May self-resolve:
- **Transient `sla_exceeded`**: If the Airbyte scheduler is just behind, the next scheduled sync will fix it. Monitor but don't act immediately — the 2-hour STALE delay before alerting accounts for this.
- **`grace_window_exceeded` due to upstream outage**: If a source API is temporarily down, syncs will resume when it comes back. Monitor the upstream status page.

### Never requires human action:
- **Recovery (STALE/UNAVAILABLE → FRESH)**: Fully automatic once a sync succeeds.
- **Audit event emission**: Automatic on every state transition. Failures are logged but never propagate.
- **Banner display/removal**: Driven by state — appears automatically when state degrades, disappears when state recovers.

---

## Alert Deduplication

Alerts are deduplicated by `(source_type, state)` with a **30-minute cooldown**. This means:

- You will NOT receive duplicate alerts for the same source in the same state within 30 minutes.
- If a source oscillates (STALE → FRESH → STALE), each new transition to STALE will alert (because the cooldown resets when the source recovers).
- The cooldown is in-memory (resets on service restart). After a deploy, you may see a burst of re-alerts.

---

## Escalation Path

```
1. Slack #analytics-ops (warning)
   │
   ├─ 2 hours in STALE with no resolution
   │   └─ Investigate Airbyte connection health
   │
   ├─ UNAVAILABLE transitions
   │   └─ PagerDuty page (critical) — immediate
   │
   └─ >= 3 tenants affected
       └─ Severity promoted to critical, PagerDuty added
```

---

## Environment Variables

| Variable | Required for | Default |
|---|---|---|
| `SLACK_FRESHNESS_WEBHOOK_URL` | Slack alerts | None (alerts skipped if unset) |
| `PAGERDUTY_FRESHNESS_ROUTING_KEY` | PagerDuty pages | None (pages skipped if unset) |

If either variable is unset, alerts to that channel are silently skipped with a warning log. The system does not crash.

---

## SLA Threshold Quick Reference

| Source | Free warn/error | Growth warn/error | Enterprise warn/error |
|---|---|---|---|
| shopify_orders | 24h / 48h | 6h / 12h | 1h / 2h |
| facebook_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| google_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| tiktok_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| snapchat_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| email | 24h / 48h | 12h / 24h | 6h / 12h |
| sms | 24h / 48h | 12h / 24h | 6h / 12h |

Source of truth: `config/data_freshness_sla.yml`

---

## Useful Queries

### All sources currently not FRESH
```sql
SELECT tenant_id, source_type, state, reason,
       minutes_since_sync, last_sync_at, billing_tier,
       state_changed_at
FROM data_availability
WHERE state != 'fresh'
ORDER BY state DESC, minutes_since_sync DESC;
```

### Sources that have been STALE longest
```sql
SELECT source_type, tenant_id, minutes_since_sync,
       warn_threshold_minutes,
       minutes_since_sync - warn_threshold_minutes as minutes_over_sla
FROM data_availability
WHERE state = 'stale'
ORDER BY minutes_over_sla DESC
LIMIT 20;
```

### Recent audit trail for a source
```sql
SELECT action, tenant_id, resource_id, metadata, created_at
FROM audit_log
WHERE action LIKE 'data.freshness.%'
  AND resource_id = '<source_type>'
ORDER BY created_at DESC
LIMIT 50;
```

### Tenants affected by a specific source outage
```sql
SELECT tenant_id, state, reason, minutes_since_sync, last_sync_at
FROM data_availability
WHERE source_type = '<source_type>' AND state = 'unavailable';
```
