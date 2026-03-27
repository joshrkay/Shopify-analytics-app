# Launch Readiness QA Modules

This document is the execution plan to launch the Shopify analytics app with confidence.
It is structured as modules so the team can run work in parallel and track readiness quickly.

## Module 1 — Current Feature/Surface Map (What is live today)

### Frontend route surfaces (page-by-page)
Source of truth: `frontend/src/App.tsx` route table.

- `/` Dashboard
- `/onboarding`
- `/builder`, `/reports`, `/dashboards/wizard`, `/dashboards/:dashboardId/edit` (custom report/builder flows)
- `/dashboards`, `/dashboards/:dashboardId`
- `/sources`, `/data-sources`, `/oauth/callback`
- `/settings`
- `/home`
- `/analytics`
- `/billing/checkout`, `/billing/callback`
- `/insights`
- `/approvals`
- `/attribution`
- `/orders`
- `/channels/:platform`, `/channel/:channelKey`
- `/ai-consultant`
- `/sync`
- `/cohorts`, `/cohort-analysis`
- `/budget-pacing`
- `/alerts`
- `/whats-new`
- `/admin/plans`, `/admin/diagnostics`

### Core backend/data modules
- API app + migrations in `backend/`.
- Worker execution loops in `backend/src/workers/`.
- Data-model and transform layer in `analytics/` (dbt).
- Superset embed/security/datasets in `docker/superset/`.
- RLS and retention controls in `db/rls/` and `db/retention/`.

## Module 2 — Deploy Readiness (What must be true before go-live)

Use `docs/deployment-guide.md` as the deployment source of truth.

### Required launch gates
1. **Infrastructure ready**
   - Render services healthy (`markinsight-api`, worker, scheduler, reconcile cron, dbt cron, Redis, Postgres).
2. **Secrets/config complete**
   - Clerk, Shopify, Airbyte, encryption key, and OpenRouter vars set in environment.
3. **Migrations complete**
   - Deploy logs show required migrations completed.
4. **Smoke checks pass**
   - `./scripts/smoke-test.sh https://<domain>` passes.
5. **Webhook callbacks active**
   - Clerk + Shopify webhooks successfully deliver events post-deploy.

## Module 3 — Page-by-Page QA (click every critical control)

Run in staging with a real tenant and connected data source.

### Navigation + access control
- Confirm all sidebar/header routes load without blank/error fallback.
- Validate feature-gated routes redirect to `/paywall` when entitlement is missing and open when entitled.
- Validate shared dashboard view route works without plan gate.

### Per-page action checklist
For every page route listed in Module 1:
1. Open page directly (deep link) and through in-app navigation.
2. Click all visible primary/secondary CTA buttons.
3. Trigger all tabs, dropdowns, filter chips, and date selectors.
4. Validate loading, empty, error, and success states.
5. Validate browser refresh retains the expected state.
6. Confirm no console errors and no failed XHR/fetch calls.


### Automated clickthrough baseline
- Run Playwright harness clickthrough:
  - `npm --prefix frontend exec playwright test tests/e2e/page-qa-clickthrough.spec.ts`
- This suite loads each key page through `e2e/test-harness.html` and clicks visible buttons to catch runtime render/interaction regressions quickly.

## Module 4 — Mock/Fake Data Elimination Gate

Before launch, verify customer-facing screens do not silently rely on non-production placeholders.

### Known hotspots already identified
- `frontend/src/components/dashboards/wizard/PreviewReportCard.tsx`
  - Explicit sample-data fallback in report preview.
- `frontend/src/utils/sampleDataGenerator.ts`
  - Synthetic chart data generation utility.
- `frontend/src/services/notificationsApi.ts`
  - Performance alert/test notification are explicit stubs.

### Decision policy
- **Allowed:** clearly labeled preview-mode sample data in builder flows.
- **Not allowed:** production dashboard/analytics pages showing synthetic data without explicit labeling.

### Verification steps
1. Run mock-data audit script:
   - `./scripts/qa/mock_data_audit.sh`
2. Review findings by severity:
   - `HIGH`: runtime app code with mock/fake/sample fallback.
   - `LOW`: tests/docs/examples only.
3. For each `HIGH` finding:
   - Confirm it is either (a) removed, or (b) clearly labeled non-production preview behavior.

## Module 5 — Streaming Data QA (source → backend → warehouse → UI)

### End-to-end validation flow
1. **Create a known test event** in source platform (e.g., an order/change you can identify).
2. **Ingestion check**
   - Confirm sync job is enqueued and completes in worker logs.
3. **Warehouse check**
   - Confirm record appears in raw/canonical tables.
4. **API check**
   - Validate endpoint payload reflects fresh record.
5. **UI check**
   - Confirm dashboard visual and data console both update accordingly.
6. **Freshness/health indicators**
   - Confirm sync/freshness badges and status pages reflect the update timeline.

### Suggested acceptance criteria
- New source record visible in UI within target SLA.
- No tenant isolation leaks (RLS enforced).
- No fallback to sample/mock paths in production user journeys.

## Module 6 — Launch Sign-off Template

A launch can proceed only when all are marked PASS:
- [ ] Deploy smoke tests pass.
- [ ] Page-by-page QA complete for all routes.
- [ ] No unresolved HIGH mock/fake data findings.
- [ ] Streaming data E2E test passes with real event.
- [ ] On-call/runbook links verified and owners assigned.
