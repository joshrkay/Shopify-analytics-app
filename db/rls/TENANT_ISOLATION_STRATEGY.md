# Tenant Isolation Strategy

## Architecture

MarkInsight uses a **defense-in-depth** approach to tenant data isolation
with two independent enforcement layers:

### Layer 1: Application-Level TenantGuard (Primary)

All API requests pass through `TenantContextMiddleware` which:

1. Extracts tenant identity from the Clerk JWT (`org_id` claim)
2. Resolves the Clerk org_id to an internal `Tenant.id` via `_resolve_tenant_from_db`
3. Enforces authorization via `TenantGuard.enforce_authorization()`
4. Injects `tenant_id` into every database query via the request context

**Scope:** All tables, all schemas, all queries.

Every route handler calls `get_tenant_context(request)` which returns the
validated tenant_id. All SQL queries filter by this tenant_id.

### Layer 2: PostgreSQL Row-Level Security (Defense-in-Depth)

RLS policies are enforced at the database level on `raw.*` tables:

- `raw.raw_shopify_orders`
- `raw.raw_meta_ads_insights`
- `raw.raw_google_ads_campaigns`
- `raw.raw_shopify_customers`
- `raw.raw_shopify_products`
- `raw.raw_pipeline_runs`

RLS uses `SET app.tenant_id` session variable and `FORCE ROW LEVEL SECURITY`
to prevent even superuser bypass. See `db/rls/raw_rls.sql`.

### Why RLS is Only on Raw Tables

**Canonical, analytics, semantic, and marts tables** (created by dbt) do NOT
have RLS policies. This is intentional for the MVP:

1. **dbt model ownership**: dbt creates and manages these tables. Adding RLS
   policies requires coordination with dbt's `post_hook` lifecycle and
   careful handling of `CREATE TABLE AS SELECT` (which drops and recreates
   tables, removing RLS policies each run).

2. **Application enforcement is sufficient**: All queries against dbt tables
   go through the FastAPI backend, which always filters by `tenant_id` from
   the authenticated JWT. There is no direct SQL access to these tables.

3. **Performance impact**: RLS adds overhead to every query. For
   pre-aggregated marts tables, the application-level filter is equivalent
   and faster.

### When to Extend RLS

Consider adding RLS to canonical/marts tables when:

- Direct SQL access is granted (e.g., Superset, BI tools, data exports)
- A security audit requires database-level isolation beyond application logic
- Multi-tenant Superset embedding goes live (Superset queries bypass FastAPI)

### Verification

```bash
# Verify raw RLS is enforced
PYTHONPATH=. pytest src/tests/platform/test_raw_rls.py -v

# Verify application-level tenant isolation
PYTHONPATH=. pytest src/tests/platform/test_tenant_isolation.py -v
```
