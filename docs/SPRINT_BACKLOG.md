# Sprint Backlog — MarkInsight Engineering

> Last updated: 2026-02-18
> Source of truth for prioritized engineering backlog.
> Derives from SPRINT_TRUTH_PASS.md, product roadmap, and CI gap analysis.

---

## Status Legend

- `READY` — Fully specified, no blockers, can be picked up immediately
- `NEEDS_SPEC` — Rough shape known, needs design/API contract before starting
- `BLOCKED` — Waiting on external dependency (listed in "Blocked by")
- `IN_PROGRESS` — Actively being worked

---

## Sprint 4 — Credential Refresh & Notifications

### S4-1: Meta OAuth Token Refresh
**Priority:** P1 | **Status:** READY | **Effort:** M

- Implement `token_manager._refresh_meta()` using Meta's OAuth token refresh endpoint
- Store new `access_token` back to `ConnectorCredential`
- Trigger on `TokenExpiredError` in Meta executor
- Test: mock Meta refresh endpoint, verify token is updated in DB

**Files:** `backend/src/integrations/token_manager.py`, `backend/src/services/platform_credentials_service.py`

---

### S4-2: Google Ads OAuth Token Refresh
**Priority:** P1 | **Status:** READY | **Effort:** M

- Implement `token_manager._refresh_google()` using Google's token refresh flow
- Uses `refresh_token` + `client_id` + `client_secret` from `GoogleAdsCredentials`
- Store new `access_token` + expiry back to credential record
- Test: mock Google token endpoint

**Files:** `backend/src/integrations/token_manager.py`

---

### S4-3: Notification Email — User Email Lookup
**Priority:** P2 | **Status:** READY | **Effort:** S

- Implement `notification_email_worker._get_user_email(user_id: str) -> Optional[str]`
- Call Clerk Users API: `GET /v1/users/{user_id}` and return `primary_email_address`
- Add `CLERK_SECRET_KEY` to env validation on worker startup
- Test: mock Clerk API response

**Files:** `backend/src/workers/notification_email_worker.py`

---

### S4-4: Action Execution — Credential Validation in Route
**Priority:** P2 | **Status:** NEEDS_SPEC | **Effort:** S

- `PlatformCredentialsService` methods are now async — audit all callers in action routes
- Any route calling `check_credentials_exist()` or `get_executor_for_platform()` must `await` the call
- Add regression test: routes that use credentials should 401/403 gracefully when credentials missing

**Files:** `backend/src/api/routes/actions.py` (if it exists), callers of `PlatformCredentialsService`

---

## Sprint 5 — Analytics Pipeline & SMS/Email Metrics

### S5-1: Klaviyo/Attentive Data Pipeline Validation
**Priority:** P1 | **Status:** BLOCKED | **Blocked by:** Real Klaviyo/Attentive API keys in test env

- Connect a real Klaviyo account using new `api-key/connect` endpoint
- Verify Airbyte syncs events to warehouse
- Validate staging models pick up the data

**Files:** `analytics/models/staging/stg_klaviyo_events.sql`, etc.

---

### S5-2: SMCE Email Engagement Metrics
**Priority:** P2 | **Status:** BLOCKED | **Blocked by:** S5-1

- Build `fct_email_engagement.sql` in metrics layer
- Metrics: open rate, click rate, revenue per email, unsubscribe rate
- Requires: `stg_klaviyo_events` or `stg_shopify_email_events` to exist

---

### S5-3: SMCE SMS Engagement Metrics
**Priority:** P2 | **Status:** BLOCKED | **Blocked by:** S5-1

- Build `fct_sms_engagement.sql` in metrics layer
- Metrics: delivery rate, click rate, revenue per SMS, opt-out rate
- Requires: `stg_attentive_events` or `stg_postscript_events` to exist

---

### S5-4: Attribution — Session Tracking Foundation
**Priority:** P3 | **Status:** NEEDS_SPEC | **Effort:** XL

- Current `multi_touch_linear` and `time_decay` models approximate multi-touch using
  campaign activity windows — not true session-level click data
- True multi-touch requires: session tracking pixel or UTM enrichment at the session level
- Define the session capture approach (Shopify storefront JS, server-side, or Airbyte event stream)

---

## Sprint 6 — Template Saving & Agency Access

### S6-1: Dashboard Template Saving (Epic 6)
**Priority:** P3 | **Status:** NEEDS_SPEC | **Effort:** L

- Backend: `POST /api/dashboards/templates` to save current layout as a reusable template
- Backend: `GET /api/dashboards/templates` to list saved templates
- Frontend: Wire `WizardFlow.handleSaveAsTemplate()` to call the save endpoint
- Currently silently no-ops (alert removed in Sprint 3)

---

### S6-2: Agency Access Token via Clerk
**Priority:** P2 | **Status:** NEEDS_SPEC | **Effort:** M

- Replace local JWT approach in `agency._generate_agency_access_token()` with Clerk org invitations
- Use Clerk `POST /v1/organizations/{org_id}/invitations` to generate cross-org access
- Tokens should be time-limited and scoped to read-only access

---

## Compliance / Audit

### SC-1: Audit Export Job — Job Queue Table
**Priority:** P2 | **Status:** NEEDS_SPEC | **Effort:** M

- `audit_export_job._poll_and_process()` is currently a no-op (`pass`)
- Needs: `audit_export_jobs` DB table with status tracking
- Needs: worker polling loop
- Migration file required before implementation

### SC-2: Legal Hold Support
**Priority:** P3 | **Status:** BLOCKED | **Blocked by:** Legal hold schema design

- `audit_retention_job` intentionally skips records with `legal_hold=True`
- `legal_hold` column does not exist on any audit table yet
- Needs: compliance team to define legal hold scope and retention rules

---

## Infrastructure / Billing

### SI-1: Paid Plan Checkout — Real Shopify Store
**Priority:** P1 | **Status:** BLOCKED | **Blocked by:** Production Shopify store

- Growth and Pro plan checkout requires a real Shopify store with a valid `access_token`
- Cannot test or complete this without a production merchant environment
- Unblocked when: real merchant onboards and connects a Shopify store

---

## Completed This Sprint (Reference)

See `SPRINT_TRUTH_PASS.md` for the full audit. Summary:
- `platform_credentials_service.py` — 6 stubs implemented
- `sources.py` — API key connect route added
- `useSourceConnection.ts` — testConnection wired to real API
- `WizardFlow.tsx` — alert() removed
- `fct_ltv.sql`, `multi_touch_linear.sql`, `time_decay.sql` — dbt models created
