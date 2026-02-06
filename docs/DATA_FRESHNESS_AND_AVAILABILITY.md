# Data Freshness & Availability System

Story 3.3 — End-to-end documentation for operators and engineers.

## Overview

The data freshness and availability system ensures that analytics dashboards, AI features, and embedded Superset reports reflect recent data. When upstream data sources stop syncing or fall behind SLA thresholds, the system automatically transitions the affected source through a three-state machine — **FRESH → STALE → UNAVAILABLE** — and takes protective action at each level: showing merchant warnings, blocking unreliable features, and paging operators.

## Architecture

```
 Airbyte sync ─┐
               ├─► TenantAirbyteConnection.last_sync_at
 dbt run ──────┘           │
                           ▼
              DataAvailabilityService._compute_state()
                           │
            ┌──────────────┼──────────────────┐
            ▼              ▼                  ▼
         FRESH          STALE           UNAVAILABLE
      (sync_ok)     (sla_exceeded)   (grace_window_exceeded
                                      / sync_failed
                                      / never_synced)
            │              │                  │
            ▼              ▼                  ▼
     No banner       Warning banner     Critical banner
     All features    AI degraded        Dashboard blocked
     enabled         Superset allowed   Superset paused
                                        PagerDuty alert
```

## Freshness Calculation

Freshness is computed in `DataAvailabilityService.get_data_availability()` (`backend/src/services/data_availability_service.py`).

### Signal source

The primary signal is `TenantAirbyteConnection.last_sync_at` — the most recent successful sync timestamp for each connection. When multiple Airbyte connections map to the same SLA source (e.g., both `shopify` and `shopify_email` map to `shopify_orders`), the most recent timestamp wins.

### Steps

1. **Load SLA thresholds** for the `(source, billing_tier)` pair from `config/data_freshness_sla.yml`.
2. **Compute elapsed time**: `minutes_since_sync = (now - last_sync_at) / 60`.
3. **Apply `_compute_state()`** — a pure function with no side effects:

| Condition | State | Reason |
|---|---|---|
| `last_sync_at` is NULL | UNAVAILABLE | `never_synced` |
| Last sync failed AND elapsed >= warn threshold | UNAVAILABLE | `sync_failed` |
| Elapsed >= error threshold | UNAVAILABLE | `grace_window_exceeded` |
| Elapsed >= warn threshold | STALE | `sla_exceeded` |
| Otherwise | FRESH | `sync_ok` |

4. **Persist** result to the `data_availability` table (upsert per `(tenant_id, source_type)`).
5. **Emit audit event** if state changed (see Audit Events below).

### Connection-to-SLA mapping

Not every Airbyte `source_type` has a 1:1 mapping to an SLA key. The mapping is defined in `CONNECTION_SOURCE_TO_SLA_KEY`:

| Connection source_type | SLA key |
|---|---|
| `shopify` | `shopify_orders` |
| `facebook`, `meta` | `facebook_ads` |
| `google` | `google_ads` |
| `tiktok` | `tiktok_ads` |
| `snapchat` | `snapchat_ads` |
| `klaviyo`, `shopify_email` | `email` |
| `attentive`, `postscript`, `smsbump` | `sms` |

## SLA Thresholds

Defined in `config/data_freshness_sla.yml`. All values in minutes.

| Source | Free (warn/error) | Growth (warn/error) | Enterprise (warn/error) |
|---|---|---|---|
| shopify_orders | 24h / 48h | 6h / 12h | 1h / 2h |
| facebook_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| google_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| tiktok_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| snapchat_ads | 24h / 48h | 6h / 12h | 1h / 2h |
| email | 24h / 48h | 12h / 24h | 6h / 12h |
| sms | 24h / 48h | 12h / 24h | 6h / 12h |

**Fallback**: If a source or tier is missing, falls back to the `free` tier, then to hardcoded defaults (1440 / 2880 minutes).

**dbt access**: The same thresholds are mirrored in `dbt_project.yml` as `var('freshness_sla')` because dbt source YAML parsing does not support custom macros. The `get_freshness_threshold()` macro wraps `var()` for use in dbt tests and models.

## States Explained

### FRESH (`sync_ok`)
Data is within the warn SLA threshold. All platform features are enabled. No merchant-facing indicators are shown.

