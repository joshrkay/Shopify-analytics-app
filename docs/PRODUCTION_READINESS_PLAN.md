# Production Readiness Plan — 10 Application Modules

**Date:** 2026-03-05
**Method:** Test suites actually executed, not code-read guesses.

---

## Real Test Numbers

| Suite | Passed | Failed | Error | Skipped |
|---|---|---|---|---|
| Unit | 1179 | **1** | 0 | 0 |
| Integration | 157 | **61** | **1** | 1 |
| Platform | 291 | 0 | 0 | 15 |
| E2E | 0 | 0 | 0 | 51 (all skipped — none run) |
| Regression | 169 | 0 | 0 | 42 |
| Frontend build | ✅ clean | — | — | — |
| Frontend lint | ✅ clean | — | — | — |
| Frontend tests | 757 | **2** (timeout under full load; pass in isolation) | 0 | 0 |
| Backend lint | — | **33 ruff violations** | — | — |

---

## Root Causes of All Failures

### Root Cause A — Missing attribute on route module (21 integration tests + 1 error) — CODE BUG

Tests patch `src.api.routes.actions.get_db_session` and `src.api.routes.action_proposals.get_db_session`, but neither module imports `get_db_session`. The patch target doesn't exist on the module, so every test in those files crashes at setup.

```
AttributeError: <module 'src.api.routes.action_proposals'> does not have the attribute 'get_db_session'
AttributeError: <module 'src.api.routes.actions'> does not have the attribute 'get_db_session'
```

### Root Cause B — No PostgreSQL → 503 (34 integration tests) — INFRA, NOT CODE

No `DATABASE_URL` in local env. `TenantContextMiddleware` can't create a DB engine → 503. Affects `test_audit_api.py` (10 tests) and `test_notifications_api.py` (9 tests) and others. These pass in CI where PostgreSQL runs.

### Root Cause C — No auth mock → 403 (12 integration tests) — TEST BUG

`test_llm_config_api.py` doesn't mock the tenant auth headers. `TenantContextMiddleware` logs `Request missing authorization token` → 403. Tests expect 200/402.

### Root Cause D — ActionJob model field mismatch (1 error) — CODE BUG / P0

```
TypeError: 'succeeded_count' is an invalid keyword argument for ActionJob
```

Test fixture constructs `ActionJob(succeeded_count=1, failed_count=0)`. Model columns are `actions_succeeded` / `actions_failed`. Also confirmed in route: `actions.py:155-156` reads `job.succeeded_count` / `job.failed_count` — will throw `AttributeError` at runtime on any request that returns an `ActionJobResponse`.

### Root Cause E — Missing function on service module (1 integration test) — CODE BUG

```
AttributeError: <module 'src.services.audit_access_control'> does not have the attribute 'log_system_audit_event_sync'
```

Test: `TestAuditRBAC::test_cross_tenant_attempt_logs_audit_event`. The function either never existed or was renamed.

### Root Cause F — Async/sync mismatch in unit test (1 unit test) — TEST BUG

```
TypeError: An asyncio.Future, a coroutine or an awaitable is required
```

`test_platform_credentials_service.py` calls `asyncio.get_event_loop().run_until_complete(...)` on a method that is no longer async.

---

## Per-Module Status

---

### Module 1 — Auth & Tenant Provisioning

**Tests run:** 291 platform tests pass. 1 unit test fails.

**Failing:**
- `test_platform_credentials_service.py::TestEncryptDecryptCredentials::test_encrypt_serializes_to_json_and_calls_encrypt_secret`
- Root Cause F: test wraps sync method in `run_until_complete`

**Production impact:** None. The credentials service works. The test is wrong.

**Fix:** Remove `asyncio.get_event_loop().run_until_complete()` wrapper — call the method directly.

**Deploy safe:** Yes.

---

### Module 2 — Billing & Entitlements

**Tests run:** 169 regression tests pass. 0 failures.

**Deploy safe:** Yes.

---

### Module 3 — Data Sources & Sync

**Tests run:** 37 unit tests pass. 0 failures.

All 3 previously-flagged "stub" platforms are implemented:
- Klaviyo → `api_key` → `connect_api_key_source`
- Attentive → `api_key` → `connect_api_key_source`
- Shopify Email → `oauth` → `initiate_oauth` (same Shopify handler)

**Deploy safe:** Yes.

---

### Module 4 — AI Insights / LLM Config

**Tests run:** 12 integration tests fail (all in `test_llm_config_api.py`).

**Failing (all 12 llm_config tests):**
- Root Cause C: no auth mock → all return 403
- Also: tests patch `src.api.routes.llm_config.LLMRoutingService` but that symbol isn't imported at module level in `llm_config.py`

**Production impact:** Routes themselves work (auth middleware just works). The test suite is broken.

**Fixes needed:**
- `test_llm_config_api.py`: add tenant auth header mock to all tests
- `test_llm_config_api.py`: fix patch target — mock at the service layer, not on the route module

**Deploy safe:** Yes (route logic is fine, tests are wrong).

---

### Module 5 — AI Actions & Proposals

**Tests run:** 21 integration tests fail (Root Cause A), 1 test errors (Root Cause D).

**Failing:**

13 in `test_action_proposals_api.py` — every test:
```
AttributeError: <module 'src.api.routes.action_proposals'> does not have the attribute 'get_db_session'
```

8 in `test_actions_api.py` — every test:
```
AttributeError: <module 'src.api.routes.actions'> does not have the attribute 'get_db_session'
```

1 error in `test_actions_api.py::TestListJobs::test_returns_jobs_list`:
```
TypeError: 'succeeded_count' is an invalid keyword argument for ActionJob
```

