# MarkInsight / Signals AI — Go-Live Beta Readiness Report

**Date:** March 6, 2026
**Prepared for:** Josh Kay
**App URL:** https://app.markinsight.net

---

## Executive Summary

The MarkInsight Shopify analytics platform is **ready for a controlled beta launch** with a small group of merchants. The core infrastructure is deployed and healthy on Render, the backend API is comprehensive (211 endpoints, zero stubs), the frontend is polished with Shopify Polaris, and the dbt data pipeline is production-grade with 44 models and 150+ tests.

**Overall Readiness: 8/10** — The platform can serve beta users today with some caveats around data pipeline activation and external service configuration that need verification.

---

## What's Working Right Now

**Infrastructure (Live on Render)**

- Web service (markinsight-api) is deployed and responding — `/health` returns `{"status":"ok"}`
- PostgreSQL 15 database is live with all 53 migrations applied (identity tables, RBAC, billing, AI schemas, etc.)
- Docker multi-stage build bundles React frontend into backend container
- Auto-deploy from `main` branch is active (~3 min deploy cycle)
- CI pipeline has 4 quality gates (platform tests, dbt validation, billing regression, tenant isolation)

**Backend API (211 endpoints across 46 route modules)**

- Authentication: Clerk JWT verification with v1/v2 format support, lazy User/Tenant/Role sync
- Billing: Shopify Billing API checkout, subscription management, entitlements (dual-path: Subscription-based + free-tier fallback)
- Data Sources: 20 endpoints — OAuth initiate/callback for 7 platforms (Meta, Google, TikTok, Snapchat, Pinterest, Twitter, Shopify), API key connect for 4 (Klaviyo, Attentive, Postscript, SMSBump)
- Custom Dashboards: Full CRUD with versioning, sharing, audit trails, optimistic locking
- AI Features: Insights, recommendations, action proposals with approval workflows — all entitlement-gated
- Data Health: Freshness monitoring, sync health, root cause diagnostics
- Audit & Compliance: Structured audit logging, CSV export, GDPR webhooks (customer/shop redaction, data requests)
- Agency Support: Multi-store access management with request/approval workflows
- Admin: Plan management, super admin, changelog, backfills

**Frontend (21 pages, TypeScript + React 18 + Polaris v12)**

- Dashboard with KPI cards and timeframe selector
- Data source connection wizard (OAuth + API key flows)
- Custom dashboard builder with drag-and-drop grid layout
- AI insights feed, approvals inbox
- Billing checkout and paywall with feature gating
- Settings, sync health monitoring, attribution analysis
- Error boundaries at root and page levels
- Clerk token refresh every 50s with localStorage fallback

**Data Pipeline (44 dbt models across 8 layers)**

- Raw → Staging → Canonical → Attribution → Semantic → Metrics → Marts
- Tenant isolation enforced at every layer (config + macros + regression tests)
- Incremental materialization with lookback windows (7/30/90 days)
- 3 attribution models (last-click, multi-touch linear, time decay)
- Key metrics: ROAS, CAC, AOV, LTV with edge case handling
- 150+ dbt tests with severity=error (blocks builds on failure)

---

## What Needs Verification Before Beta Users

These items are likely configured but should be explicitly verified:

### 1. Environment Variables on Render (Critical)

Confirm these are set in the Render dashboard (they're marked `sync: false` so they aren't auto-configured):

| Variable | Purpose | How to Verify |
|----------|---------|---------------|
| `CLERK_FRONTEND_API` | JWT validation URL | Without this, all protected endpoints return 503 |
| `CLERK_SECRET_KEY` | Token verification | Required for any authenticated request |
| `VITE_CLERK_PUBLISHABLE_KEY` | Frontend auth | Baked into build — must be set before Docker build |
| `SHOPIFY_API_KEY` | OAuth + billing | Required for store connection and checkout |
| `SHOPIFY_API_SECRET` | OAuth + billing | Required for webhook HMAC verification |
| `OPENROUTER_API_KEY` | AI features | Required for insights/recommendations generation |
| `ENCRYPTION_KEY` | Credential vault | Required for storing OAuth tokens securely |

**Verification:** Visit `https://app.markinsight.net/api/health/readiness` — it checks identity schema tables exist.

### 2. Shopify App Configuration

- Is the app registered in Shopify Partners dashboard?
- Is the app URL set to `https://app.markinsight.net`?
- Are GDPR webhook URLs configured (customers/redact, shop/redact, customers/data_request)?
- Is the Shopify Billing API enabled for the app?
- Do you have a test Shopify store for beta testing?

### 3. Clerk Organization Setup

- Is a Clerk application configured for production?
- Is the JWKS endpoint reachable from Render?
- Have you created test organizations for beta users?
- Are webhook URLs configured in Clerk dashboard (`/api/webhooks/clerk`)?

### 4. Airbyte Connection (Data Pipeline)