### STALE (`sla_exceeded`)
Time since last sync exceeds the warn threshold but is within the error threshold. This is a degraded state:

- **Merchant sees**: A yellow warning banner — "Data Update in Progress" — with affected source names.
- **AI features**: May be degraded (stale data disclaimer injected).
- **Superset**: Continues to serve existing dashboards.
- **Operator alert**: After 2 hours in STALE, a Slack alert fires to `#analytics-ops`.

### UNAVAILABLE
Data is beyond the error threshold, or the sync has failed/never occurred. Three reason codes:

| Reason | Trigger |
|---|---|
| `grace_window_exceeded` | Elapsed time >= error threshold |
| `sync_failed` | Last sync status is `failed` AND elapsed >= warn threshold |
| `never_synced` | No `last_sync_at` recorded at all |

- **Merchant sees**: A red critical banner — "Data Temporarily Unavailable" — with retry action button.
- **AI features**: Blocked (returns error).
- **Superset**: Query execution paused for affected sources.
- **Operator alert**: Immediate PagerDuty page + Slack notification.

## Recovery

A source **recovers** (transitions to FRESH) when:

1. Airbyte completes a successful sync, updating `last_sync_at`.
2. The next evaluation by `DataAvailabilityService` computes `minutes_since_sync < warn_threshold`.
3. State transitions to FRESH with reason `sync_ok`.
4. A `data.freshness.recovered` audit event is emitted.

Recovery is **automatic** — no manual intervention is required once the sync succeeds. The merchant-facing banner disappears, and all features are re-enabled.

## Merchant-Facing Indicators

### Banner (`DataFreshnessBanner.tsx`)
Rendered when state is `stale` or `unavailable`. Uses Shopify Polaris `<Banner>` component.

| State | Tone | Title | Actions |
|---|---|---|---|
| fresh | (hidden) | — | — |
| stale | warning | "Data Update in Progress" | Dismiss |
| unavailable | critical | "Data Temporarily Unavailable" | Retry, Dismiss |

When `affectedSources` are provided, they are listed as a comma-separated string inside the banner body.

### Badge (`DataFreshnessBadge.tsx`)
Small inline status indicator using Polaris `<Badge>`:

| State | Badge tone | Label |
|---|---|---|
| fresh | success | "Up to date" |
| stale | attention | "Data delayed" |
| unavailable | critical | "Data temporarily unavailable" |

### Copy functions (`freshness_copy.ts`)
All merchant-visible text is centralized in `frontend/src/utils/freshness_copy.ts`. Functions:

- `getFreshnessLabel(state)` — Badge label
- `getFreshnessBannerTitle(state)` — Banner title
- `getFreshnessBannerMessage(state, reason?)` — Banner body (reason-aware)
- `getFreshnessTooltip(state, reason?)` — Hover tooltip
- `getFreshnessBadgeTone(state)` — Polaris tone for Badge
- `getFreshnessBannerTone(state)` — Polaris tone for Banner

No copy function ever exposes internal timestamps, SLA values, or reason codes to merchants.

## Feature Blocking

### API-level guards
Decorator-based middleware in `backend/src/entitlements/middleware.py` provides feature-gating:

- `@require_entitlement(feature_key)` — General feature guard
- `@require_billing_state(allowed_states)` — Billing state guard

The data availability state is used alongside these entitlements to determine feature access:

- **FRESH**: All features allowed.
- **STALE**: AI features may inject a staleness disclaimer. Superset dashboards remain accessible.
- **UNAVAILABLE**: API endpoints return HTTP 503 with a structured error body. Superset queries for affected sources are paused.

### Superset integration
The Superset availability hook checks `DataAvailability.state` before executing embedded queries. When state is `unavailable`, queries for that source are blocked and the user sees a "data unavailable" message instead of stale charts.

### AI feature gating
AI-powered features check availability state before generating insights. In `stale` state, responses include a disclaimer. In `unavailable` state, the feature returns an error rather than producing misleading analysis.

## Audit Events

Three structured audit events are emitted on state transitions (`backend/src/platform/audit.py`, `audit_events.py`):

