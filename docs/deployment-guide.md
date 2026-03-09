# Deployment Guide — MarkInsight (Shopify Analytics App)

This guide covers deploying the full MarkInsight stack to Render.com using the `render.yaml` blueprint.

---

## Architecture Overview

The production stack consists of:

| Service | Type | Purpose |
|---------|------|---------|
| `markinsight-api` | Web | FastAPI backend + bundled React frontend |
| `markinsight-worker` | Worker | Polls DB for sync jobs, runs Airbyte syncs + dbt transforms |
| `markinsight-sync-scheduler` | Cron (*/15 min) | Dispatches sync jobs for connections due |
| `markinsight-reconcile-subscriptions` | Cron (hourly :00) | Reconciles Shopify billing state |
| `markinsight-dbt-incremental` | Cron (hourly :30) | Safety-net dbt incremental transforms |
| `markinsight-redis` | Redis | OAuth state, sync settings cache |
| `markinsight-db` | PostgreSQL 15 | Primary database |

---

## Prerequisites

Before deploying to Render, set up these external services and have their credentials ready.

### 1. Clerk (Authentication)

1. Create an organization at https://dashboard.clerk.com
2. Note your **Clerk Frontend API URL** (e.g., `https://your-app.clerk.accounts.dev` or custom domain `https://clerk.yourdomain.com`)
3. Copy your **Secret Key** (`sk_live_*`) from API Keys
4. Copy your **Publishable Key** (`pk_live_*`) from API Keys
5. Set up a webhook endpoint (configure after first deploy):
   - URL: `https://<your-domain>/api/webhooks/clerk`
   - Events: `user.created`, `user.updated`, `organization.created`, `organizationMembership.created`
   - Copy the **Signing Secret** for `CLERK_WEBHOOK_SECRET`

### 2. Shopify Partner App

