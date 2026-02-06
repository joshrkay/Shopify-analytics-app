# Superset Tenant Isolation Architecture

> Operator reference for the multi-tenant Superset analytics deployment.
> Covers security architecture, RLS enforcement, embedding, performance limits,
> and failure modes.

## 1. Why Single-Instance Multi-Tenant is Safe

The analytics layer uses a **single Superset instance** serving all tenants.
This is safe because of **defense in depth** — four independent layers each
prevent data leakage:

```
Layer 1: JWT Authentication (deny-by-default)
    ↓ every request must carry a valid JWT
Layer 2: Row-Level Security (RLS)
    ↓ SQL WHERE clauses injected per-tenant
Layer 3: Explore Guardrails
    ↓ query complexity and date range limits
Layer 4: Dataset Column Allow-Lists
    ↓ only YAML-defined columns are exposed
```

**Key invariant:** If any single layer fails, the others still prevent
cross-tenant data access. The worst case for a single-layer failure is
denial of service (empty data), not data leakage.

### Why not one Superset instance per tenant?

- Cost: Each Superset instance requires ~512MB RAM + metadata DB
- Operational: N instances means N deployments, N upgrades, N monitoring targets
- Unnecessary: RLS provides database-level isolation within a shared instance

## 2. How RLS Works

### Jinja Template Evaluation

RLS rules are defined as Jinja templates that evaluate against the current
user's JWT claims (set in Flask `g` context by `jwt_auth.py`):

```sql
-- Single-tenant merchant
WHERE tenant_id = '{{ current_user.tenant_id }}'

-- Agency user with multiple tenants
WHERE tenant_id IN {{ current_user.allowed_tenants | tojson }}
```

### Role-Based RLS Clauses

| User Role     | RLS Clause                                           | Effect                          |
|---------------|------------------------------------------------------|---------------------------------|
| Merchant      | `tenant_id = '{{ current_user.tenant_id }}'`         | See only own data               |
| Agency        | `tenant_id IN ({{ allowed_tenants | tojson }})`       | See managed tenants only        |
| Super Admin   | `1=1`                                                | See all data (operations only)  |

### Deny-by-Default

Any dataset without an explicit RLS rule gets `WHERE 1=0` (returns zero rows).
This is enforced by `rls_rules.py:enforce_deny_by_default()` at startup.

**Protected datasets:**
- `fact_orders`
- `fact_marketing_spend`
- `fact_campaign_performance`

### How RLS is Applied

1. JWT decoded → `g.user` (EmbedUser) set with `tenant_id`, `allowed_tenants`
2. Superset query engine detects RLS rules for the target dataset
3. Jinja template evaluates against `current_user` (= `g.user`)
4. WHERE clause injected into generated SQL
5. Database executes query with tenant filter

## 3. How Embedding Works

### Token Flow

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐
│  Shopify Admin   │     │   Backend    │     │   Superset    │
│  (iframe host)   │     │  (FastAPI)   │     │  (Dashboard)  │
└────────┬────────┘     └──────┬───────┘     └───────┬───────┘
         │                      │                      │
         │  1. Request embed    │                      │
         │─────────────────────>│                      │
         │                      │                      │
         │  2. Generate JWT     │                      │
         │     (EmbedTokenSvc)  │                      │
         │<─────────────────────│                      │
         │                      │                      │
         │  3. Load iframe with token                  │
         │─────────────────────────────────────────────>│
         │                      │                      │
         │                      │  4. Verify JWT       │
         │                      │     (jwt_auth.py)    │
         │                      │                      │
         │  5. Render dashboard │  6. Query with RLS   │
         │<─────────────────────────────────────────────│