| Event | AuditAction | Severity | Trigger |
|---|---|---|---|
| `data.freshness.stale` | `DATA_FRESHNESS_STALE` | medium | FRESH → STALE |
| `data.freshness.unavailable` | `DATA_FRESHNESS_UNAVAILABLE` | high | ANY → UNAVAILABLE |
| `data.freshness.recovered` | `DATA_FRESHNESS_RECOVERED` | low | ANY → FRESH |

### Event metadata fields

All three events include:

| Field | Description |
|---|---|
| `tenant_id` | Affected tenant |
| `source` | SLA source key (e.g., `shopify_orders`) |
| `previous_state` | State before transition (`unknown` if first evaluation) |
| `new_state` | State after transition |
| `detected_at` | ISO 8601 timestamp |
| `root_cause` | Reason code from state machine |

Events are written to the append-only `AuditLog` table with PII redaction. The `data.freshness.unavailable` event carries `compliance_tags: ["SOC2"]`.

### Failure isolation
Audit emission is wrapped in a try/except. If the audit write fails (e.g., DB connection lost), the error is logged but **never propagates** to the state machine caller.

## Operator Alerting

### Alert rules (`config/alert_thresholds.yml`)

| Rule | Trigger | Delay | Channels |
|---|---|---|---|
| `stale_extended` | Source in STALE | 2 hours | Slack `#analytics-ops` |
| `unavailable_immediate` | Source in UNAVAILABLE | Immediate | Slack + PagerDuty |

### Deduplication
Alerts for the same `(source_type, state)` are deduplicated with a 30-minute cooldown window.

### Multi-tenant escalation
If >= 3 tenants are affected by the same source violation, severity is promoted to `critical` and PagerDuty is added to the channel list.

### Likely cause inference
The alert system infers the probable root cause from the reason code:

| Reason | Likely cause |
|---|---|
| `sync_failed`, `sla_exceeded`, `grace_window_exceeded`, `never_synced` | Ingestion |
| `dbt_failed` | dbt transformation |

### Environment variables

| Variable | Purpose |
|---|---|
| `SLACK_FRESHNESS_WEBHOOK_URL` | Slack incoming webhook for `#analytics-ops` |
| `PAGERDUTY_FRESHNESS_ROUTING_KEY` | PagerDuty Events API v2 routing key |

## dbt Integration

### Source freshness
dbt source freshness checks are defined in `analytics/models/raw_sources/sources.yml` using inline `var('freshness_sla')` lookups. These run during `dbt source freshness` and validate that raw tables have recent data.

### Generic test
`analytics/tests/generic/test_freshness.sql` provides a reusable freshness test for staging models. It accepts `source_name` (to look up SLA thresholds via `get_freshness_threshold()` macro), or explicit `warn_after_hours` / `error_after_hours`. All freshness tests are configured with `severity: warn` to avoid blocking CI on stale test databases.

### Macro
`analytics/macros/get_freshness_threshold.sql` wraps `var('freshness_sla')` for ergonomic threshold lookups in dbt models and tests. It is **not** available during source YAML parsing (dbt 1.11+ limitation) — sources must use inline `var()` instead.

## Key Files

| File | Purpose |
|---|---|
| `config/data_freshness_sla.yml` | SLA thresholds (single source of truth) |
| `config/alert_thresholds.yml` | Alert rules, channels, escalation |
| `backend/src/services/data_availability_service.py` | State machine, SLA evaluation |
| `backend/src/models/data_availability.py` | `DataAvailability` model, state/reason enums |
| `backend/src/monitoring/freshness_alerts.py` | Alert manager with dedup + dispatch |
| `backend/src/platform/audit.py` | Audit event definitions |
| `backend/src/platform/audit_events.py` | Event registry, categories, severity |
| `frontend/src/components/DataFreshnessBanner.tsx` | Merchant-facing banner |
| `frontend/src/components/DataFreshnessBadge.tsx` | Inline status badge |
| `frontend/src/utils/freshness_copy.ts` | All merchant-visible text |
| `analytics/macros/get_freshness_threshold.sql` | dbt threshold lookup macro |
| `analytics/tests/generic/test_freshness.sql` | dbt generic freshness test |
| `analytics/models/raw_sources/sources.yml` | dbt source freshness definitions |
| `analytics/models/staging/schema.yml` | Staging model freshness tests |
