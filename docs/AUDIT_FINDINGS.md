# Performance & Cleanup Audit — Per-Folder Findings

Audit date: 2026-02-06. Plan: performance-cleanup-audit (folder-by-folder).

**Baseline (summary):**
- Stack: FastAPI, React/Vite, PostgreSQL, Redis, Render, GitHub Actions.
- Backend: `requirements.txt` pinned (FastAPI 0.104, SQLAlchemy 2.0, httpx, redis, pytest, hypothesis).
- Frontend: React 18, Polaris 12, Vite 5, Vitest.
- Analytics: dbt-core 1.7.x, dbt-postgres.
- Config: `config/alert_thresholds.yml`, `config/data_freshness_sla.yml`, `config/governance/`, `config/plans.json`.

---

## 1. Backend (`backend/src`)

### 1.1 API routes

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **Expensive total count on list endpoints** | `audit.py` (lines 145, 267, 390), `recommendations.py:211`, `insights.py:214`, `actions.py:240,676`, `llm_config.py:588`, `changelog_service` used by changelog routes | **Perf**: `query.count()` on filtered query runs a full COUNT; on large tables (e.g. `audit_log`) this can be slow and scales with table size. | For list endpoints where UI only needs "has_more", consider omitting `total` or estimating it (e.g. fetch `limit+1` and return `has_more` only). If total is required, add a DB index on common filter columns (tenant_id, timestamp) and document that count is expensive for large ranges. |
| **Pagination already bounded** | All list routes | Good: `limit` is capped (e.g. 20–100 or 50–500). | No change. |

### 1.2 Services

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **TODOs in committed code** | `platform_credentials_service.py`: 110, 146, 278, 336, 369, 390, 407 | **Compliance**: .cursorrules disallow TODOs unless tracked. Multiple stubs (DB lookup, encryption, revocation, API test) leave credentials path incomplete. | Track each TODO in an issue; either implement or mark as intentional stub with issue link and approval. |
| **TODO in worker** | `notification_email_worker.py:163` | Same as above. | Link to issue or implement "Integrate with user service to get email addresses". |
| **ChangelogService N+1-style counts** | `changelog_service.py`: `get_unread_count` (lines 219–234) | **Perf**: Loops over `FEATURE_AREAS` and runs one `base_query.filter(...).count()` per area. | Replace with a single query using GROUP BY feature_area (or equivalent) to get all counts in one round-trip. |
| **Superset dataset sync sequential** | `superset_dataset_sync.py`: loop over `models.items()` (lines 366–424) | **Perf**: Each dataset is synced one-by-one (create/update, refresh columns, activate version). For many datasets, total time is linear. | Consider batching Superset API calls where the API allows (e.g. bulk column refresh) or parallelizing independent dataset updates with a bounded pool to avoid rate limits. |
| **RecommendationGenerationService two-step fetch** | `recommendation_generation_service.py`: `_fetch_unprocessed_insights` (lines 163–196) | **Perf**: Raw SQL for IDs then `AIInsight` query by `id.in_(insight_ids)`. Two round-trips. | Single query: select full `AIInsight` rows with the same WHERE/NOT EXISTS and ORDER/LIMIT to avoid two round-trips. |
| **Action batch execution sequential by design** | `action_execution_service.py`: `execute_batch` (lines 524–565) | Docstring states sequential to avoid rate limiting. | No change; document in findings only. |

### 1.3 Jobs / workers

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **DQ runner per-tenant sequential** | `dq_runner.py`: `run()` (lines 394–410) | **Perf**: For each tenant, `run_for_tenant` is awaited; events are extended and committed per batch. No parallelism across tenants. | Consider running tenants in a bounded concurrent pool (e.g. asyncio Semaphore) to reduce wall-clock time while limiting concurrency. |

### 1.4 Integrations / HTTP

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Timeouts present** | OpenRouter client, Airbyte client, Shopify billing, platform executors (e.g. Shopify, Meta, Google) | Good: connect/read timeouts set. | No change. |

### 1.5 Auth / middleware

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Context resolution** | `auth/context_resolver.py` | AuthContext built per request with tenant/role lookups. | Ensure DB access is minimal and cached where appropriate (e.g. short TTL per user if needed). No change recommended without profiling. |

### 1.6 Repositories / database

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Base repo count** | `repositories/base_repo.py:343` | Generic count used by callers. | Callers that use this for pagination should be aware of cost on large tables (same as API count finding). |

---

## 2. Frontend (`frontend/src`)

### 2.1 Components and pages

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **SyncHealth page unreachable** | `pages/SyncHealth.tsx` exists; no `<Route>` in `App.tsx` | **Dead code**: Page and `syncHealthApi` are used only by this page; `DataFreshnessBadge` comment references "navigate to SyncHealth page". | Either add a route (e.g. `/sync-health`) and link from health UI, or remove the page and API usage if the feature was deprecated. |
| **No route-based code splitting** | `App.tsx`: all pages imported eagerly | **Perf**: Initial JS bundle includes every page (AdminPlans, RootCausePanel, Analytics, Paywall, InsightsFeed, ApprovalsInbox, WhatsNew). | Use `React.lazy()` and `Suspense` for route components to split chunks by route and reduce initial load. |
| **ConsentApprovalModal is .jsx** | `components/ConsentApprovalModal.jsx` | **Consistency**: Rest of app is TypeScript. | Optional: migrate to .tsx and add types for props/state. |

