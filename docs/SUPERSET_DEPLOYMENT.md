# Superset Deployment Guide

Production deployment guide for Apache Superset in the MarkInsight multi-tenant analytics platform.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ Shopify Admin (iframe)                                   │
│   └── Embedded Dashboard (standalone=1)                  │
│         ├── Token: Authorization: Bearer <embed_jwt>     │
│         └── CSP: frame-ancestors admin.shopify.com       │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│ Backend API (FastAPI)                                    │
│   ├── /api/v1/embed/token    → EmbedTokenService         │
│   ├── /api/v1/embed/refresh  → Token refresh             │
│   └── JWT: HS256, 60-min lifetime                        │
│         Claims: sub, tenant_id, roles, allowed_tenants,  │
│                 billing_tier, rls_filter                  │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│ Apache Superset (3.0.1)                                  │
│   ├── JWT verification (security/jwt_auth.py)            │
│   ├── RLS enforcement (rls_rules.py)                     │
│   │     ├── Merchant: tenant_id = 'X'                    │
│   │     ├── Agency:   tenant_id IN ('X', 'Y', 'Z')      │
│   │     └── Default:  1=0 (deny)                         │
│   ├── Metadata DB: superset_metadata (PostgreSQL)        │
│   └── Cache: Redis (db 1)                                │
└──────────────────────────────────────────────────────────┘
```

## Non-Negotiable Security Principles

1. **Superset is NOT the auth system** — it only verifies embed JWTs
2. **Superset is NOT the source of truth for permissions** — roles come from JWT claims
3. **Superset never sees raw secrets** — only signed JWT claims
4. **All access is mediated by JWT + RLS** — no login forms, no direct access
5. **Deny by default** — missing token = 401, missing RLS = `1=0`

## Deployment Modes

### Local Development

```bash
# Start all services (Postgres, Redis, Superset, API, Frontend)
docker-compose up -d

# Superset available at http://localhost:8088
# Health check: http://localhost:8088/health
```

**Local environment variables** (set in docker-compose.yml):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUPERSET_SECRET_KEY` | `superset-secret-key-for-local-dev-only` | Flask secret key |
| `SUPERSET_METADATA_DB_URI` | `postgresql://...@postgres:5432/superset_metadata` | Metadata DB |
| `SUPERSET_JWT_SECRET_CURRENT` | `test-jwt-secret-for-dev` | JWT verification secret |
| `REDIS_URL` | `redis://redis:6379/1` | Cache (db 1, separate from backend) |
| `TALISMAN_ENABLED` | `false` | HTTPS disabled for local dev |

### Production (Render)

Production deployment is defined in `render.yaml`. The Superset service:

- Runs on a **standard** plan (requires more memory than starter)
- Uses a **separate PostgreSQL database** for metadata (`markinsight-superset-db`)
- Shares the Redis instance but uses a different database number
- Has HTTPS/HSTS enforced via Talisman

**Required secrets** (set in Render dashboard, `sync: false`):

| Secret | How to Generate |
|--------|----------------|
| `SUPERSET_SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SUPERSET_JWT_SECRET_CURRENT` | Same as backend's `SUPERSET_JWT_SECRET` |
| `SUPERSET_JWT_SECRET_PREVIOUS` | Set only during key rotation |

## Metadata Database

Superset uses a **separate PostgreSQL database** (`superset_metadata`) from the application database (`markinsight`). This provides:

- **Isolation**: Superset schema changes don't affect app data
- **Independent backups**: Can restore Superset state without affecting application
- **Security boundary**: Superset never has access to raw tenant data tables

In local dev, the `db/migrations/000_create_superset_db.sql` init script creates this database automatically.

## JWT Authentication Flow

