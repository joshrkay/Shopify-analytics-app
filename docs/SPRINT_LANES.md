# Sprint Lanes — Parallel Workstream Coordination

> Last updated: 2026-02-18
> Maps backlog items to parallel engineering lanes to minimize blocking dependencies.

---

## Lane Philosophy

Each lane is designed to be independently executable — teams/engineers in different lanes
should not block each other within the same sprint. Cross-lane dependencies are explicitly listed.

---

## Sprint 4 Lanes

### Lane A: Platform Credential Infrastructure
**Owner:** Backend Platform
**Depends on:** Nothing (all infra exists)

| Item | Effort | Notes |
|------|--------|-------|
| S4-1: Meta token refresh | M | Unblocked — uses existing `encrypt_secret` + `ConnectorCredential` |
| S4-2: Google token refresh | M | Same pattern as Meta, can be done in parallel |
| S4-4: Audit async caller migrations | S | Follow-on to this sprint's async changes |

**Deliverable:** Token refresh works end-to-end for Meta + Google. Credentials auto-refresh
on 401 without user re-auth.

---

### Lane B: Notifications
**Owner:** Backend Platform
**Depends on:** Nothing (CLERK_SECRET_KEY available)

| Item | Effort | Notes |
|------|--------|-------|
| S4-3: User email lookup | S | Single Clerk API call, well-understood |

**Deliverable:** Notification emails can be sent to users (currently silently dropped).

---

### Lane C: dbt Attribution (Spec work)
**Owner:** Analytics
**Depends on:** Nothing (session tracking is future work)

| Item | Effort | Notes |
|------|--------|-------|
| S5-4: Session tracking spec | XL | Define the event capture approach |
| Update `attribution/schema.yml` | S | Add entries for `multi_touch_linear` and `time_decay` |

**Deliverable:** Session tracking RFC written, schema.yml updated with new model tests.

---

## Sprint 5 Lanes

### Lane A: Klaviyo/Attentive Pipeline
**Owner:** Data Engineering
**Depends on:** Real API keys from merchant

| Item | Effort | Notes |
|------|--------|-------|
| S5-1: Connect real accounts | S | Use new `api-key/connect` endpoint |
| Validate staging models | M | Airbyte source → staging → canonical |

---

### Lane B: SMS + Email Metrics
**Owner:** Analytics
**Depends on:** Lane A (S5-1)

| Item | Effort | Notes |
|------|--------|-------|
| S5-2: Email engagement metrics | M | Starts once staging events exist |
| S5-3: SMS engagement metrics | M | Parallel to email metrics once events exist |

---

### Lane C: Agency + Template Saving
**Owner:** Fullstack
**Depends on:** Nothing

| Item | Effort | Notes |
|------|--------|-------|
| S6-2: Agency access token via Clerk | M | Independent of pipeline work |
| S6-1: Dashboard template saving | L | Frontend already has the hook call, needs backend |

---

## Dependency Graph

```
S4-1, S4-2 (token refresh)
    └── No deps

S4-3 (email lookup)
    └── No deps

S5-1 (connect Klaviyo/Attentive)
    └── Real API keys (external blocker)
    └── api-key/connect endpoint ✅ (done this sprint)
    └── S5-2, S5-3 depend on S5-1

S6-1 (template saving)
    └── No code deps; needs product spec

S6-2 (agency tokens)
    └── No code deps; needs Clerk org invitations API exploration

SC-1 (audit export job)
    └── Needs DB migration spec first

SC-2 (legal hold)
    └── Blocked on compliance team definition
```

---

## Critical Path to Production Readiness

The critical path for merchant-facing value delivery:

1. **NOW** — `api-key/connect` lets Klaviyo/Attentive users connect ✅
2. **Sprint 4** — Token refresh prevents credential expiry interruptions (S4-1, S4-2)
3. **Sprint 5** — SMS/Email metrics populate dashboards after S5-1 unblocks
4. **Sprint 5** — LTV cohort charts visible for existing Shopify data ✅ (fct_ltv done)
5. **Sprint 6** — Multi-touch attribution visible in dashboard ✅ (models done; needs UI wiring)

---

## Evergreen Non-Sprint Items

These run continuously and are not sprint-bounded:

- **CI Health** — Platform gate tests must pass on every PR
- **Credential Rotation** — Automated alerts when credentials expire (Datadog/Render alerts)
- **dbt Freshness** — 48h error threshold on `dbt_updated_at` columns
- **Stub Audit** — Re-run SPRINT_TRUTH_PASS.md methodology quarterly
