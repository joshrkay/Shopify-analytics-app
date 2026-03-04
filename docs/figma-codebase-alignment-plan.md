# Figma-Codebase Alignment Plan

**Generated**: March 4, 2026
**Branch**: `claude/figma-codebase-alignment-plan-baSL9`
**Source**: Gap analysis comparing 88 Figma tasks vs codebase (79% coverage, 21 missing tasks)

---

## Overview

This plan addresses the 21 missing tasks and 37 partial implementations identified in the Figma-to-codebase delta analysis. Work is organized into 6 phases, ordered by impact and dependency.

---

## Phase 1: Design Token Foundation (Sprint 1 Gaps)

**Priority**: High — affects visual consistency across all pages
**Effort**: ~2 days
**Files touched**: 4-5 frontend files

### 1.1 Extract and apply Figma design tokens

Create a centralized design token file that maps Figma design decisions to Tailwind theme overrides.

**Tasks**:
- [ ] Create `frontend/src/styles/tokens.css` with CSS custom properties for:
  - Color palette (primary, secondary, accent, semantic colors from Figma)
  - Typography scale (font sizes, weights, line heights)
  - Spacing scale (if Figma uses non-standard spacing)
  - Border radii, shadows, transitions
- [ ] Update `frontend/src/index.css` to import tokens and extend Tailwind's `@theme` with Figma values
- [ ] Update `frontend/src/utils/chartColors.ts` to reference token CSS variables instead of hardcoded hex values

**Acceptance criteria**:
- All color, typography, and spacing values reference design tokens
- Changing a token value updates all components that use it
- Chart colors are consistent with the Figma palette

### 1.2 Create global color palette constants

**Tasks**:
- [ ] Define semantic color mappings in `tokens.css`: `--color-success`, `--color-warning`, `--color-danger`, `--color-info`
- [ ] Define platform brand colors: `--color-meta`, `--color-google`, `--color-tiktok`, `--color-shopify`
- [ ] Refactor existing hardcoded colors in `chartColors.ts`, `KpiWidget.tsx`, `Attribution.tsx`, `ChannelAnalytics.tsx`, and `Orders.tsx` to use tokens

### 1.3 Create typography scale

**Tasks**:
- [ ] Define typography tokens in `tokens.css`: `--font-size-xs` through `--font-size-4xl`, `--font-weight-normal/medium/semibold/bold`, `--line-height-tight/normal/relaxed`
- [ ] Map to Tailwind `@theme` fontSize overrides if Figma values differ from defaults

### 1.4 Create spacing scale

**Tasks**:
- [ ] Define spacing tokens if Figma uses a non-4px-based scale
- [ ] Map to Tailwind `@theme` spacing overrides
- [ ] If Figma uses standard 4px scale (matches Tailwind defaults), document this and mark as N/A

---

## Phase 2: Layout & Navigation Gaps (Sprint 2 Gaps)

**Priority**: High — affects overall app usability
**Effort**: ~3 days
**Files touched**: 6-8 frontend files

### 2.1 Add global search functionality

**Tasks**:
- [ ] Create `frontend/src/components/layout/GlobalSearch.tsx`
  - Command palette style (Cmd+K / Ctrl+K to trigger)
  - Search across: pages (nav items), recent dashboards, data sources, insights
  - Use shadcn `Command` component (already in `ui/command.tsx`)
- [ ] Create `frontend/src/hooks/useGlobalSearch.ts` for search logic
- [ ] Integrate into `AppHeader.tsx` — search icon in header bar
- [ ] Backend: Create `GET /api/search` route in `backend/src/api/routes/search.py`
  - Query dashboards, insights, sources by name/title
  - Return typed results with navigation paths

**Acceptance criteria**:
- Cmd+K opens search overlay
- Results grouped by type (Pages, Dashboards, Sources, Insights)
- Clicking a result navigates to it
- Debounced input (300ms)

### 2.2 Add Markinsight logo component

**Tasks**:
- [ ] Create `frontend/src/components/layout/MarkinsightIcon.tsx` matching Figma logo design
- [ ] Replace current branding in `Sidebar.tsx` with the Figma-accurate logo component

### 2.3 Align sidebar section grouping with Figma

**Tasks**:
- [ ] Compare current `NAV_SECTIONS` in `Sidebar.tsx` (Main/Channels) against Figma sidebar sections (Analytics/Tools/System)
- [ ] Restructure nav sections to match Figma grouping:
  - **Analytics**: Home, Attribution, Orders, Channels, Cohort Analysis, Budget Pacing
  - **Tools**: Dashboard Builder, Sources, Report Builder
  - **System**: Settings, Alerts, Sync Health, What's New