```

### CSP Enforcement

Content Security Policy restricts which domains can embed Superset:

```
Content-Security-Policy: frame-ancestors 'self' https://admin.shopify.com
```

This prevents loading Superset in iframes on unauthorized domains.

### Session Refresh

The `TokenRefreshManager` (frontend) automatically refreshes JWT tokens
before they expire:

1. Token issued with 60-minute max lifetime
2. Refresh triggered at 50% remaining lifetime (30 min)
3. On refresh failure, user sees expiration warning
4. On expiration, iframe shows re-authentication prompt

### Token Extraction Priority

`jwt_auth.py:extract_token_from_request()` checks in order:
1. `Authorization: Bearer <token>` header
2. `X-GuestToken` header (Superset embedded SDK convention)
3. `?token=` query parameter (initial dashboard load)

## 4. Common Failure Modes

### 401 on All Requests

**Symptom:** Every Superset request returns 401 Unauthorized.

**Causes:**
1. `SUPERSET_JWT_SECRET_CURRENT` env var not set
2. JWT secret mismatch between backend and Superset
3. All tokens expired (clock skew > 60 minutes)

**Resolution:**
- Check startup guards log: `Guard [jwt_secret]: FAIL`
- Verify env var: `echo $SUPERSET_JWT_SECRET_CURRENT`
- Compare with backend's `EMBED_TOKEN_SECRET`

### Empty Data (All Queries Return Zero Rows)

**Symptom:** Dashboard loads but charts show "No data."

**Causes:**
1. RLS deny-by-default active (`WHERE 1=0`)
2. `tenant_id` in JWT doesn't match any data
3. New dataset added without RLS rule

**Resolution:**
- Check startup guards: `Guard [rls_enforcement]: WARN`
- Verify JWT claims: decode token and check `tenant_id`
- Check `ALL_DATASETS_REQUIRING_RLS` in `rls_rules.py`

### New Dataset Blocked

**Symptom:** New dataset added but returns no data for all users.

**Expected behavior:** This is correct! Deny-by-default blocks unprotected
datasets. To enable a new dataset:

1. Add YAML config to `datasets/` with RLS enabled
2. Add table name to `ALL_DATASETS_REQUIRING_RLS` in `rls_rules.py`
3. Run `enforce_deny_by_default()` to apply
4. Deploy and verify

### Startup Guards Failing

**Symptom:** Log line: `STARTUP GUARDS FAILED — Superset may not be safe`

**Resolution:** Check individual guard results:
- `jwt_secret`: Set `SUPERSET_JWT_SECRET_CURRENT` (min 32 chars)
- `metadata_db`: Set `SUPERSET_METADATA_DB_URI`
- `perf_limits`: Ensure `performance_config.py` is deployed
- `feature_flags`: Verify `SAFETY_FEATURE_FLAGS` all False
- `rls_enforcement`: Ensure `rls_rules.py` is deployed with datasets

### Cross-Tenant Access Blocked

**Symptom:** 401 with audit log `analytics.cross_tenant.blocked`

**Cause:** JWT `tenant_id` is not in `allowed_tenants` list.

**Resolution:** This is expected security behavior. Check:
- Backend `EmbedTokenService` is setting `allowed_tenants` correctly
- For agency users, verify all managed tenants are in the list

## 5. Performance Limits

All limits are defined in `performance_config.py` (single source of truth).

| Guardrail              | Value       | Enforcement Point              |
|------------------------|-------------|--------------------------------|
| Max date range         | 90 days     | ExplorePermissionValidator     |
| Query timeout          | 20 seconds  | SQLLAB_ASYNC_TIME_LIMIT_SEC    |
| Row limit              | 50,000      | SQL_MAX_ROW / ROW_LIMIT        |
| Max group-by dims      | 2           | ExplorePermissionValidator     |
| Max filters            | 10          | ExplorePermissionValidator     |
| Max metrics per query  | 5           | ExplorePermissionValidator     |
| Cache TTL              | 30 minutes  | DATA_CACHE_CONFIG              |
| Webserver timeout      | 30 seconds  | SUPERSET_WEBSERVER_TIMEOUT     |
| File export            | Disabled    | SAFETY_FEATURE_FLAGS           |
| CSV export             | Disabled    | SAFETY_FEATURE_FLAGS           |
| Custom SQL             | Disabled    | SAFETY_FEATURE_FLAGS           |
| Ad-hoc subqueries      | Disabled    | SAFETY_FEATURE_FLAGS           |

**Important:** These limits are enforced via a frozen dataclass. They cannot
be modified at runtime. The startup guard `check_performance_limits_frozen()`
verifies this on boot.

## 6. File Reference

### Security Files (Superset Container)

| File                          | Purpose                                    |
|-------------------------------|--------------------------------------------|
| `security/jwt_auth.py`       | JWT verification, deny-by-default auth     |
| `rls_rules.py`               | RLS Jinja templates, deny-by-default       |
| `guards.py`                  | Startup + runtime safety guards            |
| `performance_config.py`      | Frozen performance limits (single source)  |
| `explore_guardrails.py`      | Explore mode query complexity limits       |
| `superset_config.py`         | Superset configuration (imports above)     |
| `datasets/*.yaml`            | Column allow-lists, metrics, RLS config    |
| `dataset_loader.py`          | YAML parsing, PII validation, registration |

### Backend Files

| File                                   | Purpose                              |
|----------------------------------------|--------------------------------------|
| `services/embed_token_service.py`      | JWT generation for embedded access   |
| `api/routes/embed.py`                  | Embed token API endpoints            |
| `services/audit_logger.py`             | Audit event emitters                 |
| `platform/audit.py`                    | AuditAction enum, DB persistence     |
| `platform/audit_events.py`             | Event registry with required fields  |

### Frontend Files

| File                                        | Purpose                         |
|---------------------------------------------|---------------------------------|
| `components/ShopifyEmbeddedSuperset.tsx`    | Dashboard iframe component      |
| `utils/embedSession.ts`                     | Session lifecycle management    |
| `services/embedApi.ts`                      | Token refresh manager           |

## 7. Debugging Checklist

When investigating a Superset issue, work through this checklist:

### 1. Check Startup Guards
```bash
# Look for startup guard results in logs
docker logs <superset-container> | grep "Guard \["
```

### 2. Verify JWT Configuration
```bash
# Check env vars are set
docker exec <superset-container> env | grep SUPERSET_JWT
```

### 3. Test JWT Verification
```bash
# Decode a token (without verifying) to inspect claims
python3 -c "import jwt; print(jwt.decode('<token>', options={'verify_signature': False}))"
```

### 4. Check RLS Rules
```bash
# Verify datasets in RLS registry
docker exec <superset-container> python3 -c "
from rls_rules import ALL_DATASETS_REQUIRING_RLS
print(ALL_DATASETS_REQUIRING_RLS)
"
```

### 5. Verify Dataset Configs
```bash
# Validate all dataset YAML files
docker exec <superset-container> python3 -c "
from dataset_loader import DatasetLoader
loader = DatasetLoader()
loader.load_all()
valid, issues = loader.validate_all()
print(f'Valid: {valid}')
for i in issues:
    print(f'  - {i}')
"
```

### 6. Check Audit Logs
```bash
# Look for security events
docker logs <superset-container> | grep "AUDIT_EVENT"

# Look for denied access
docker logs <superset-container> | grep "access.denied"
```

### 7. Verify Performance Limits
```bash
docker exec <superset-container> python3 -c "
from performance_config import PERFORMANCE_LIMITS
print(f'Row limit: {PERFORMANCE_LIMITS.row_limit}')
print(f'Query timeout: {PERFORMANCE_LIMITS.query_timeout_seconds}s')
print(f'Date range: {PERFORMANCE_LIMITS.max_date_range_days} days')
"
```

## 8. Security Invariants

These invariants must always hold. If any is violated, Superset is unsafe:

1. **Every request requires a valid JWT** — no anonymous access
2. **Every dataset has RLS** — unprotected datasets return zero rows
3. **Performance limits are frozen** — cannot be modified at runtime
4. **Dangerous features are disabled** — no custom SQL, no exports
5. **PII columns are never exposed** — column allow-lists in YAML
6. **Cross-tenant access is blocked** — tenant_id must be in allowed_tenants
7. **Audit logs are emitted** — all access events are logged
