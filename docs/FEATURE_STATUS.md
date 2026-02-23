# MarkInsight (Signals AI) — Feature Status Report

> Last updated: 2026-02-23

## What the Software Does

**MarkInsight** is a **multi-tenant SaaS analytics platform** that embeds inside the Shopify Admin panel. It provides Shopify merchants with:

1. **Unified marketing analytics** — Pull data from Shopify, Google Ads, Meta Ads, TikTok, and other platforms into one place
2. **AI-powered insights** — Automatically detect anomalies, trends, and opportunities across sales and marketing data using LLMs (via OpenRouter)
3. **AI recommendations & actions** — Suggest concrete actions (pause campaigns, adjust budgets) and optionally execute them with approval workflows
4. **Custom dashboards** — Drag-and-drop dashboard builder with charts, KPIs, and templates
5. **Marketing attribution** — Multi-touch attribution modeling via dbt data pipeline (raw -> staging -> canonical -> attribution -> metrics -> marts)
6. **Embedded analytics** — Apache Superset integration for advanced SQL-based exploration
7. **Agency support** — One user can manage multiple Shopify stores with role-based access
8. **Billing** — Tiered plans (Free, Growth, Pro, Enterprise) with feature gating via Shopify Billing API

### Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy, Pydantic, Alembic
- **Frontend**: TypeScript, React 18, Vite 5, Shopify Polaris v12, Recharts, react-grid-layout
- **Auth**: Clerk (OAuth2/JWT)
- **Database**: PostgreSQL 15 with row-level security (RLS)
- **Cache/Queue**: Redis 7
- **Data Pipeline**: dbt, Airbyte for ETL
- **Embedded Analytics**: Apache Superset
- **LLM Integration**: OpenRouter API
- **Deployment**: Docker, Render.com, GitHub Actions CI

### Scale

- 43 route modules, 150+ API endpoints
- 57 database models
- 50+ service classes
- 18 frontend pages, 80+ reusable components
- 28 frontend API service modules
- 3 external integrations (OpenRouter, Airbyte, Shopify)

---

## Working Features

### Core Platform

| Feature | Details |
|---------|---------|
| Authentication (Clerk) | JWT-based auth with Clerk OAuth2, org provisioning, tenant isolation |
| Multi-tenancy | TenantContextMiddleware, PostgreSQL RLS, per-request tenant scoping |
| RBAC | Data-driven roles (admin, viewer, agency_admin, agency_viewer) with permission evaluation |
| CI/CD pipeline | GitHub Actions with 4 quality gates: platform tests, dbt validation, billing regression, tenant isolation |

### Data Sources & Ingestion

| Feature | Details |
|---------|---------|
| Shopify data sync | OAuth connect, Airbyte-based ingestion, sync orchestration |
| Google Ads | OAuth flow, account discovery, data ingestion via Airbyte |
| Meta/Facebook Ads | OAuth flow, account discovery, data ingestion via Airbyte |
| TikTok Ads | OAuth flow with backend handler |
| Source management UI | Connect wizard, connection status cards, disconnect, sync config |
| Sync health monitoring | Per-connector health, incident tracking, backfill execution |
| Data quality checks | DQ models, freshness tracking, availability state per source |

### AI Features

| Feature | Details |
|---------|---------|
| AI Insights | LLM-powered insight generation (OpenRouter), anomaly detection, severity/category filtering, dismiss/recover |
| AI Recommendations | Tactical recommendation engine, accept/reject workflow, priority filtering |
| AI Action Proposals | Action proposal generation, approval inbox, risk assessment, audit trail |
| AI Action Execution | Full execution pipeline with status tracking (queued -> executing -> succeeded/failed), idempotency keys |
| Action Rollback | Rollback capability with before/after state capture |
| Action Safety | Safety service with kill-switch feature flags |
| LLM Routing | Model registry, prompt governance, multi-model routing via OpenRouter |

### Dashboards & Reporting

| Feature | Details |
|---------|---------|
| Custom dashboards | Full CRUD: create, list, edit, delete, publish, duplicate, archive |
| Dashboard builder | Drag-drop grid (react-grid-layout), report configurator, chart type selection |
| Chart widgets | Area, bar, line, KPI, pie, table chart types via Recharts |
| Dashboard sharing | Share permissions, shared dashboard viewing |
| Version history | Immutable version snapshots, restore capability |
| Dashboard audit trail | Append-only audit log for dashboard operations |
| Report templates | Template gallery with category filtering, preview, instantiation |

### Billing & Entitlements

| Feature | Details |
|---------|---------|
| Plan management | Admin CRUD for plans and features, 4 tiers configured |
| Feature gating | `<FeatureGate>` component + `useFeatureEntitlement` hook, route-level gating |
| Free plan activation | Checkout flow works for free tier |
| Entitlements API | `/api/billing/entitlements` with dual-path (Subscription table + static fallback) |
| Billing webhooks | Shopify webhook HMAC verification, subscription update handling |

### User & Team Management

| Feature | Details |
|---------|---------|
| Team members | List, invite, update role, remove members |
| Tenant invites | Clerk-backed invitation flow |
| Agency access | Multi-store management, store switching, access request/approval workflow |
| Access revocation | Grace-period access removal |

