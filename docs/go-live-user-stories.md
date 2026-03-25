# Go-Live User Stories

Generated from full codebase assessment (2026-03-25). Each story is independently deliverable.

---

## Priority 1: Must Build (Blocking Go-Live)

### Story GL-1: ApprovalsInbox Frontend Page

**As a** merchant admin,
**I want** a UI to view, approve, and reject AI action proposals,
**So that** I can control which automated actions are executed on my ad platforms.

**Acceptance Criteria:**
- [ ] New page at `/approvals` route (replace current stub)
- [ ] Lists all pending action proposals for the current tenant
- [ ] Each proposal card shows: action type, affected entity (campaign/ad set), risk disclaimer, expected effect, expiry date (7-day TTL)
- [ ] "Approve" button calls `POST /api/action-proposals/{id}/approve`
- [ ] "Reject" button opens reason modal, calls `POST /api/action-proposals/{id}/reject` with reason
- [ ] Only visible to users with MERCHANT_ADMIN or AGENCY_ADMIN role
- [ ] Audit trail tab shows decision history via `GET /api/action-proposals/{id}/audit`
- [ ] Empty state when no pending proposals
- [ ] Expired proposals shown as "Expired" (not actionable)
- [ ] Feature-gated behind `AI_ACTIONS` entitlement

**Backend routes (already exist):**
- `GET /api/action-proposals` — list with filtering
- `GET /api/action-proposals/{id}` — single proposal
- `POST /api/action-proposals/{id}/approve`
- `POST /api/action-proposals/{id}/reject`
- `GET /api/action-proposals/{id}/audit`

**Estimate:** Medium (frontend only, backend complete)

---

## Priority 2: Must Verify (Configuration / Infrastructure)

### Story GL-2: Production Environment Verification

**As a** deployment engineer,
**I want** a runnable checklist that validates all production configuration,
**So that** I know the app will work before opening to merchants.

**Acceptance Criteria:**
- [ ] Script verifies all required env vars are set (non-empty) in the running environment
- [ ] Script checks Airbyte health endpoint is reachable
- [ ] Script checks Redis PING succeeds
- [ ] Script checks PostgreSQL connection works
- [ ] Script checks dbt marts have rows (mart_marketing_metrics, mart_revenue_metrics are not empty)
- [ ] Script checks plans table has active plans
- [ ] Script checks PlanFeature rows exist for each active plan
- [ ] Script checks Clerk JWKS endpoint is reachable
- [ ] Script checks SHOPIFY_BILLING_TEST_MODE != "true"
- [ ] Script checks OAUTH_REDIRECT_URI matches CORS_ORIGINS domain
- [ ] Script outputs pass/fail per check with clear remediation instructions

**Estimate:** Small

---

### Story GL-3: Seed Production Plans and Entitlements

**As a** product manager,
**I want** plans, pricing, and feature entitlements correctly seeded in the production database,
**So that** merchants see accurate pricing and get the right features.

**Acceptance Criteria:**
- [ ] Free, Growth, Pro, Enterprise plans exist in `plans` table with correct `price_monthly_cents`
- [ ] All feature keys have `PlanFeature` rows for every plan (enabled/disabled per tier)
- [ ] Feature keys include: AI_INSIGHTS, AI_RECOMMENDATIONS, AI_ACTIONS, CUSTOM_REPORTS, ADVANCED_DASHBOARDS, AGENCY_ACCESS, DATA_EXPORT, WAREHOUSE_EXPORT, COHORT_ANALYSIS, BUDGET_PACING, ALERTS
- [ ] `BILLING_TIER_FEATURES` static dict in `billing_entitlements.py` matches PlanFeature rows
- [ ] Verified via automated test or migration script

**Estimate:** Small

---

### Story GL-4: OAuth Platform Credentials Configuration

**As a** deployment engineer,
**I want** all ad platform OAuth credentials configured in Render,
**So that** merchants can connect their ad accounts.

**Acceptance Criteria:**
- [ ] META_APP_ID + META_APP_SECRET set
- [ ] GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET + GOOGLE_ADS_DEVELOPER_TOKEN set
- [ ] TIKTOK_APP_ID + TIKTOK_APP_SECRET set
- [ ] SNAPCHAT_CLIENT_ID + SNAPCHAT_CLIENT_SECRET set
- [ ] PINTEREST_APP_ID + PINTEREST_APP_SECRET set
- [ ] TWITTER_CLIENT_ID + TWITTER_CLIENT_SECRET set
- [ ] LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET set
- [ ] MICROSOFT_ADS_CLIENT_ID + MICROSOFT_ADS_CLIENT_SECRET + MICROSOFT_ADS_DEVELOPER_TOKEN set
- [ ] HUBSPOT_CLIENT_ID + HUBSPOT_CLIENT_SECRET set
- [ ] SHOPIFY_API_KEY + SHOPIFY_API_SECRET set
- [ ] OAUTH_REDIRECT_URI = `https://app.markinsight.net/api/sources/oauth/callback`
- [ ] Each platform tested with a real OAuth flow end-to-end

**Estimate:** Medium (requires app registrations on each platform)

---

### Story GL-5: Airbyte Instance Deployment and Verification

**As a** deployment engineer,
**I want** Airbyte running and accessible from the Render deployment,
**So that** data ingestion pipelines work.

**Acceptance Criteria:**
- [ ] Airbyte instance deployed (OSS or Cloud)
- [ ] AIRBYTE_BASE_URL or AIRBYTE_API_TOKEN configured in Render
- [ ] Health check endpoint returns 200
- [ ] At least one test workspace can be created
- [ ] PostgreSQL destination configured in Airbyte pointing to production DB
- [ ] Source connectors available: source-shopify, source-facebook-marketing, source-google-ads, source-tiktok-marketing