- [ ] Add nav items for new pages (Cohort Analysis, Budget Pacing, Alerts)

### 2.4 Mobile responsive improvements

**Tasks**:
- [ ] Verify sidebar drawer behavior on mobile (< 1024px)
- [ ] Ensure hamburger menu properly toggles sidebar overlay
- [ ] Note: RotatePhoneIndicator is low priority — skip unless Figma specifically requires it for chart pages

### 2.5 Create 404 / NotFound page

**Tasks**:
- [ ] Create `frontend/src/pages/NotFound.tsx` — simple page with "Page not found" message and link back to home
- [ ] Add catch-all route in `App.tsx`: `<Route path="*" element={<NotFound />} />`

---

## Phase 3: Missing Analytics Pages (Sprint 5 Gaps) — LARGEST GAP

**Priority**: Critical — 3 entire Figma pages have no implementation
**Effort**: ~8-10 days
**Dependencies**: Phase 1 (design tokens) recommended but not blocking

### 3.1 Cohort Analysis Page

The Figma design shows a retention heatmap with cohort-based customer analysis.

#### 3.1.1 dbt models (backend data layer)

**Tasks**:
- [ ] Create `analytics/models/cohorts/stg_cohort_base.sql`
  - Source: `canonical.orders` + customer data
  - Assign each customer to an acquisition cohort by first-order month
  - Output: `customer_id`, `tenant_id`, `cohort_month`, `first_order_date`, `acquisition_channel`
- [ ] Create `analytics/models/cohorts/fct_cohort_retention.sql`
  - Join cohort base with subsequent orders
  - Calculate: `cohort_month`, `period_number` (months since acquisition), `customers_active`, `customers_total`, `retention_rate`, `revenue`
  - Materialization: `incremental` with monthly grain
- [ ] Add dbt tests for the new models (unique, not_null, accepted_values)
- [ ] Update `analytics/dbt_project.yml` with `cohorts` folder schema config

#### 3.1.2 Backend route

**Tasks**:
- [ ] Create `backend/src/api/routes/cohort_analysis.py`
  - `GET /api/analytics/cohort-analysis` — returns cohort retention grid
  - Query params: `timeframe` (3m/6m/12m), `cohort_dimension` (month/quarter), `metric` (retention/revenue/orders)
  - Query `fct_cohort_retention` via SQL (verify against dbt model columns)
  - Response shape:
    ```json
    {
      "cohorts": [
        {
          "cohort_month": "2025-01",
          "customers_total": 150,
          "periods": [
            { "period": 0, "retention_rate": 1.0, "customers": 150 },
            { "period": 1, "retention_rate": 0.42, "customers": 63 },
            { "period": 2, "retention_rate": 0.28, "customers": 42 }
          ]
        }
      ],
      "summary": { "avg_retention_month_1": 0.38, "best_cohort": "2025-03" }
    }
    ```
- [ ] Register route in `backend/src/main.py`
- [ ] Verify module loads: `PYTHONPATH=. python -c "from src.api.routes import cohort_analysis"`

#### 3.1.3 Frontend page

**Tasks**:
- [ ] Create `frontend/src/services/cohortAnalysisApi.ts` with `getCohortRetention(timeframe, dimension, metric)`
- [ ] Create `frontend/src/pages/CohortAnalysis.tsx`
  - Retention heatmap: grid where rows = cohorts, columns = periods, cell color intensity = retention rate
  - Use Recharts or custom HTML table with background-color scaling
  - Timeframe selector (3m/6m/12m)
  - Cohort dimension toggle (monthly/quarterly)
  - Metric toggle (retention rate / revenue / order count)
  - Summary KPI cards at top (avg retention, best cohort, worst cohort)
- [ ] Create `frontend/src/components/charts/RetentionHeatmap.tsx` — reusable heatmap component
- [ ] Add lazy import + route in `App.tsx`: `/cohort-analysis`
- [ ] Add to sidebar nav under Analytics section
- [ ] Feature gate: `COHORT_ANALYSIS` (paid tier)

### 3.2 Budget Pacing Page

The Figma design shows spend tracking with progress bars and forecast charts.

#### 3.2.1 Backend model & dbt

