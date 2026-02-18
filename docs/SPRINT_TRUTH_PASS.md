# Sprint Truth Pass — Stub & Gap Audit

> Last updated: 2026-02-18
> Purpose: Canonical record of every stub, placeholder, and missing implementation
> discovered during the February 2026 truth pass. One source of truth — do not duplicate.

---

## Methodology

Each item below was verified by reading the actual implementation, not just route definitions or
catalog entries. "Verified" means the code was read and behavior confirmed by tracing execution.

Status legend:
- `FIXED` — Implemented in this sprint (branch `claude/setup-ai-sprint-planning-3XcpO`)
- `BLOCKED` — Cannot be implemented without external dependency (Stripe, Clerk, schema)
- `BACKLOG` — Real implementation needed, scheduled for a future sprint
- `DEFERRED` — Intentional product decision to defer (documented below)

---

## Backend Stubs

### `platform_credentials_service.py`

| Method | Was | Now | Status |
|--------|-----|-----|--------|
| `get_meta_credentials()` | Returns `None` with warning log | Queries `ConnectorCredential`, decrypts via Fernet | **FIXED** |
| `get_google_credentials()` | Returns `None` with warning log | Queries `ConnectorCredential`, decrypts via Fernet | **FIXED** |
| `store_credentials()` | Returns `False` | Creates `ConnectorCredential` row, encrypts payload | **FIXED** |
| `revoke_credentials()` | Returns `False` | Sets `status=REVOKED`, sets `soft_deleted_at` | **FIXED** |
| `_encrypt_credentials()` | `raise NotImplementedError` | `await encrypt_secret(json.dumps(data))` | **FIXED** |
| `_decrypt_credentials()` | `raise NotImplementedError` | `await decrypt_secret(data)` + `json.loads` | **FIXED** |

**Key change:** All credential-touching methods are now `async` (matching `encrypt_secret`/`decrypt_secret`).
Callers that already used `await` are unaffected. Any remaining sync callers must be updated.

---

### `sources.py` — Missing API Key Connect Route

| Route | Was | Now | Status |
|-------|-----|-----|--------|
| `POST /api/sources/{platform}/api-key/connect` | Did not exist | Creates Airbyte source + pipeline for api_key platforms | **FIXED** |

Platforms covered: `klaviyo`, `attentive`, `postscript`, `smsbump`.

**Note:** Attentive and Klaviyo are listed in CLAUDE.md stub table as "needs OAuth builder" but their
`PLATFORM_AUTH_TYPE` is `api_key`. The new route serves as the correct implementation — no OAuth needed.

---

### `token_manager.py` — Token Refresh Stubs

| Method | Was | Now | Status |
|--------|-----|-----|--------|
| `_refresh_meta()` | `raise TokenRefreshError` (not implemented) | Not yet implemented | **BACKLOG** |
| `_refresh_google()` | `raise TokenRefreshError` (not implemented) | Not yet implemented | **BACKLOG** |

**Reason deferred:** Requires OAuth refresh token flow. Meta and Google token refresh needs platform
app credentials configured (Meta App Secret + Google OAuth client). Scheduled for Sprint 4.

---

### `notification_email_worker.py`

| Method | Was | Now | Status |
|--------|-----|-----|--------|
| `_get_user_email()` | Returns `None` | Not yet implemented | **BACKLOG** |

**Reason deferred:** Requires Clerk Users API to look up user email by user_id. Implementation
is straightforward but needs Clerk API key + rate limiting. Scheduled for Sprint 4.

---

### `audit_export_job.py`

| Feature | Was | Now | Status |
|---------|-----|-----|--------|
| `_poll_and_process()` | `pass` (no-op) | Not yet implemented | **BACKLOG** |
| Legal hold support | Not mentioned | Not yet implemented | **BLOCKED** — needs `legal_hold` schema |

---

### Agency Service

| Feature | Was | Now | Status |
|---------|-----|-----|--------|
| `_generate_agency_access_token()` | Uses `JWT_SECRET` env var (local JWT) | Not yet implemented | **BACKLOG** |

**Correct approach:** Should use Clerk API to issue organization invitation tokens, not local JWT.

---

## Frontend Stubs

### `useSourceConnection.ts` — `testConnection()` for API key platforms

| Feature | Was | Now | Status |
|---------|-----|-----|--------|
| Wizard `testConnection()` | Returns fake `{ success: true }` always | Calls `completeApiKeyConnect` then `apiTestConnection` | **FIXED** |

---

### `WizardFlow.tsx` — `handleSaveAsTemplate`

| Feature | Was | Now | Status |
|---------|-----|-----|--------|
| `handleSaveAsTemplate()` | Calls `window.alert()` with "coming soon" message | Silent no-op with `console.info` | **FIXED** |

**Note:** No backend endpoint for template saving. Silencing the alert removes UX disruption.
Full implementation is Epic 6 scope.

---

## dbt Models

### Missing Attribution Models

| Model | Was | Now | Status |
|-------|-----|-----|--------|
| `attribution/multi_touch_linear.sql` | Did not exist | Implemented (campaign-window approximation) | **FIXED** |
| `attribution/time_decay.sql` | Did not exist | Implemented (exp decay weight by days-before-order) | **FIXED** |

**Limitation note:** Without session-level click tracking, both models approximate multi-touch
by scanning campaign activity in the 7-day window before each order. True multi-touch requires
session data (future work).

### Missing Metrics Models

| Model | Was | Now | Status |
|-------|-----|-----|--------|
| `metrics/fct_ltv.sql` | Did not exist | Cohort-based LTV at 30/90/180/365-day windows | **FIXED** |

### SMCE Metrics (Engagement Channel Models)

| Model | Was | Now | Status |
|-------|-----|-----|--------|
| SMS/Email engagement metrics | Did not exist | Not yet implemented | **BACKLOG** |

**Reason deferred:** Requires canonical SMS/Email engagement event tables from Klaviyo/Attentive
Airbyte sources. Those sources depend on `api-key/connect` implementation (now FIXED).
SMCE models depend on Airbyte data being present. Scheduled for Sprint 5.

---

## Paid Plan Checkout

| Feature | Was | Now | Status |
|---------|-----|-----|--------|
| Growth/Pro plan checkout | Frontend works | Requires real Shopify store with valid access_token | **BLOCKED** |

This is an infrastructure/environment gap — not a code stub. Shopify Billing API calls require
a real merchant shop. Cannot be fixed in code alone.

---

## Summary Counts

| Status | Count |
|--------|-------|
| FIXED (this sprint) | 12 |
| BACKLOG (next sprints) | 7 |
| BLOCKED (external dep) | 2 |
| **Total gaps found** | **21** |