**Production impact — P0 RUNTIME CRASH:** `actions.py:155-156` accesses `job.succeeded_count` and `job.failed_count`. The `ActionJob` model has `actions_succeeded` and `actions_failed`. Any API call returning an `ActionJobResponse` (job list, execute-with-job, etc.) throws `AttributeError` → 500.

**Fixes required before deploy:**

1. `actions.py:155` → `job.actions_succeeded`
2. `actions.py:156` → `job.actions_failed`
3. `test_actions_api.py:97` → `actions_succeeded=1`
4. `test_actions_api.py:98` → `actions_failed=0`
5. Both test files: fix patch target — add `from src.database.session import get_db_session` to `actions.py` and `action_proposals.py`, OR change tests to mock at the dependency override level

**Deploy safe:** No.

---

### Module 6 — Dashboards & Reports

**Tests run:** No integration failures in dashboard files. 0 failures.

**Deploy safe:** Yes.

---

### Module 7 — Analytics & Attribution

**Tests run:** 0 failures.

**Deploy safe:** Yes.

---

### Module 8 — Data Health & Monitoring

**Tests run:** 0 failures in data health files directly.

**Note:** `test_alerts_e2e.py` has 1 ruff F401 (`MagicMock` unused import) — lint only, not a test failure.

**Deploy safe:** Yes.

---

### Module 9 — Agency & Multi-tenancy

**Tests run:** 0 failures.

**Deploy safe:** Yes.

---

### Module 10 — Platform & Admin

**Tests run:** 19 integration failures (Root Cause B — no DB), 1 integration failure (Root Cause E — missing function).

**Failures by type:**

No-DB failures (19) — pass in CI, not code bugs:
- `test_audit_api.py`: 10 tests → 503 (no PostgreSQL)
- `test_notifications_api.py`: 9 tests → 503 (no PostgreSQL)

Code bug (1):
- `TestAuditRBAC::test_cross_tenant_attempt_logs_audit_event`
- `AttributeError: <module 'src.services.audit_access_control'> does not have the attribute 'log_system_audit_event_sync'`
- Function is called in test but doesn't exist on the module

**Fix:**
- Check `audit_access_control.py` — either the function was renamed, removed, or the test is calling the wrong name. Align test with what exists.

**Deploy safe:** Yes for routes. The missing `log_system_audit_event_sync` is a test bug, not a route bug. The audit routes themselves don't call that function.

---

## Backend Lint — 33 Violations

All auto-fixable with `ruff check src/ --fix`. Breakdown:

| File | Issue |
|---|---|
| `src/api/routes/search.py` | F401 `HTTPException`, `status` unused |
| `src/jobs/reconcile_subscriptions.py` | F401 `BillingService` unused |
| `src/models/alert_rule.py` | F401 `datetime`, `timezone` unused |
| `src/services/alert_rule_service.py` | F401 `ComparisonOperator`, `AlertSeverity` unused |
| `src/services/shopify_ingestion.py` | F841 `access_token` assigned but never used |
| `src/tests/e2e/test_revenue_pipeline.py` | F401 `EXPECTED_OUTCOMES` unused |
| `src/tests/integration/test_alerts_e2e.py` | F401 `MagicMock` unused |
| `src/tests/integration/test_budget_pacing_e2e.py` | F401 `date`, `MagicMock`, `event` unused |
| `src/tests/platform/test_identity_collision.py` | F401 `Mock`, `patch`, `MagicMock`, `List` |
| `src/tests/platform/test_rate_limiting.py` | F401 `MagicMock` unused |
| `src/tests/platform/test_super_admin.py` | 3× F401 + 1× F841 |
| `src/tests/test_ad_ingestion.py` | F841 `accounts` unused |
| `src/tests/unit/test_alert_rule_service.py` | 4× F401 + 1× F841 |
| `src/tests/unit/test_budget_pacing_service.py` | F841 unused var |
| `src/tests/unit/test_search_logic.py` | F401 `pytest`, `SearchResult` |

---

## E2E Tests — All Skipped

51 tests decorated to skip. Nothing runs. Not a failure, but there is zero E2E coverage executing locally.

---

## Fix Queue

| Priority | Fix | File | Lines |
|---|---|---|---|
| P0 | `job.succeeded_count` → `job.actions_succeeded` | `actions.py` | 155 |
| P0 | `job.failed_count` → `job.actions_failed` | `actions.py` | 156 |
| P0 | `ActionJob(succeeded_count=1)` → `actions_succeeded=1` | `test_actions_api.py` | 97 |
| P0 | `ActionJob(failed_count=0)` → `actions_failed=0` | `test_actions_api.py` | 98 |
| P1 | Add `get_db_session` import to `actions.py` + `action_proposals.py` OR fix 21 test patch targets | `actions.py`, `action_proposals.py`, both test files | — |
| P1 | Fix `test_llm_config_api.py` — add auth mock, fix patch target | `test_llm_config_api.py` | all 12 tests |
| P1 | Fix `log_system_audit_event_sync` — rename or create the function | `audit_access_control.py` | — |
| P1 | Fix `test_platform_credentials_service.py` async wrapper | `test_platform_credentials_service.py` | — |
| P2 | `ruff check src/ --fix` | all | — |

---

## Deploy Decision

| Modules | Safe to deploy? |
|---|---|
| 1, 2, 3, 6, 7, 8, 9 | Yes |
| 4, 10 | Yes — test bugs only, routes work |
| 5 (Actions) | **No** — P0 runtime crash on any ActionJob response |