**Tasks**:
- [ ] Create `backend/src/models/ad_budget.py`
  - `AdBudget` model: `id`, `tenant_id`, `source_platform`, `budget_monthly_cents`, `start_date`, `end_date`, `enabled`, `created_at`, `updated_at`
  - RLS policy on `tenant_id`
- [ ] Create Alembic migration for `ad_budgets` table
- [ ] Create `analytics/models/budget/fct_budget_pacing.sql`
  - Join `AdBudget` with `canonical.marketing_spend`
  - Calculate: `platform`, `date`, `daily_spend`, `cumulative_spend`, `budget_allocated`, `pct_budget_spent`, `days_elapsed`, `days_remaining`, `projected_total_spend`

#### 3.2.2 Backend routes

**Tasks**:
- [ ] Create `backend/src/services/budget_pacing_service.py`
  - `list_budgets(tenant_id)` — CRUD for budget rules
  - `get_pacing(tenant_id, timeframe)` — current pacing vs budget by platform
  - `get_forecast(tenant_id)` — projected end-of-period spend
- [ ] Create `backend/src/api/routes/budget_pacing.py`
  - `GET /api/budgets` — list budgets for tenant
  - `POST /api/budgets` — create budget
  - `PUT /api/budgets/{id}` — update budget
  - `DELETE /api/budgets/{id}` — delete budget
  - `GET /api/budget-pacing` — current pacing data
- [ ] Register route in `main.py`
- [ ] Verify module loads

#### 3.2.3 Frontend page

**Tasks**:
- [ ] Create `frontend/src/services/budgetPacingApi.ts`
- [ ] Create `frontend/src/pages/BudgetPacing.tsx`
  - Per-platform budget cards with progress bars
  - Progress bar color: green (on pace) / yellow (slightly over) / red (significantly over)
  - Pacing ratio: `% budget spent` vs `% time elapsed`
  - Forecast line chart showing projected spend vs budget limit
  - Budget CRUD: modal to set/edit monthly budgets per platform
- [ ] Create `frontend/src/components/budget/PacingProgressBar.tsx`
- [ ] Create `frontend/src/components/budget/BudgetForecastChart.tsx`
- [ ] Add lazy import + route in `App.tsx`: `/budget-pacing`
- [ ] Add to sidebar nav under Analytics section
- [ ] Feature gate: `BUDGET_PACING` (paid tier)

### 3.3 Alerts Page

The Figma design shows a notification center with alert rules and severity indicators.

#### 3.3.1 Backend model & service

**Tasks**:
- [ ] Create `backend/src/models/alert_rule.py`
  - `AlertRule`: `id`, `tenant_id`, `name`, `description`, `metric_name`, `comparison_operator` (gt/lt/eq/gte/lte), `threshold_value`, `evaluation_period` (daily/weekly/monthly), `enabled`, `severity` (info/warning/critical), `created_at`, `updated_at`
  - `AlertExecution`: `id`, `tenant_id`, `alert_rule_id`, `fired_at`, `metric_value`, `threshold_value`, `resolved_at`, `notification_id`
  - RLS policies on both tables
- [ ] Create Alembic migration
- [ ] Add `ALERT_TRIGGERED` to `NotificationEventType` enum (with `values_callable`)
- [ ] Create `backend/src/services/alert_rule_service.py`
  - CRUD for alert rules
  - `evaluate_rules(tenant_id)` — query dbt metrics, compare against thresholds
  - `notify_on_trigger()` — create notification via existing `NotificationService`
- [ ] Create background job: `backend/src/jobs/alert_evaluation_job.py`
  - Scheduled hourly via worker
  - Evaluates all enabled rules across all tenants
  - Creates `AlertExecution` records + notifications for triggered alerts

#### 3.3.2 Backend routes

**Tasks**:
- [ ] Create `backend/src/api/routes/alerts.py`
  - `GET /api/alerts/rules` — list alert rules
  - `POST /api/alerts/rules` — create rule
  - `PUT /api/alerts/rules/{id}` — update rule
  - `DELETE /api/alerts/rules/{id}` — delete rule
  - `GET /api/alerts/history` — list alert executions (fired alerts)
  - `GET /api/alerts/rules/{id}/history` — execution history for specific rule
- [ ] Register in `main.py`, verify module loads

#### 3.3.3 Frontend page