### 2.2 Hooks and contexts

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **Fetch without abort on unmount** | `DataHealthContext` (fetchData), `useEntitlements`, `WhatsNew` (fetchEntries), `SyncHealth`, etc. | **Perf / correctness**: If user navigates away during fetch, setState may run after unmount (React 18 suppresses warning but work is wasted). | Use AbortController in fetch calls and pass signal; in useEffect cleanup, abort the controller so in-flight requests don’t update state. |
| **DataHealthContext polling** | `DataHealthContext.tsx`: schedulePoll with setTimeout | Good: cleanup clears timeout; visibility change pauses when tab hidden. | No change. |

### 2.3 Services and build

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **No explicit Vite chunk splitting** | `vite.config.ts` | Vite automatically splits dynamic imports; all route imports are static. | Once route-level lazy loading is added, consider `build.rollupOptions.output.manualChunks` if needed (e.g. Polaris in a vendor chunk). |
| **Duplicate fetch pattern** | Multiple pages (WhatsNew, ApprovalsInbox, InsightsFeed, etc.) each have local fetch + useEffect | **Maintainability**: Same pattern repeated; no shared cache (e.g. React Query). | Optional: introduce a thin data layer (e.g. React Query or SWR) for list endpoints to get caching, dedup, and abort-on-unmount. |

---

## 3. Analytics / dbt (`analytics`)

### 3.1 Models

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Canonical and metrics** | `canonical/` (orders, marketing_spend, fact_*), `metrics/fct_revenue.sql` | Good: incremental where appropriate; unique_key and on_schema_change set. | No change. |
| **Marts as full tables** | `marts/mart_marketing_metrics.sql`, `marts/mart_revenue_metrics.sql`, `marts/marketing/fct_marketing_metrics.sql`, `metrics/fct_roas.sql`, `fct_cac.sql`, `fct_aov.sql` | **Perf**: Materialized as `table` (full refresh). For large fact bases, full rebuild can be slow. | Consider incremental marts or incremental-intermediate models where sources are incremental and aggregation can be expressed as incremental (e.g. by date partition). Evaluate by run duration and data volume. |
| **Placeholder in fct_revenue** | `fct_revenue.sql` (lines 88–89): partial refund uses `total_price * 0.5` | **Correctness**: Comment states need actual refund amount from refunds array. | Replace with real refund amount when Shopify refunds structure is available; track in story/ticket. |

### 3.2 Macros and config

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **Duplicate freshness config** | `dbt_project.yml` vars `freshness_sla` vs `config/data_freshness_sla.yml` | **Maintainability**: Macro and docs say "keep both in sync"; backend reads YAML, dbt reads vars. | Single source of truth: e.g. generate dbt vars from YAML in a pre-step or document a strict update checklist when changing SLAs. |
| **get_freshness_threshold** | `macros/get_freshness_threshold.sql` | Used in tests/models; sources use inline var() per dbt 1.11+. | No change. |

### 3.3 Governance and tests

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Governance column approvals** | `analytics/governance/approved_columns_*.yml` | Per-source column allowlists. | Periodically prune unused columns or sources; ensure schema_registry and governance stay aligned. |

---

## 4. Database & migrations (`db`)

### 4.1 Migrations and indexes

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Performance indexes** | `db/migrations/performance_indexes.sql` | Composite indexes on (tenant_id, date), (tenant_id, channel), (tenant_id, date, channel) for orders, marketing_spend, campaign_performance. | No change. |
| **RLS and roles** | `db/rls/raw_rls.sql`, `db/config/database_timeouts.sql` | Tenant isolation and timeouts. | Confirm statement_timeout and analytics.max_rows align with Superset and API expectations. |

### 4.2 Retention and cleanup

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Raw cleanup** | `db/retention/raw_cleanup.sql` | Retention policy for raw data. | Ensure deletes are batched or use partition drop where applicable to avoid long locks; document retention window. |

---

## 5. Infra / CI (`docker`, `.github/workflows`, `scripts`)

### 5.1 GitHub Actions

| Issue | Location | Impact | Recommendation |
|-------|----------|--------|----------------|
| **No frontend checks** | `.github/workflows/ci.yml` | **CI gap**: Lint, typecheck, and tests for frontend are not run in CI. | Add a job (e.g. `frontend`) that runs `npm ci`, `npm run lint`, `npm run build`, `npm test` so PRs validate frontend. |
| **Repeated setup** | Multiple jobs each run Set up Python, Install dependencies | **Perf**: Pip cache is used; duplicate steps across jobs. | Optional: use a reusable workflow or composite action to reduce duplication; low priority if pipeline time is acceptable. |
| **dbt deps from backend dir** | dbt-validation: "Install dbt dependencies" with `working-directory: ./backend` | dbt is installed in backend folder; dbt run/test use `working-directory: ./analytics`. | Prefer installing dbt in analytics context (`./analytics` and `pip install -r requirements.txt` from analytics) for clarity, or document that backend venv is shared. |

### 5.2 Docker

| Finding | Location | Impact | Recommendation |
|---------|----------|--------|----------------|
| **Compose layout** | `docker-compose.yml`: postgres, redis, superset, backend, frontend | Standard; healthchecks and depends_on in place. | No change. |
| **Backend volume** | `backend` service mounts `./backend` as :ro | Dev convenience. | No change. |

---

## Priority summary (backend only so far)

| Priority | Item | Effort |
|----------|------|--------|
| High | Resolve or track TODOs in `platform_credentials_service.py` and `notification_email_worker.py` | Medium (implement or document) |
| Medium | ChangelogService: single-query unread counts by feature area | Low |
| Medium | List endpoints: avoid or optimize expensive `total` count on large tables | Medium |
| Low | RecommendationGenerationService: single-query fetch for unprocessed insights | Low |
| Low | Superset dataset sync: batch or parallelize where safe | Medium |
| Low | DQ runner: bounded concurrency across tenants | Medium |