### Audit & Compliance

| Feature | Details |
|---------|---------|
| Audit logging | Comprehensive event logging with structured JSON, correlation IDs |
| Audit querying | Filter by event type, date range, user |
| Audit export | CSV/JSON export |
| Safety events | Dedicated safety event tracking for AI actions |

### Other Working Features

| Feature | Details |
|---------|---------|
| Changelog / What's New | Release notes with category filtering, read tracking |
| Data change tracking | Aggregated change events for "what changed" summaries |
| Notifications | Notification model, email sender, worker job, preference model |
| Diagnostics | Root cause analysis panel with ranked hypotheses |
| dbt pipeline | Full model chain: raw -> staging -> canonical -> attribution -> semantic -> metrics -> marts |
| OAuth callback handling | Universal OAuth redirect handler for all platforms |

---

## Not Working / Incomplete Features

### Stub OAuth Integrations

These platforms have a frontend catalog entry but no backend OAuth handler implementation.

| Feature | What Exists | What's Missing |
|---------|-------------|----------------|
| Attentive | Catalog entry in source list | No OAuth URL builder in `sources.py`, no Airbyte connection setup |
| Klaviyo | Catalog entry in source list | No OAuth URL builder in `sources.py`, no Airbyte connection setup |
| Shopify Email | Catalog entry in source list | No OAuth URL builder in `sources.py`, no Airbyte connection setup |

### Billing Gaps

| Feature | What Exists | What's Missing |
|---------|-------------|----------------|
| Paid plan checkout (Growth/Pro/Enterprise) | `BillingCheckout.tsx` works, Shopify Billing API client exists | Requires a real Shopify store with valid `access_token` to complete checkout |
| Per-tenant entitlement overrides | Database model exists | Admin API surface missing, governance authorization not enforced, audit event taxonomy incomplete |
| Entitlement override migration | Planned | `tenant_entitlement_overrides` table migration artifact missing |

### Embedded Analytics (Superset)

| Feature | What Exists | What's Missing |
|---------|-------------|----------------|
| Superset embedding | JWT embed service, explore guardrails, Docker config, frontend iframe integration | **Not deployed to production** — Superset service is commented out in `render.yaml` |

### Infrastructure Not Running in Production

| Component | What Exists | What's Missing |
|-----------|-------------|----------------|
| Redis | Config in render.yaml | Commented out — not deployed |
| Background worker | `worker.Dockerfile`, job definitions, worker handlers | Commented out in render.yaml — not deployed |
| Cron jobs | Reconciliation jobs defined | Commented out in render.yaml — not deployed |

### Frontend Stubs / Placeholders

| Feature | What Exists | What's Missing |
|---------|-------------|----------------|
| Settings page | Tab-based layout with 8 tabs | Most tabs show placeholder content ("Configure your X settings") |
| Dashboard page AI chat | AI Assistant chat interface | Shows mock responses when AI not configured |
| Sync config settings | Frontend service methods | `updateSyncSchedule`, `updateDataProcessing`, `updateStorageConfig` return placeholder responses |
| LLM config | Frontend service API | `setApiKey`, `updateFeatureFlags` not fully implemented |
| Notification test | `testNotification()` method | Returns `{ success: true }` stub |
| API key connection test | Source connection hook | TODO: "Implement API key connection test" |

### Dashboard Builder (Phase 2) Gaps

| Feature | What Exists | What's Missing |
|---------|-------------|----------------|
| Save-as-template | Alert placeholder in wizard | Backend integration for template saving (noted TODO in WizardFlow.tsx) |
| Builder architecture | useState-based state | Deviates from planned reducer pattern |
| Builder test coverage | No dedicated test files | Component tests, integration tests, e2e tests all missing |

---

## Feature Maturity Summary

| Maturity Level | Features |
|---|---|
| **Production-ready** | Auth/tenancy, RBAC, Shopify/Google/Meta/TikTok data sources, AI insights/recommendations/actions, custom dashboards, dashboard sharing/versioning, billing (free tier), team management, agency access, audit logging, changelog, sync health, dbt pipeline, CI/CD |
| **Functional but incomplete** | Billing (paid tiers need real Shopify store), dashboard wizard (save-as-template is TODO), settings page (placeholder tabs), notifications (infrastructure exists, worker not deployed) |
| **Infrastructure-ready, not deployed** | Superset embedded analytics, Redis caching, background workers, cron jobs |
| **Stub / catalog-only** | Attentive, Klaviyo, Shopify Email OAuth connectors |

---

## Verification Commands

```bash
# Check which OAuth platforms have backend handlers
grep -n "platform ==" backend/src/api/routes/sources.py | head -20

# Check plans and pricing
python3 -c "import psycopg2, os; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(); cur.execute('SELECT name, display_name, price_monthly_cents FROM plans WHERE is_active=true'); print(cur.fetchall()); conn.close()"

# Test an API endpoint returns real data
curl -s https://app.markinsight.net/api/sources/catalog -H "Authorization: Bearer <token>" | python3 -m json.tool

# Check Superset deployment status
grep -A2 "superset" render.yaml
```