**Tasks**:
- [ ] Create `frontend/src/services/alertsApi.ts`
- [ ] Create `frontend/src/pages/Alerts.tsx`
  - Two tabs: "Rules" (manage alert rules) and "History" (fired alerts log)
  - Rules tab: list of alert rules with enable/disable toggle, edit/delete actions
  - History tab: timeline of fired alerts with severity badge, metric value, timestamp
  - Create/edit rule modal: metric picker, operator, threshold, period, severity
  - Severity indicators: colored badges (info=blue, warning=yellow, critical=red)
- [ ] Create `frontend/src/components/alerts/AlertRuleCard.tsx`
- [ ] Create `frontend/src/components/alerts/AlertHistoryTimeline.tsx`
- [ ] Create `frontend/src/components/alerts/CreateAlertRuleModal.tsx`
- [ ] Add lazy import + route in `App.tsx`: `/alerts`
- [ ] Add to sidebar nav under System section
- [ ] Feature gate: `ALERTS` (paid tier — or free tier with limited rule count)

---

## Phase 4: Partial Implementation Completion (Sprints 3-6 Gaps)

**Priority**: Medium — improves existing pages
**Effort**: ~4-5 days

### 4.1 MetricCard sparkline mini-charts

**Tasks**:
- [ ] Enhance `frontend/src/components/charts/KpiWidget.tsx` to accept optional `sparklineData` prop
- [ ] Render small inline Recharts `<AreaChart>` (50x20px) inside KPI cards showing 7-day trend
- [ ] Pass sparkline data from Dashboard.tsx

### 4.2 Enhanced drill-down modal with tabs

**Tasks**:
- [ ] Update `frontend/src/components/dashboard/BreakdownModal.tsx` to support tabbed views
- [ ] Tabs: Summary, Trend Chart, Data Table
- [ ] Use shadcn `Tabs` component (already available in `ui/tabs.tsx`)

### 4.3 Sortable table headers (consistent pattern)

**Tasks**:
- [ ] Create `frontend/src/components/common/SortableTable.tsx` — wrapper that adds sort indicators and click handlers to `<th>` elements
- [ ] Apply to Orders.tsx, Attribution.tsx, ChannelAnalytics.tsx tables

### 4.4 Cross-page date range sync

**Tasks**:
- [ ] Create `frontend/src/contexts/DateRangeContext.tsx`
  - Stores selected timeframe globally
  - Provider mounted in `App.tsx` `AppWithOrg()`
- [ ] Create `frontend/src/hooks/useDateRange.ts`
- [ ] Refactor `TimeframeSelector` to read/write from context
- [ ] Update all analytics pages (Dashboard, Attribution, Orders, ChannelAnalytics, CohortAnalysis, BudgetPacing) to use the shared date range context

### 4.5 Dashboard empty state

**Tasks**:
- [ ] Create empty state component for Dashboard.tsx when no data sources are connected
- [ ] Show friendly illustration + "Connect your first data source" CTA
- [ ] Reuse pattern from existing `EmptySourcesState.tsx`

### 4.6 Loading skeleton states (systematic)

**Tasks**:
- [ ] Audit all pages for loading state consistency
- [ ] Add Polaris `<SkeletonPage>` / `<SkeletonBodyText>` to any page that shows a raw spinner
- [ ] Priority pages: Dashboard, Attribution, Orders, CohortAnalysis, BudgetPacing, Alerts

---

## Phase 5: Settings & Intelligence Alignment (Sprint 6 Gaps)

**Priority**: Medium
**Effort**: ~2 days

### 5.1 Align Settings tabs with Figma spec

**Tasks**:
- [ ] Compare current Settings tabs (DataSources, Sync, Team) against Figma (Profile, Integrations, Notifications, Billing)
- [ ] Add missing tabs if needed:
  - Profile tab: user profile editing (may be handled by Clerk, in which case link to Clerk profile)
  - Notifications tab: surface existing `useNotificationPreferences` hook as a settings tab
  - Billing tab: link to existing `/billing/checkout` flow or embed billing summary
- [ ] Reorder tabs to match Figma sequence

### 5.2 AI Consultant suggested prompts

**Tasks**:
- [ ] Add suggested prompt chips to `InsightsFeed.tsx`
- [ ] Example prompts: "What drove revenue this week?", "Which channel has best ROAS?", "Show me customer retention trends"
- [ ] Clicking a prompt should trigger the AI insight generation flow

---

## Phase 6: Quality & Infrastructure (Sprint 7 Gaps)

**Priority**: Low-Medium — production readiness improvements
**Effort**: ~2-3 days

### 6.1 Visual QA pass