1. Create a custom app in the [Shopify Partner Dashboard](https://partners.shopify.com)
2. Set **App URL**: `https://<your-domain>`
3. Set **Allowed redirection URLs**: `https://<your-domain>/api/shopify/oauth/callback`
4. Copy `SHOPIFY_API_KEY` and `SHOPIFY_API_SECRET`
5. Required scopes: `read_orders`, `read_products`, `read_customers`, `write_billing_charges`

### 3. Airbyte (Data Ingestion)

**Option A — Airbyte Cloud:**
- Create workspace at https://cloud.airbyte.com
- Generate API token (Settings > API Tokens)
- Set `AIRBYTE_BASE_URL=https://api.airbyte.com/v1`
- Set `AIRBYTE_API_TOKEN=<token>`

**Option B — Airbyte OSS (self-hosted):**
- Deploy Airbyte OSS on a separate VM/container
- Set `AIRBYTE_BASE_URL=http://<host>:8006/v1`
- Set `AIRBYTE_USERNAME` + `AIRBYTE_PASSWORD` (basic auth)

### 4. OpenRouter (AI/LLM)

- Create account at https://openrouter.ai
- Generate API key
- Set `OPENROUTER_API_KEY=<key>`

### 5. Encryption Key

Generate a 32-byte base64 key for encrypting secrets at rest:

```bash
openssl rand -base64 32
```

### 6. Ad Platform OAuth Apps (optional — per platform you want to support)

| Platform | Developer Portal | Env Vars |
|----------|-----------------|----------|
| Meta (Facebook) | https://developers.facebook.com | `META_APP_ID`, `META_APP_SECRET` |
| Google Ads | https://console.cloud.google.com | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_ADS_DEVELOPER_TOKEN` |
| TikTok | https://developer.tiktok.com | `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET` |
| Snapchat | https://business.snapchat.com | `SNAPCHAT_CLIENT_ID`, `SNAPCHAT_CLIENT_SECRET` |
| Pinterest | https://developers.pinterest.com | `PINTEREST_APP_ID`, `PINTEREST_APP_SECRET` |
| Twitter/X | https://developer.twitter.com | `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET` |

Set OAuth redirect URI on each platform to: `https://<your-domain>/api/sources/oauth/callback`

---

## Deploying to Render

### Step 1: Connect Repository

1. Sign in to https://dashboard.render.com
2. Go to **Blueprints** > **New Blueprint Instance**
3. Connect your GitHub repository
4. Select the branch `main`
5. Render detects `render.yaml` and shows the services to create

### Step 2: Set Environment Variables

Render auto-populates `DATABASE_URL`, `REDIS_URL`, and `DB_*` variables from managed services.

You must manually set these in the Render dashboard (under each service's **Environment** tab):

**Required (app won't function without these):**

| Variable | Where to Set | Notes |
|----------|-------------|-------|
| `CLERK_FRONTEND_API` | Web + Worker + Crons | Clerk domain URL |
| `CLERK_SECRET_KEY` | Web + Worker + Reconcile | Backend auth operations |
| `VITE_CLERK_PUBLISHABLE_KEY` | Web only | Baked into frontend at build time |
| `ENCRYPTION_KEY` | Web + Worker + Reconcile | `openssl rand -base64 32` |

**Required for Shopify integration:**

| Variable | Where to Set |
|----------|-------------|
| `SHOPIFY_API_KEY` | Web + Worker + Reconcile |
| `SHOPIFY_API_SECRET` | Web + Worker + Reconcile |

**Required for AI features:**

| Variable | Where to Set |
|----------|-------------|
| `OPENROUTER_API_KEY` | Web + Worker + Reconcile |

**Required for data ingestion:**

| Variable | Where to Set |
|----------|-------------|
| `AIRBYTE_BASE_URL` | Worker |
| `AIRBYTE_API_TOKEN` | Worker |

**Optional (ad platform OAuth):**

Set on the **Web** service only: `META_APP_ID`, `META_APP_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_ADS_DEVELOPER_TOKEN`, `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET`, `SNAPCHAT_CLIENT_ID`, `SNAPCHAT_CLIENT_SECRET`, `PINTEREST_APP_ID`, `PINTEREST_APP_SECRET`, `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET`

### Step 3: Deploy

1. Click **Apply** on the Blueprint page
2. Render creates all services, database, and Redis
3. First deploy takes ~3-5 minutes (Docker build + migrations)
4. Watch the **markinsight-api** deploy logs for:
   - `Running required migrations` — migration runner executing
   - `Required migrations completed` — all migrations applied
   - `Uvicorn running on http://0.0.0.0:10000` — app is serving

### Step 4: Custom Domain (optional)

1. In Render > markinsight-api > **Settings** > **Custom Domains**
2. Add your domain (e.g., `app.markinsight.net`)
3. Create a CNAME record in your DNS provider pointing to Render's provided target
4. Render auto-provisions an SSL certificate
5. Update `CORS_ORIGINS` if using a different domain than `app.markinsight.net`
6. Update `SHOPIFY_BILLING_RETURN_URL` and `OAUTH_REDIRECT_URI` accordingly

---

## Post-Deployment Configuration

### Register Webhooks

After the first successful deploy:

1. **Clerk webhook:**
   - Clerk Dashboard > Webhooks > Add Endpoint
   - URL: `https://<your-domain>/api/webhooks/clerk`
   - Copy signing secret → set `CLERK_WEBHOOK_SECRET` in Render
   - Click "Test" to verify delivery

2. **Shopify webhook:**
   - Shopify Partner Dashboard > App > Webhooks
   - URL: `https://<your-domain>/api/webhooks/shopify`
   - Topics: `app/uninstalled`, `subscription_billing_attempts/*`

### Verify Deployment

Run the smoke test script against your deployment:

```bash
./scripts/smoke-test.sh https://<your-domain>
```

Or manually:

```bash
# Health check (no auth required)
curl -s https://<your-domain>/health
# Expected: {"status":"ok","timestamp":"..."}

# Frontend loads
curl -s -o /dev/null -w "%{http_code}" https://<your-domain>/
# Expected: 200

# Auth enforcement
curl -s -o /dev/null -w "%{http_code}" https://<your-domain>/api/billing/entitlements
# Expected: 401 or 403

# Check migrations applied (via Render Shell)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM schema_migrations;"
# Expected: 31+ rows
```

---

## Environment-Specific URLs

| Environment | URL | Notes |
|------------|-----|-------|
| **Production** | `https://app.markinsight.net` | Auto-deploys from `main` |
| **Render default** | `https://markinsight-api.onrender.com` | If no custom domain |
| **Local (frontend)** | `http://localhost:3000` | Vite dev server |
| **Local (API)** | `http://localhost:8000` | FastAPI + Swagger at `/docs` |
| **Local (Superset)** | `http://localhost:8088` | Embedded analytics |

---

## How Deploys Work

Every push to `main` triggers an auto-deploy:

1. **Docker build** (~2-3 min) — 2-stage: frontend Vite build → Python backend image
2. **Migration runner** — `run_required_migrations.py` executes before uvicorn starts. Idempotent; skips already-applied migrations.
3. **Uvicorn starts** — Health check at `/health` confirms readiness
4. **Workers/Crons restart** — Worker and cron services rebuild and restart with the same image

### Adding a Database Migration

1. Create a `.sql` file in `backend/migrations/`
2. Add the filename to `MIGRATIONS` list in `backend/scripts/run_required_migrations.py`
3. Push to `main` — the migration runner applies it on next deploy

---

## CI Pipeline (Required Before Merge)

All 4 jobs must pass before a PR can merge to `main`:

1. **Quality Gates** — Platform gate + tenant isolation tests
2. **dbt Validation** — Compile, build, and test all dbt models
3. **Platform Tests** — Full platform test suite with coverage
4. **Billing Regression** — Checkout, webhooks, RLS isolation tests

Run locally before pushing:

```bash
cd backend
PYTHONPATH=. pytest src/tests/platform/test_platform_gate.py -v --tb=short
```

---

## Troubleshooting

### App returns 503 on all protected endpoints

**Cause:** `CLERK_FRONTEND_API` is not set or the JWKS endpoint is unreachable.
**Fix:** Set `CLERK_FRONTEND_API` in Render env vars and redeploy.

### Frontend shows blank page or "Unexpected token '<'"

**Cause:** API calls missing `/api` prefix, so Vite SPA fallback returns HTML.
**Fix:** Ensure all frontend API URLs use `${API_BASE_URL}/api/...`.

### Migrations fail on deploy

**Cause:** A required `.sql` file is missing from `backend/migrations/`.
**Fix:** Check the error in deploy logs, ensure the file exists, and redeploy.

### 403 TENANT_NOT_PROVISIONED

**Cause:** SQLAlchemy enum columns missing `values_callable`, causing silent rollback of identity table inserts.
**Fix:** Ensure every `Enum()` column includes `values_callable=lambda enum_cls: [e.value for e in enum_cls]`.

### Worker not processing sync jobs

**Cause:** `AIRBYTE_BASE_URL` or credentials not set on the worker service.
**Fix:** Set Airbyte env vars on `markinsight-worker` in Render and restart.

---

## Local Development

For local development with Docker:

```bash
# Start everything
./scripts/start-local.sh

# View logs
./scripts/start-local.sh --logs

# Stop
./scripts/start-local.sh --stop

# Reset database
./scripts/start-local.sh --reset
```

Or run backend/frontend separately for faster iteration:

```bash
# Terminal 1: Backend
cd backend && make install && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm install && npm run dev
```