**Estimate:** Medium

---

### Story GL-6: Initial dbt Run and Mart Population

**As a** data engineer,
**I want** dbt models built against the production database,
**So that** analytics dashboards and AI insights have data to query.

**Acceptance Criteria:**
- [ ] `dbt run` completes successfully against production PostgreSQL
- [ ] All mart tables created: `marts.mart_marketing_metrics`, `marts.mart_revenue_metrics`, `marts.fct_marketing_metrics`
- [ ] Canonical tables created: `canonical.orders`, `canonical.marketing_spend`
- [ ] Attribution table created: `attribution.last_click`
- [ ] `dbt test` passes with no errors
- [ ] Hourly cron (`dbt-incremental`) verified to be running

**Estimate:** Small (assuming Airbyte has synced data)

---

## Priority 3: Should Fix Before Launch

### Story GL-7: Fix AI Consultant "View Details" Dead Link

**As a** merchant,
**I want** the "View Details" button on recommendations to show full details,
**So that** I can understand the recommendation before acting on it.

**Acceptance Criteria:**
- [ ] "View Details" button on recommendation cards navigates to detail view or opens modal
- [ ] Detail view shows: full rationale, affected entity, expected impact, risk level, confidence score, supporting metrics
- [ ] If linking to ApprovalsInbox, navigation works correctly

**Estimate:** Small

---

### Story GL-8: Verify Notifications Settings Backend Integration

**As a** merchant,
**I want** notification preferences (email, Slack) to actually save and apply,
**So that** I receive alerts through my preferred channels.

**Acceptance Criteria:**
- [ ] Settings > Notifications tab form submits to a real backend endpoint
- [ ] Preferences persist across page refreshes
- [ ] Backend endpoint exists and saves to database
- [ ] If backend endpoint is missing, document and create it

**Estimate:** Small-Medium

---

### Story GL-9: Paid Checkout Error Handling

**As a** merchant without a connected Shopify store,
**I want** a clear error message when I try to upgrade to a paid plan,
**So that** I know I need to connect my store first instead of seeing a silent failure.

**Acceptance Criteria:**
- [ ] `POST /api/billing/checkout` returns a user-friendly error when ShopifyStore doesn't exist
- [ ] Frontend `BillingCheckout.tsx` displays the error message with a CTA to connect store
- [ ] Error message: "Please connect your Shopify store before upgrading to a paid plan"
- [ ] CTA links to `/sources` or `/onboarding`

**Estimate:** Small

---

## Priority 4: Nice to Have (Post-Launch)

### Story GL-10: Frontend Data Caching with React Query

**As a** merchant,
**I want** pages to load instantly when navigating back,
**So that** the app feels responsive.

**Acceptance Criteria:**
- [ ] Install and configure React Query (TanStack Query)
- [ ] Convert top-level data fetches to useQuery hooks
- [ ] Stale-while-revalidate behavior for dashboard, sources, insights
- [ ] Mutation hooks with cache invalidation for create/update/delete

**Estimate:** Large

---

### Story GL-11: Superset Embedded Analytics Deployment

**As a** merchant on Growth+ plan,
**I want** embedded Superset dashboards available in the Analytics page,
**So that** I can explore my data with advanced visualizations.

**Acceptance Criteria:**
- [ ] Superset instance deployed (uncomment render.yaml section or deploy separately)
- [ ] JWT authentication configured between app and Superset
- [ ] RLS rules enforced for tenant isolation in Superset
- [ ] At least one dashboard template available
- [ ] `/analytics` page shows Superset embed when available

**Estimate:** Large

---

### Story GL-12: Circuit Breaker for External Platform APIs

**As a** system,
**I want** a circuit breaker pattern on ad platform API calls,
**So that** one platform's outage doesn't cascade to all sync jobs.

**Acceptance Criteria:**
- [ ] Circuit breaker wraps each platform's API calls (Meta, Google, TikTok, etc.)
- [ ] After N consecutive failures, circuit opens and fails fast for that platform
- [ ] Circuit half-opens after cooldown period, allows one test request
- [ ] Other platforms continue syncing normally
- [ ] Dashboard shows circuit state per platform

**Estimate:** Medium

---

### Story GL-13: Dead Letter Queue for Failed Sync Jobs

**As a** system,
**I want** permanently failed sync jobs moved to a dead letter queue,
**So that** they can be investigated and retried manually.

**Acceptance Criteria:**
- [ ] After max retries exhausted, job moves to DLQ table instead of staying in main queue
- [ ] Admin endpoint to list DLQ entries
- [ ] Admin endpoint to retry DLQ entry
- [ ] Alert fires when DLQ grows beyond threshold

**Estimate:** Medium

---

### Story GL-14: Missing dbt Models (order_line_items, products)

**As a** data analyst,
**I want** order line items and products available in the analytics layer,
**So that** product-level analytics and per-SKU reporting work.

**Acceptance Criteria:**
- [ ] `canonical.order_line_items` dbt model created from Shopify raw data
- [ ] `canonical.products` dbt model created from Shopify raw data
- [ ] Schema tests added for both models
- [ ] Backend queries that reference these tables no longer 503

**Estimate:** Medium

---

### Story GL-15: Frontend Optimistic Locking

**As a** merchant editing a dashboard simultaneously with a teammate,
**I want** a conflict warning when my save would overwrite their changes,
**So that** work isn't silently lost.

**Acceptance Criteria:**
- [ ] Frontend sends `expected_updated_at` on PUT/PATCH requests
- [ ] Backend returns 409 Conflict when timestamp doesn't match
- [ ] Frontend shows "This item was modified by someone else. Reload?" dialog
- [ ] Applies to: dashboards, alert rules, sync settings

**Estimate:** Medium