**Tasks**:
- [ ] Side-by-side comparison of each page against Figma designs
- [ ] Document pixel-level discrepancies in a tracking spreadsheet
- [ ] Prioritize fixes by visual impact

### 6.2 Performance monitoring

**Tasks**:
- [ ] Add Lighthouse CI to GitHub Actions: `npm run build && npx lighthouse-ci`
- [ ] Set performance budget: score >= 90
- [ ] Add bundle analysis: `npx vite-bundle-analyzer` or `rollup-plugin-visualizer`
- [ ] Set bundle size budget: < 200KB gzipped for initial JS

### 6.3 Accessibility audit

**Tasks**:
- [ ] Run `axe-core` audit on all pages
- [ ] Fix WCAG AA contrast violations
- [ ] Add missing ARIA labels to interactive elements
- [ ] Verify keyboard navigation on modals, dropdowns, tables

### 6.4 PR preview deployments

**Tasks**:
- [ ] Configure Render preview environments or add Render PR preview config to `render.yaml`
- [ ] Each PR gets a temporary deployment URL for visual review

---

## Entitlement Changes Required

New features need entitlement definitions in both systems:

| Feature Key | Free Tier | Growth | Pro | Enterprise |
|---|---|---|---|---|
| `COHORT_ANALYSIS` | No | Yes | Yes | Yes |
| `BUDGET_PACING` | No | Yes | Yes | Yes |
| `ALERTS` | 3 rules max | 10 rules | Unlimited | Unlimited |

**Files to update**:
- `backend/src/services/billing_entitlements.py` — add to `BILLING_TIER_FEATURES` dict
- `backend/src/models/plan_feature.py` — add `PlanFeature` rows via migration
- `frontend/src/services/entitlementsApi.ts` — add new feature key constants

---

## Implementation Order & Dependencies

```
Phase 1 (Design Tokens)          ← No dependencies, can start immediately
  ↓
Phase 2 (Layout & Nav)           ← Depends on Phase 1 for token values
  ↓
Phase 3 (Missing Pages)          ← Depends on Phase 2 for nav integration
  ├─ 3.1 Cohort Analysis         ← Needs dbt models first, then backend, then frontend
  ├─ 3.2 Budget Pacing           ← Needs DB model + migration first
  └─ 3.3 Alerts                  ← Needs DB models + background job
  ↓
Phase 4 (Partial Completions)    ← Can run in parallel with Phase 3
  ↓
Phase 5 (Settings & AI)          ← After Phase 3 (uses new features)
  ↓
Phase 6 (Quality)                ← After all feature work complete
```

**Parallelization opportunities**:
- Phase 1 + Phase 2.5 (404 page) can run simultaneously
- Phase 3.1, 3.2, 3.3 are independent — can be developed in parallel by different developers
- Phase 4 can run in parallel with Phase 3

---

## Estimated Timeline

| Phase | Effort | Can Parallel With |
|---|---|---|
| Phase 1: Design Tokens | 2 days | Phase 2.5 |
| Phase 2: Layout & Nav | 3 days | — |
| Phase 3: Missing Pages | 8-10 days | Phase 4 |
| Phase 4: Partial Completions | 4-5 days | Phase 3 |
| Phase 5: Settings & AI | 2 days | — |
| Phase 6: Quality | 2-3 days | — |
| **Total** | **~18-22 days** | (with parallelization: ~14-16 days) |

---

## Out of Scope (Acknowledged Divergences)

These items from the gap analysis are **intentionally different** and should NOT be aligned:

1. **Auth page** — Clerk handles auth; custom login/signup forms are unnecessary
2. **Vercel deployment** — Render is the production target; no migration needed
3. **Mock data modules** — Real API services exist; static mocks add no value
4. **Storybook** — Not prioritized; consider adding later if team grows
5. **RotatePhoneIndicator** — Niche mobile feature; low ROI
6. **Form validation on auth** — Clerk handles this

---

## Risk Mitigation

1. **dbt model verification** — All SQL queries MUST be verified against dbt model final SELECTs before merging (per CLAUDE.md policy)
2. **Route module import verification** — Run `PYTHONPATH=. python -c "from src.api.routes import <module>"` after every route file change
3. **Entitlement dual-path update** — Update both `BILLING_TIER_FEATURES` and `EntitlementPolicy` when adding features
4. **Enum `values_callable`** — All new SQLAlchemy Enum columns MUST include `values_callable=lambda enum_cls: [e.value for e in enum_cls]`
5. **Frontend `/api` prefix** — All new API service URLs must include `/api/` prefix
