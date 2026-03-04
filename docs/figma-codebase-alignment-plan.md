# Figma-Codebase Alignment Plan — Parallelized

**Generated**: March 4, 2026
**Branch**: `claude/figma-codebase-alignment-plan-baSL9`
**Source**: Gap analysis comparing 88 Figma tasks vs codebase (79% coverage, 21 missing tasks)

---

## Architecture: How Each Stream Connects

Every work stream follows the same full-stack vertical. Understanding this
is critical for parallelization — each stream is independent because each
owns its own slice through every layer:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FIGMA DESIGN (source of truth)                  │
│  Design tokens, page layouts, component specs, interaction patterns   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     FRONTEND (React/TypeScript)                        │
│  Page component → API service (createHeadersAsync) → types/interfaces │
│  Feature gate (FeatureGateRoute in App.tsx) → Sidebar nav item        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ fetch(`${API_BASE_URL}/api/...`)
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     MIDDLEWARE LAYER (FastAPI)                          │
│  CORSMiddleware → EmbedOnlyCSPMiddleware → TenantContextMiddleware    │
│  JWT → _resolve_tenant_from_db() → TenantGuard.enforce_authorization()│
│  Result: request.state.tenant_id, request.state.user_id set           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ get_tenant_context(request)
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     API ROUTE (backend/src/api/routes/*.py)            │
│  router = APIRouter(prefix="/api/...", tags=[...])                    │
│  Pydantic request/response models                                     │
│  Entitlement check via BillingEntitlementsService                     │
│  Register in main.py: app.include_router(module.router)               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     SERVICE LAYER (backend/src/services/*.py)          │
│  Business logic, SQL queries against dbt tables                       │
│  Tenant isolation: WHERE tenant_id = :tenant_id on every query        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                     DATA LAYER                                         │
│  SQLAlchemy models (backend/src/models/) → PostgreSQL + RLS           │
│  dbt models (analytics/models/) → staging → canonical → metrics/marts │
│  Enum columns: MUST use values_callable=lambda e: [x.value for x in e]│
└─────────────────────────────────────────────────────────────────────────┘
```

### Route Registration Pattern (for every new route)

```python
# 1. backend/src/api/routes/your_feature.py
from fastapi import APIRouter, Request
from src.platform.tenant_context import get_tenant_context
from src.database.session import SessionLocal

router = APIRouter(prefix="/api/your-feature", tags=["your_feature"])

def _get_db(request: Request):
    get_tenant_context(request)  # validates JWT + tenant → 401/403 if invalid
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. backend/main.py — add these two lines:
from src.api.routes import your_feature      # import at top
app.include_router(your_feature.router)       # register in router section

# 3. Verify: PYTHONPATH=. python -c "from src.api.routes import your_feature"
```

### Entitlement Integration Pattern (for gated features)

```python
# Backend: billing_entitlements.py
class BillingFeature:
    YOUR_FEATURE = "your_feature"  # add constant

BILLING_TIER_FEATURES = {
    'free':       { BillingFeature.YOUR_FEATURE: False },
    'growth':     { BillingFeature.YOUR_FEATURE: True },
    'enterprise': { BillingFeature.YOUR_FEATURE: True },
}
```

```typescript
// Frontend: App.tsx — wrap route with FeatureGateRoute
<Route path="/your-feature" element={
  <FeatureGateRoute feature="your_feature" entitlements={entitlements}
    entitlementsLoading={entitlementsLoading}
    entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
    <YourFeaturePage />
  </FeatureGateRoute>
} />
```

---

## Parallel Work Streams

```
                    ┌──────────────────────────────────────────┐
                    │         SHARED FOUNDATION (S0)           │
                    │  Design tokens, entitlement scaffolding  │
                    │  404 page, sidebar restructure           │
                    └──────────┬───────────────────────────────┘
                               │ tokens.css + nav structure ready
          ┌────────────────────┼────────────────────┬───────────────────────┐
          ▼                    ▼                    ▼                       ▼
 ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐  ┌──────────────────┐
 │  STREAM A (S-A) │ │  STREAM B (S-B) │ │  STREAM C (S-C) │  │  STREAM D (S-D)  │
 │ Cohort Analysis │ │ Budget Pacing   │ │ Alerts           │  │ UX Polish &      │
 │                 │ │                 │ │                  │  │ Existing Pages   │
 │ dbt: fct_cohort │ │ model: AdBudget │ │ model: AlertRule │  │                  │
 │ route: /api/    │ │ route: /api/    │ │ route: /api/     │  │ Global search    │
 │   analytics/    │ │   budgets,      │ │   alerts/rules,  │  │ KPI sparklines   │
 │   cohort-       │ │   budget-pacing │ │   alerts/history │  │ Drill-down tabs  │
 │   analysis      │ │ service: pacing │ │ service: rules   │  │ Sortable tables  │
 │ page: /cohort-  │ │ page: /budget-  │ │ job: evaluation  │  │ Date range sync  │
 │   analysis      │ │   pacing        │ │ page: /alerts    │  │ Empty/loading    │
 │                 │ │                 │ │                  │  │   states         │
 │ Entitlement:    │ │ Entitlement:    │ │ Entitlement:     │  │ Settings tabs    │
 │ COHORT_ANALYSIS │ │ BUDGET_PACING   │ │ ALERTS           │  │ AI prompts       │
 └─────────────────┘ └─────────────────┘ └─────────────────┘  └──────────────────┘
          │                    │                    │                       │
          └────────────────────┴────────────────────┴───────────────────────┘
                                         │
                               ┌─────────▼─────────┐
                               │   STREAM E (S-E)   │
                               │   Quality Gate     │
                               │   Visual QA        │
                               │   Lighthouse CI    │
                               │   a11y audit       │
                               │   Bundle analysis  │
                               └────────────────────┘
```

**Key**: S0 must complete first. Then S-A, S-B, S-C, S-D run fully in parallel. S-E runs after all streams merge.

---

## S0: Shared Foundation (BLOCKING — do first)

**Effort**: ~2 days | **Owner**: 1 developer
**Why blocking**: Establishes design tokens all streams consume, restructures sidebar nav that all new pages plug into, and scaffolds entitlement keys that all gated features reference.

### S0.1 Design Tokens

| Task | File(s) | Details |
|------|---------|---------|
| Create token file | `frontend/src/styles/tokens.css` | CSS custom properties: `--color-primary`, `--color-success/warning/danger/info`, `--color-meta/google/tiktok/shopify`, `--font-size-xs..4xl`, `--font-weight-*`, `--radius-*`, `--shadow-*` |
| Wire into Tailwind | `frontend/src/index.css` | `@import './styles/tokens.css'` + extend `@theme` with token references |
| Consolidate chart colors | `frontend/src/utils/chartColors.ts` | Replace hardcoded hex with `var(--color-*)` references |
| Consolidate platform colors | `Attribution.tsx`, `ChannelAnalytics.tsx`, `Orders.tsx`, `BreakdownModal.tsx` | Replace scattered `PLATFORM_COLORS` / `statusBadge` color dicts with shared token imports |

### S0.2 Sidebar Restructure

| Task | File(s) | Details |
|------|---------|---------|
| Restructure NAV_SECTIONS | `frontend/src/components/layout/Sidebar.tsx` | **Analytics**: Home, Attribution, Orders, Channels, Cohort Analysis, Budget Pacing — **Tools**: Dashboard Builder, Sources — **System**: Settings, Alerts, Sync Health, What's New |
| Add Markinsight logo | `frontend/src/components/layout/MarkinsightIcon.tsx` | SVG logo matching Figma; replace current branding in Sidebar.tsx |

### S0.3 Entitlement Scaffolding

These keys are added now so all streams can reference them without merge conflicts.

| Task | File(s) | Details |
|------|---------|---------|
| Add BillingFeature constants | `backend/src/services/billing_entitlements.py` | Add `COHORT_ANALYSIS = "cohort_analysis"`, `BUDGET_PACING = "budget_pacing"`, `ALERTS = "alerts"` to `BillingFeature` class |
| Add to tier matrix | `backend/src/services/billing_entitlements.py` | Add all 3 keys to `free` (False), `growth` (True), `enterprise` (True) in `BILLING_TIER_FEATURES` |
| Add alert rule limits | `backend/src/services/billing_entitlements.py` | `free`: `'max_alert_rules': 3`, `growth`: `'max_alert_rules': 10`, `enterprise`: `'max_alert_rules': -1` (unlimited) |

### S0.4 NotFound Page

| Task | File(s) | Details |
|------|---------|---------|
| Create 404 page | `frontend/src/pages/NotFound.tsx` | "Page not found" with Home link |
| Add catch-all route | `frontend/src/App.tsx` | `<Route path="*" element={<NotFound />} />` as last route |

### S0 Verification Checklist

```bash
# After S0, verify:
cd frontend && npm run build          # tokens compile, no TS errors
cd ../backend && PYTHONPATH=. python -c "from src.services.billing_entitlements import BillingFeature; print(BillingFeature.COHORT_ANALYSIS, BillingFeature.BUDGET_PACING, BillingFeature.ALERTS)"
```

---

## S-A: Cohort Analysis (Full-Stack Vertical)

**Effort**: ~3 days | **Owner**: 1 developer | **Depends on**: S0
**Zero overlap** with S-B, S-C, S-D — unique files at every layer.

### S-A.1 Data Layer — dbt Models

**Existing asset**: `metrics.fct_ltv` already has cohort-month grouping with retention rates at 90d/365d windows. Extend rather than rebuild.

| Task | File | Details |
|------|------|---------|
| Create cohort retention model | `analytics/models/cohorts/fct_cohort_retention.sql` | Source: `canonical.orders`. Group customers by first-order month (`cohort_month`). For each cohort + period_number (0..N months), calculate: `customers_total`, `customers_active`, `retention_rate`, `cohort_revenue`. Materialized as `table`. Cross-join `utils.dim_date_ranges` for period-over-period. Tenant isolation via `tenant_id` column. |
| Add schema config | `analytics/dbt_project.yml` | Under `models.markinsight`: add `cohorts: { +schema: analytics, +materialized: table }` |
| Add dbt tests | `analytics/models/cohorts/schema.yml` | `unique: id`, `not_null: [tenant_id, cohort_month, period_number]`, `accepted_values: { period_number: range(0,24) }` |

**SQL verification before commit**:
```bash
# Confirm source tables exist
find analytics/models -name "orders.sql"    # → canonical/orders.sql ✓
grep -l "dim_date_ranges" analytics/models/  # → utils/dim_date_ranges.sql ✓
```

### S-A.2 API Layer — Backend Route + Service

| Task | File | Details |
|------|------|---------|
| Create Pydantic schemas | `backend/src/api/schemas/cohort_analysis.py` | `CohortPeriod(period: int, retention_rate: float, customers: int, revenue: float)`, `CohortRow(cohort_month: str, customers_total: int, periods: list[CohortPeriod])`, `CohortAnalysisResponse(cohorts: list[CohortRow], summary: CohortSummary)` |
| Create route | `backend/src/api/routes/cohort_analysis.py` | `router = APIRouter(prefix="/api/analytics/cohort-analysis", tags=["cohort_analysis"])`. `GET /` with query params: `timeframe` (3m/6m/12m), `cohort_dimension` (month/quarter), `metric` (retention/revenue/orders). Uses `get_tenant_context(request)` for tenant isolation. Queries `fct_cohort_retention WHERE tenant_id = :tenant_id`. |
| Register route | `backend/main.py` | `from src.api.routes import cohort_analysis` + `app.include_router(cohort_analysis.router)` |
| Entitlement check | In route handler | `BillingEntitlementsService(db, tenant_id).check_feature_entitlement(BillingFeature.COHORT_ANALYSIS)` → 403 if not entitled |

**Route verification**:
```bash
cd backend && PYTHONPATH=. python -c "from src.api.routes import cohort_analysis; print('OK')"
```

### S-A.3 Frontend — Page + API Service

| Task | File | Details |
|------|------|---------|
| Create API service | `frontend/src/services/cohortAnalysisApi.ts` | `getCohortRetention(timeframe, dimension, metric)` → `GET ${API_BASE_URL}/api/analytics/cohort-analysis?...` using `createHeadersAsync()` + `handleResponse<CohortAnalysisResponse>()` |
| Create heatmap component | `frontend/src/components/charts/RetentionHeatmap.tsx` | HTML table: rows = cohorts, columns = periods. Cell `background-color` intensity scales with retention_rate (green gradient). Tooltip on hover showing exact values. |
| Create page | `frontend/src/pages/CohortAnalysis.tsx` | **Header**: TimeframeSelector (3m/6m/12m) + dimension toggle (month/quarter) + metric toggle (retention/revenue/orders). **KPI row**: avg retention at month 1, best cohort, worst cohort. **Main**: RetentionHeatmap. **Loading**: SkeletonPage. **Empty**: "Connect data sources to see cohort analysis." |
| Add route | `frontend/src/App.tsx` | Lazy import. `<Route path="/cohort-analysis" element={<FeatureGateRoute feature="cohort_analysis" ...><CohortAnalysis /></FeatureGateRoute>} />` |
| Sidebar nav item | `frontend/src/components/layout/Sidebar.tsx` | Already added in S0.2 — verify icon + path `/cohort-analysis` |

### S-A Integration Contract

```
Frontend calls:  GET /api/analytics/cohort-analysis?timeframe=12m&dimension=month&metric=retention
                 Authorization: Bearer <clerk_jwt>

Middleware:      TenantContextMiddleware extracts tenant_id from JWT
                 Sets request.state.tenant_id

Route:           get_tenant_context(request) validates auth
                 Checks COHORT_ANALYSIS entitlement → 403 if free tier
                 Queries: SELECT * FROM analytics.fct_cohort_retention
                          WHERE tenant_id = :tenant_id
                          AND cohort_month >= :start_date
                 Returns: CohortAnalysisResponse (JSON, snake_case)

Frontend:        handleResponse<CohortAnalysisResponse> parses JSON
                 Renders RetentionHeatmap + KPI cards
```

---

## S-B: Budget Pacing (Full-Stack Vertical)

**Effort**: ~3 days | **Owner**: 1 developer | **Depends on**: S0
**Zero overlap** with S-A, S-C, S-D — unique files at every layer.

### S-B.1 Data Layer — DB Model + dbt

| Task | File | Details |
|------|------|---------|
| Create SQLAlchemy model | `backend/src/models/ad_budget.py` | `AdBudget`: `id` (UUID, PK), `tenant_id` (FK), `source_platform` (String — 'meta_ads', 'google_ads', 'tiktok_ads'), `budget_monthly_cents` (BigInteger), `start_date`, `end_date` (Date), `enabled` (Boolean, default True), `created_at`, `updated_at`. Add `__table_args__` with `Index('ix_ad_budget_tenant_platform', 'tenant_id', 'source_platform')`. |
| Create Alembic migration | `backend/migrations/versions/xxx_create_ad_budgets.py` | `create_table('ad_budgets', ...)` + RLS policy: `CREATE POLICY ad_budgets_tenant_isolation ON ad_budgets USING (tenant_id = current_setting('app.current_tenant_id'))` |
| Create dbt pacing model | `analytics/models/budget/fct_budget_pacing.sql` | Source: `canonical.marketing_spend`. Calculates per platform per day: `daily_spend`, `cumulative_spend_mtd`, `days_elapsed`, `days_in_month`, `pct_time_elapsed`, `pct_budget_spent` (requires budget from API param or join), `projected_total_spend` = `cumulative_spend / pct_time_elapsed`. Materialized as `table`. |
| Add schema config | `analytics/dbt_project.yml` | `budget: { +schema: analytics, +materialized: table }` |

### S-B.2 API Layer — Backend Route + Service

| Task | File | Details |
|------|------|---------|
| Create Pydantic schemas | `backend/src/api/schemas/budget_pacing.py` | `AdBudgetCreate(source_platform: str, budget_monthly_cents: int, start_date: date, end_date: date | None)`, `AdBudgetResponse(id, source_platform, budget_monthly_cents, ...)`, `PacingData(platform: str, budget_cents: int, spent_cents: int, pct_spent: float, pct_time: float, pace_ratio: float, projected_total_cents: int, status: str)`, `BudgetPacingResponse(platforms: list[PacingData])` |
| Create service | `backend/src/services/budget_pacing_service.py` | `create_budget()`, `update_budget()`, `delete_budget()`, `list_budgets(tenant_id)`. `get_pacing(tenant_id)` — queries `canonical.marketing_spend` for MTD spend per platform, joins with `ad_budgets` table for budget targets, calculates pace ratio. |
| Create route | `backend/src/api/routes/budget_pacing.py` | `router = APIRouter(prefix="/api", tags=["budget_pacing"])`. Routes: `GET /budgets`, `POST /budgets`, `PUT /budgets/{id}`, `DELETE /budgets/{id}`, `GET /budget-pacing`. All use `get_tenant_context(request)`. Entitlement: `BUDGET_PACING`. |
| Register route | `backend/main.py` | `from src.api.routes import budget_pacing` + `app.include_router(budget_pacing.router)` |

**Route verification**:
```bash
cd backend && PYTHONPATH=. python -c "from src.api.routes import budget_pacing; print('OK')"
```

### S-B.3 Frontend — Page + API Service

| Task | File | Details |
|------|------|---------|
| Create API service | `frontend/src/services/budgetPacingApi.ts` | `listBudgets()`, `createBudget(data)`, `updateBudget(id, data)`, `deleteBudget(id)`, `getPacing()` — all use `createHeadersAsync()`, all URLs prefixed with `/api/`. |
| Create progress bar | `frontend/src/components/budget/PacingProgressBar.tsx` | Props: `pctSpent`, `pctTime`, `platform`. Color: green if pace_ratio < 1.1, yellow if 1.1-1.3, red if > 1.3. Shows `$X,XXX of $Y,YYY` label. |
| Create forecast chart | `frontend/src/components/budget/BudgetForecastChart.tsx` | Recharts `<AreaChart>`: X = day of month, Y = cumulative spend. Two lines: actual (solid) and projected (dashed). Horizontal line at budget cap. |
| Create budget modal | `frontend/src/components/budget/BudgetEditModal.tsx` | Form: platform select, monthly budget input ($), start/end dates. Uses shadcn `Dialog`. |
| Create page | `frontend/src/pages/BudgetPacing.tsx` | **Header**: Month selector. **Cards**: One `PacingProgressBar` per platform with edit/delete buttons. **Chart**: `BudgetForecastChart` for selected platform. **CTA**: "Set Budget" button opens `BudgetEditModal`. **Empty**: "Set your first budget to track ad spend pacing." |
| Add route | `frontend/src/App.tsx` | Lazy import. `<Route path="/budget-pacing" element={<FeatureGateRoute feature="budget_pacing" ...><BudgetPacing /></FeatureGateRoute>} />` |

### S-B Integration Contract

```
Frontend calls:  GET /api/budget-pacing      (read pacing data)
                 GET /api/budgets            (list budgets)
                 POST /api/budgets           (create budget)
                 PUT /api/budgets/{id}       (update budget)
                 DELETE /api/budgets/{id}    (delete budget)

Middleware:      TenantContextMiddleware → tenant_id from JWT

Route:           get_tenant_context(request) → auth + tenant
                 Checks BUDGET_PACING entitlement → 403 if free tier
                 Service queries: ad_budgets (ORM) + canonical.marketing_spend (raw SQL)
                 All queries: WHERE tenant_id = :tenant_id
```

---

## S-C: Alerts (Full-Stack Vertical)

**Effort**: ~4 days | **Owner**: 1 developer | **Depends on**: S0
**Zero overlap** with S-A, S-B, S-D — unique files at every layer.
**Unique complexity**: Background job for rule evaluation + integration with existing NotificationService.

### S-C.1 Data Layer — DB Models

| Task | File | Details |
|------|------|---------|
| Create AlertRule model | `backend/src/models/alert_rule.py` | `AlertRule`: `id` (UUID), `tenant_id` (FK), `user_id` (FK), `name` (String), `description` (Text, nullable), `metric_name` (String — e.g. 'roas', 'cac', 'revenue', 'spend'), `comparison_operator` (Enum: gt/lt/eq/gte/lte — use `values_callable`), `threshold_value` (Float), `evaluation_period` (Enum: daily/weekly/monthly — use `values_callable`), `enabled` (Boolean, default True), `severity` (Enum: info/warning/critical — use `values_callable`), `created_at`, `updated_at`. |
| Create AlertExecution model | `backend/src/models/alert_rule.py` | `AlertExecution`: `id` (UUID), `tenant_id` (FK), `alert_rule_id` (FK → AlertRule), `fired_at` (DateTime), `metric_value` (Float), `threshold_value` (Float), `resolved_at` (DateTime, nullable), `notification_id` (UUID, nullable — FK → Notification). |
| Create Alembic migration | `backend/migrations/versions/xxx_create_alert_tables.py` | `create_table('alert_rules', ...)`, `create_table('alert_executions', ...)`. Create PostgreSQL enum types with lowercase values. RLS policies on both tables. |
| Add notification event type | `backend/src/models/notification.py` | Add `ALERT_TRIGGERED = 'alert_triggered'` to `NotificationEventType` enum. **Critical**: Ensure the enum uses `values_callable`. |

### S-C.2 API Layer — Backend Route + Service + Job

| Task | File | Details |
|------|------|---------|
| Create Pydantic schemas | `backend/src/api/schemas/alerts.py` | `AlertRuleCreate(name, metric_name, comparison_operator, threshold_value, evaluation_period, severity)`, `AlertRuleResponse(id, name, ..., enabled, last_fired_at: datetime | None)`, `AlertExecutionResponse(id, alert_rule_id, rule_name, fired_at, metric_value, threshold_value, severity)` |
| Create service | `backend/src/services/alert_rule_service.py` | **CRUD**: `create_rule()`, `update_rule()`, `delete_rule()`, `list_rules(tenant_id)`, `toggle_rule(id, enabled)`. **Evaluation**: `evaluate_rules(tenant_id)` — for each enabled rule, query the relevant dbt metric table (`marts.mart_marketing_metrics` for roas/cac/spend, `metrics.fct_revenue` for revenue), compare latest value against threshold using the rule's operator. **On trigger**: call `NotificationService.notify()` with `ALERT_TRIGGERED` event type, create `AlertExecution` record. **Limit check**: `check_rule_count(tenant_id)` — enforce `max_alert_rules` from entitlements. |
| Create route | `backend/src/api/routes/alerts.py` | `router = APIRouter(prefix="/api/alerts", tags=["alerts"])`. Routes: `GET /rules` (list), `POST /rules` (create — check rule limit), `PUT /rules/{id}` (update), `DELETE /rules/{id}`, `PATCH /rules/{id}/toggle` (enable/disable), `GET /history` (paginated execution log), `GET /rules/{id}/history`. All: `get_tenant_context(request)` + `ALERTS` entitlement check. |
| Register route | `backend/main.py` | `from src.api.routes import alerts` + `app.include_router(alerts.router)` |
| Create background job | `backend/src/jobs/alert_evaluation_job.py` | Scheduled task (hourly). Iterates all tenants with enabled rules. Calls `AlertRuleService.evaluate_rules(tenant_id)` for each. Logs results. Error handling: per-tenant try/except so one tenant's failure doesn't block others. |

**Route verification**:
```bash
cd backend && PYTHONPATH=. python -c "from src.api.routes import alerts; print('OK')"
```

### S-C.3 Frontend — Page + API Service

| Task | File | Details |
|------|------|---------|
| Create API service | `frontend/src/services/alertsApi.ts` | `listAlertRules()`, `createAlertRule(data)`, `updateAlertRule(id, data)`, `deleteAlertRule(id)`, `toggleAlertRule(id, enabled)`, `getAlertHistory(params)`, `getRuleHistory(ruleId, params)`. All: `createHeadersAsync()`, `/api/alerts/...` URLs. |
| Create rule card | `frontend/src/components/alerts/AlertRuleCard.tsx` | Displays: name, metric, operator + threshold, period, severity badge. Actions: edit, delete, enable/disable toggle. Severity colors: info=`--color-info`, warning=`--color-warning`, critical=`--color-danger` (from S0 tokens). |
| Create history timeline | `frontend/src/components/alerts/AlertHistoryTimeline.tsx` | Vertical timeline: each entry shows severity badge + rule name + metric value vs threshold + timestamp. Paginated. |
| Create rule modal | `frontend/src/components/alerts/CreateAlertRuleModal.tsx` | Form fields: name, metric (dropdown: ROAS, CAC, Revenue, Spend, Orders), operator (>, <, =, >=, <=), threshold (number input), period (daily/weekly/monthly), severity (info/warning/critical). Uses shadcn `Dialog` + `Select` + `Input`. |
| Create page | `frontend/src/pages/Alerts.tsx` | **Tabs** (shadcn Tabs): "Rules" and "History". **Rules tab**: list of `AlertRuleCard` components + "Create Alert" button. Shows rule count vs limit badge (e.g., "3 / 3 rules"). **History tab**: `AlertHistoryTimeline`. **Loading**: SkeletonPage. **Empty rules**: "Create your first alert to get notified when metrics cross thresholds." |
| Add route | `frontend/src/App.tsx` | Lazy import. `<Route path="/alerts" element={<FeatureGateRoute feature="alerts" ...><Alerts /></FeatureGateRoute>} />` |

### S-C Integration Contract

```
Frontend calls:  GET    /api/alerts/rules            (list rules)
                 POST   /api/alerts/rules            (create rule)
                 PUT    /api/alerts/rules/{id}        (update rule)
                 DELETE /api/alerts/rules/{id}        (delete rule)
                 PATCH  /api/alerts/rules/{id}/toggle (enable/disable)
                 GET    /api/alerts/history           (execution log)

Middleware:      TenantContextMiddleware → tenant_id + user_id from JWT

Route:           get_tenant_context(request) → auth
                 ALERTS entitlement check
                 POST /rules: also checks max_alert_rules limit
                 Service → SQLAlchemy ORM for alert_rules/alert_executions tables
                 Evaluation job → raw SQL against marts.mart_marketing_metrics

Notification:    AlertRuleService.evaluate_rules() → NotificationService.notify()
                 Uses existing ALERT_TRIGGERED event type
                 Respects user notification preferences (in-app / email)
```

---

## S-D: UX Polish & Existing Page Improvements

**Effort**: ~4 days | **Owner**: 1 developer | **Depends on**: S0
**Zero overlap** with S-A, S-B, S-C — touches only existing files, no new routes.

### S-D.1 Global Search (Frontend + Backend)

| Task | File | Details |
|------|------|---------|
| Create search route | `backend/src/api/routes/search.py` | `GET /api/search?q=...` — queries dashboards (name ILIKE), insights (title ILIKE), sources (platform ILIKE). Returns `{ results: [{ type: 'dashboard'|'insight'|'source'|'page', title, path, icon }] }`. Tenant-isolated. Max 20 results. |
| Register route | `backend/main.py` | `from src.api.routes import search` + `app.include_router(search.router)` |
| Create search service | `frontend/src/services/searchApi.ts` | `searchAll(query: string)` → `GET /api/search?q=${query}` |
| Create search component | `frontend/src/components/layout/GlobalSearch.tsx` | Uses shadcn `Command` (already installed as `ui/command.tsx`). Cmd+K / Ctrl+K triggers. Groups results by type. Static page results (nav items) searched client-side. API results debounced 300ms. |
| Create hook | `frontend/src/hooks/useGlobalSearch.ts` | Manages search state, debounce, keyboard shortcut registration. |
| Integrate in header | `frontend/src/components/layout/AppHeader.tsx` | Add search icon button that opens GlobalSearch. Show Cmd+K hint. |

### S-D.2 KPI Sparklines

| Task | File | Details |
|------|------|---------|
| Enhance KpiWidget | `frontend/src/components/charts/KpiWidget.tsx` | Add optional `sparklineData?: number[]` prop. When provided, render a tiny Recharts `<AreaChart>` (64x24px, no axes, no labels) below the metric value. Use `--color-primary` with 20% opacity fill. |
| Pass trend data | `frontend/src/pages/Dashboard.tsx` | Extract 7-day trend arrays from existing KPI API response. Pass to KpiWidget. |

### S-D.3 Enhanced Drill-Down Modal

| Task | File | Details |
|------|------|---------|
| Add tabs to BreakdownModal | `frontend/src/components/dashboard/BreakdownModal.tsx` | Wrap existing content with shadcn `<Tabs>`. Three tabs: **Summary** (existing bar + pie charts), **Trend** (new LineChart showing metric over time), **Data** (new table view of raw data). |

### S-D.4 Sortable Table Headers

| Task | File | Details |
|------|------|---------|
| Create SortableTable util | `frontend/src/components/common/SortableTable.tsx` | Wrapper component. Props: `columns`, `data`, `defaultSort`. Renders `<th>` with sort arrow icons, click toggles asc/desc/none. Returns sorted data. |
| Apply to existing pages | `Orders.tsx`, `Attribution.tsx`, `ChannelAnalytics.tsx` | Replace plain `<table>` headers with SortableTable. |

### S-D.5 Cross-Page Date Range Sync

| Task | File | Details |
|------|------|---------|
| Create DateRange context | `frontend/src/contexts/DateRangeContext.tsx` | `DateRangeProvider` stores `{ timeframe, setTimeframe }`. Default: `'30days'`. |
| Create hook | `frontend/src/hooks/useDateRange.ts` | `useDateRange()` → `{ timeframe, setTimeframe }` |
| Mount provider | `frontend/src/App.tsx` | Add `<DateRangeProvider>` inside `AppWithOrg()`, wrapping `<Routes>`. |
| Refactor pages | `Dashboard.tsx`, `Attribution.tsx`, `Orders.tsx`, `ChannelAnalytics.tsx` | Replace local `useState('30days')` with `useDateRange()`. Changing timeframe on one page persists to others. |

### S-D.6 Loading & Empty States

| Task | File | Details |
|------|------|---------|
| Dashboard empty state | `frontend/src/pages/Dashboard.tsx` | When no data sources connected, show illustration + "Connect your first data source" CTA linking to `/sources`. |
| Skeleton audit | All page files | Replace raw spinners with Polaris `<SkeletonPage>` + `<SkeletonBodyText>`. Priority: Dashboard, Attribution, Orders. |

### S-D.7 Settings Tabs Alignment

| Task | File | Details |
|------|------|---------|
| Add Notifications tab | `frontend/src/components/settings/NotificationSettingsTab.tsx` | Surface existing `useNotificationPreferences` hook as a settings tab UI. |
| Add Billing tab | `frontend/src/components/settings/BillingSettingsTab.tsx` | Show current plan name + "Manage Plan" button linking to `/billing/checkout`. |
| Reorder tabs | `frontend/src/pages/Settings.tsx` | Tab order: Profile (→ Clerk), Integrations (existing DataSources), Notifications (new), Billing (new), Sync (existing), Team (existing). |

### S-D.8 AI Suggested Prompts

| Task | File | Details |
|------|------|---------|
| Add prompt chips | `frontend/src/pages/InsightsFeed.tsx` | Below header, render clickable chip buttons: "What drove revenue this week?", "Which channel has best ROAS?", "Show retention trends", "Compare ad spend efficiency". Clicking triggers AI insight generation with that prompt. |

---

## S-E: Quality Gate (runs after S-A through S-D merge)

**Effort**: ~2-3 days | **Owner**: 1 developer | **Depends on**: All streams merged

### S-E.1 Visual QA

| Task | Details |
|------|---------|
| Side-by-side Figma comparison | Open each page alongside Figma Make. Screenshot discrepancies. Log as issues with priority (P1 = layout broken, P2 = spacing/color, P3 = polish). |
| Fix P1/P2 issues | Address layout and color discrepancies identified in comparison. |

### S-E.2 Performance

| Task | File | Details |
|------|------|---------|
| Add Lighthouse CI | `.github/workflows/ci.yml` | Add job: `npm run build && npx @lhci/cli autorun`. Budget: performance >= 90. |
| Bundle analysis | `frontend/vite.config.ts` | Add `rollup-plugin-visualizer` to build. Set size budget: initial JS < 200KB gzip. |

### S-E.3 Accessibility

| Task | Details |
|------|---------|
| axe-core audit | Run `npx axe-cli` on all pages. Fix WCAG AA contrast violations. |
| Keyboard nav | Verify tab order on: GlobalSearch modal, AlertRuleModal, BudgetEditModal, BreakdownModal tabs. |
| ARIA labels | Add `aria-label` to icon-only buttons (search, notification bell, sidebar collapse). |

### S-E.4 Integration Testing

| Task | Details |
|------|---------|
| Route import smoke test | `PYTHONPATH=. python -c "from src.api.routes import cohort_analysis, budget_pacing, alerts, search"` |
| Frontend build | `cd frontend && npm run build && npm run lint` |
| Backend tests | `cd backend && make test` |
| dbt compile | `cd analytics && dbt compile --profiles-dir . --project-dir .` |

---

## Merge Coordination

Each stream works on its own branch, merging into the feature branch:

| Stream | Branch | Touches `main.py`? | Touches `App.tsx`? | Touches `Sidebar.tsx`? |
|--------|--------|--------------------|--------------------|------------------------|
| S0 | `claude/figma-codebase-alignment-plan-baSL9` | No | Yes (404 route) | Yes (restructure) |
| S-A | `s-a/cohort-analysis` | Yes (1 import + 1 include) | Yes (1 route) | No (done in S0) |
| S-B | `s-b/budget-pacing` | Yes (1 import + 1 include) | Yes (1 route) | No (done in S0) |
| S-C | `s-c/alerts` | Yes (1 import + 1 include) | Yes (1 route) | No (done in S0) |
| S-D | `s-d/ux-polish` | Yes (1 import + 1 include for search) | Yes (DateRangeProvider + route) | No (done in S0) |

**Merge conflict zones** (small, predictable):
- `main.py` lines 21-67 (imports) and 224-298 (router registration) — each stream adds 2 lines; resolve by keeping all additions
- `App.tsx` lazy imports section and `<Routes>` section — each stream adds 1 lazy import + 1 `<Route>`; resolve by keeping all additions

**Merge order**: S0 first → then S-A, S-B, S-C, S-D in any order → S-E last.

---

## Summary

| Stream | What | Effort | Owner | Files Created | Files Modified |
|--------|------|--------|-------|---------------|----------------|
| **S0** | Foundation | 2 days | Dev 1 | 3 (tokens.css, MarkinsightIcon, NotFound) | 5 (index.css, chartColors, Sidebar, App, billing_entitlements) |
| **S-A** | Cohort Analysis | 3 days | Dev 2 | 5 (dbt model, schema, route, service, page + heatmap) | 3 (dbt_project.yml, main.py, App.tsx) |
| **S-B** | Budget Pacing | 3 days | Dev 3 | 8 (model, migration, dbt, schemas, service, route, 3 components, page) | 3 (dbt_project.yml, main.py, App.tsx) |
| **S-C** | Alerts | 4 days | Dev 4 | 9 (2 models, migration, schemas, service, route, job, 3 components, page) | 3 (notification.py enum, main.py, App.tsx) |
| **S-D** | UX Polish | 4 days | Dev 1 (or 5) | 6 (search route+service+component, DateRange context, SortableTable, NotificationSettingsTab) | 10+ (existing pages) |
| **S-E** | Quality Gate | 2-3 days | Any | 0 | 2-3 (CI config, vite config) |
| **Total** | | **~8-9 days wall clock** (parallel) | 4-5 devs | ~31 new files | ~20 modified files |

---

## Out of Scope (Unchanged from v1)

1. **Auth page** — Clerk handles auth
2. **Vercel deployment** — Using Render
3. **Mock data modules** — Real APIs exist
4. **Storybook** — Not prioritized
5. **RotatePhoneIndicator** — Low ROI
6. **Form validation on auth** — Clerk handles this

---

## Risk Mitigation (Unchanged from v1)

1. **dbt model verification** — All SQL queries verified against dbt model final SELECTs
2. **Route module import verification** — `PYTHONPATH=. python -c "from src.api.routes import <module>"`
3. **Entitlement dual-path update** — Both `BILLING_TIER_FEATURES` and `EntitlementPolicy`
4. **Enum `values_callable`** — All new SQLAlchemy Enum columns
5. **Frontend `/api` prefix** — All new API service URLs
6. **Merge conflict prevention** — S0 handles shared files (Sidebar, billing_entitlements) before parallel streams start