- Is an Airbyte workspace provisioned?
- Is `AIRBYTE_WORKSPACE_ID` and `AIRBYTE_API_TOKEN` set?
- Has a PostgreSQL destination been configured in Airbyte pointing to the Render database?
- Without Airbyte, data source connections will fail at the "connect" step

### 5. dbt Models Built

- Have `dbt run` and `dbt test` been executed against the production database?
- The `analytics`, `canonical`, `attribution`, `metrics`, `semantic`, and `marts` schemas must exist
- Without dbt models built, dashboard KPI queries will return empty/503
- `performance_indexes.sql` migration was deferred (depends on dbt schemas) — run it manually after dbt

---

## What's Not Yet Active (Commented Out in render.yaml)

These services are fully configured but disabled. Enable them when ready:

| Service | Purpose | Dependencies | When to Enable |
|---------|---------|-------------|----------------|
| **markinsight-worker** | Background jobs (sync orchestration, AI generation) | Redis | When you need async processing beyond request/response |
| **markinsight-reconcile-subscriptions** | Hourly billing reconciliation | Redis, worker | When paid plans are live |
| **markinsight-superset** | Embedded analytics dashboards | Superset DB, Redis | When you want Superset-powered analytics views |
| **markinsight-redis** | Caching + job queue | None | Required by worker, cron, and Superset |

**Note:** The worker entry point (`src.jobs.worker`) doesn't have a corresponding file yet. Create `backend/src/jobs/worker.py` before uncommenting the worker service.

---

## Known Limitations for Beta

### Feature Stubs (Frontend UI exists, backend incomplete)

| Feature | What Works | What's Missing |
|---------|-----------|----------------|
| Attentive OAuth | Catalog entry shows | API key connect works, but no OAuth URL builder for Attentive specifically |
| Klaviyo OAuth | Catalog entry shows | API key connect works, but no OAuth URL builder for Klaviyo specifically |
| Shopify Email OAuth | Catalog entry shows | Uses Shopify OAuth (shared), but Airbyte source type mapping may be incomplete |
| Paid plan checkout | BillingCheckout.tsx works | Requires a real Shopify store with valid access_token for Billing API calls |

### Data Gaps

- `canonical.order_line_items` — No dbt model exists. Any feature needing line-item data won't work
- `canonical.products` — No dbt model exists. Product catalog queries won't work
- If a tenant has no connected data sources, the dashboard shows empty KPI cards (silently, no error banner)

### Database Scale

- PostgreSQL plan is basic-256mb — sufficient for beta (5-20 merchants) but monitor with:
  ```sql
  SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;
  ```

---

## Beta Launch Checklist

### Must-Do (Day of Launch)

- [ ] Verify all env vars are set in Render dashboard
- [ ] Confirm `https://app.markinsight.net/health` returns `{"status":"ok"}`
- [ ] Confirm `https://app.markinsight.net/api/health/readiness` passes
- [ ] Test Clerk login flow end-to-end (sign up → org creation → app access)
- [ ] Test at least one data source OAuth flow (e.g., Shopify or Meta Ads)
- [ ] Verify dbt models are built (dashboard KPIs load, not empty)
- [ ] Test free plan entitlements (feature gates block premium features correctly)
- [ ] Check Shopify Admin embed loads correctly (if embedding in Shopify)

### Should-Do (First Week)

- [ ] Run `performance_indexes.sql` manually after confirming dbt schemas exist
- [ ] Set up error monitoring (Sentry or similar) — currently only Render logs
- [ ] Test billing checkout with a test Shopify store
- [ ] Verify GDPR webhook handlers receive and process events
- [ ] Load test with expected beta user count
- [ ] Review console.log statements in frontend (144 found, mostly error handlers)

### Nice-to-Have (Before Wider Launch)

- [ ] Enable Redis + background worker for async AI generation
- [ ] Enable Superset for embedded analytics views
- [ ] Add `order_line_items` and `products` dbt models for richer analytics
- [ ] Increase test coverage (frontend has 5 test files for 21 pages)
- [ ] Set up monitoring dashboards for API latency, error rates, database size

---

## Architecture Strengths for Beta

The codebase has several qualities that make it resilient for a beta:

- **Fail-closed auth** — If anything goes wrong with tenant resolution, it returns 503 (not a data leak)
- **Idempotent migrations** — `schema_migrations` table prevents re-running applied migrations
- **Optimistic locking** — Dashboard edits use `expected_updated_at` to prevent overwrite conflicts
- **Graceful degradation** — KPI queries silently return empty when data isn't available (no crashes)
- **Audit trail** — Every API call is logged with correlation IDs for debugging
- **Tenant isolation at 3 layers** — Middleware, PostgreSQL RLS, and dbt model enforcement

---

## Summary

The app is deployed, the API is comprehensive, and the data pipeline is well-engineered. The main gap between "deployed" and "beta-ready" is verifying that external services (Clerk, Shopify, Airbyte) are configured and that dbt models have been built against the production database. Once those are confirmed, you can invite beta merchants.