1. User opens embedded dashboard in Shopify Admin
2. Frontend requests embed token from backend API (`POST /api/v1/embed/token`)
3. Backend verifies Clerk JWT, builds `TenantContext`, generates embed JWT via `EmbedTokenService`
4. Frontend loads Superset dashboard with embed JWT in `Authorization: Bearer` header
5. Superset's `authenticate_embed_request()` verifies the HS256 token
6. On success, sets `g.user` (EmbedUser) with `tenant_id`, `allowed_tenants`, `roles`
7. RLS templates evaluate against `current_user.tenant_id` / `current_user.allowed_tenants`

### Token Lifecycle

- **Lifetime**: 60 minutes (max enforced by Superset)
- **Refresh**: Client refreshes when < 5 minutes remain
- **Grace period**: Backend allows refresh up to 10 minutes after expiry
- **Key rotation**: Set `SUPERSET_JWT_SECRET_PREVIOUS` to old secret, update `SUPERSET_JWT_SECRET_CURRENT`

## Row-Level Security (RLS)

### Rule Types

| User Type | RLS Clause | Effect |
|-----------|-----------|--------|
| Merchant | `tenant_id = '{{ current_user.tenant_id }}'` | Single store |
| Agency | `tenant_id IN ({{ current_user.allowed_tenants }})` | Assigned stores |
| Super Admin | `1=1` | All data |
| No context | `1=0` | Zero rows (deny) |

### Protected Datasets

All datasets in `ALL_DATASETS_REQUIRING_RLS` (rls_rules.py):
- `fact_orders`, `fact_marketing_spend`, `fact_campaign_performance`
- `dim_products`, `dim_customers`, `fact_inventory`
- `fct_revenue`, `fct_roas`, `fct_aov`, `fct_cac`
- `mart_revenue_metrics`, `mart_marketing_metrics`

### Deny-by-Default Enforcement

The `enforce_deny_by_default()` function:
1. Queries Superset for all datasets
2. Queries all RLS rules
3. Any dataset without RLS gets `1=0` clause automatically
4. Logs CRITICAL alert for unprotected datasets

## Health Checks

| Endpoint | Interval | Purpose |
|----------|----------|---------|
| `GET /health` | 30s | Container health (Docker/Render) |

## Scaling Considerations

- **Workers**: 4 gunicorn workers with gevent (async I/O)
- **Connection pool**: 5 connections + 10 overflow (configurable via `SUPERSET_POOL_SIZE`)
- **Cache**: 30-minute TTL, Redis-backed
- **Query timeout**: 20 seconds (matches explore guardrails)

## Troubleshooting

### Superset won't start
- Check `SUPERSET_METADATA_DB_URI` — database must exist
- In docker-compose, ensure postgres is healthy before superset starts
- First start takes ~90s for `db upgrade` + `init`

### 401 on all requests
- Verify `SUPERSET_JWT_SECRET_CURRENT` matches backend's `SUPERSET_JWT_SECRET`
- Check token isn't expired (60-min max lifetime)
- Ensure token has required claims: `sub`, `tenant_id`, `roles`, `exp`, `iat`

### RLS not filtering data
- Verify `g.user` has `tenant_id` attribute (check jwt_auth.py logs)
- Verify RLS rules are applied to datasets in Superset admin
- Run `validate_all_datasets_have_rls()` to check coverage

### Key rotation
1. Set `SUPERSET_JWT_SECRET_PREVIOUS` = current secret
2. Set `SUPERSET_JWT_SECRET_CURRENT` = new secret
3. Update backend's `SUPERSET_JWT_SECRET` to match new current
4. After all old tokens expire (60 min), clear `SUPERSET_JWT_SECRET_PREVIOUS`

## File Reference

| File | Purpose |
|------|---------|
| `docker/superset.Dockerfile` | Container build |
| `docker/superset/superset_config.py` | Superset configuration |
| `docker/superset/security/jwt_auth.py` | JWT authentication handler |
| `docker/superset/rls_rules.py` | RLS rules and deny-by-default |
| `docker/superset/explore_guardrails.py` | Query guardrails |
| `docker/superset/superset_feature_flags.py` | Feature flags |
| `backend/src/services/embed_token_service.py` | Embed token generation |
| `backend/src/api/routes/embed.py` | Embed API endpoints |
