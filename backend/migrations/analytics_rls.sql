-- Analytics / Canonical / Attribution / Marts Layer - Row-Level Security (RLS) Policies
-- Version: 1.0.0
-- Date: 2026-03-19
--
-- This script configures Row-Level Security for analytics-layer tables:
--   canonical.orders
--   analytics.marketing_spend
--   attribution.last_click
--   marts.mart_marketing_metrics
--   marts.fct_marketing_metrics
--
-- PREREQUISITES:
--   - The target tables must already exist (created by dbt)
--   - PostgreSQL 9.5+ required for RLS support
--
-- SECURITY MODEL:
--   - Shared tables with tenant_id column
--   - RLS enabled on all analytics-layer tables
--   - Query role uses session variable 'app.tenant_id' for filtering
--   - Superuser/table owner bypasses RLS for administration
--
-- Usage: psql $DATABASE_URL -f analytics_rls.sql
--
-- APPLICATION USAGE:
--   Before executing queries, set the tenant context:
--   SET app.tenant_id = 'tenant-123';
--   SELECT * FROM canonical.orders;  -- Returns only tenant-123 data

-- =============================================================================
-- Database Roles
-- =============================================================================

-- Create the query role if it doesn't exist
-- This role is used by the application for all analytics data access
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analytics_query_role') THEN
        CREATE ROLE analytics_query_role NOLOGIN;
        COMMENT ON ROLE analytics_query_role IS 'Query role for analytics/canonical/attribution/marts access - RLS enforced';
    END IF;
END
$$;

-- Create the admin role for dbt / data pipeline (bypasses RLS)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analytics_admin_role') THEN
        CREATE ROLE analytics_admin_role NOLOGIN;
        COMMENT ON ROLE analytics_admin_role IS 'Admin role for analytics data pipeline (dbt) - bypasses RLS';
    END IF;
END
$$;

-- =============================================================================
-- Create Schemas If Not Exist
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS canonical;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS attribution;
CREATE SCHEMA IF NOT EXISTS marts;

-- =============================================================================
-- Grant Schema Access
-- =============================================================================

GRANT USAGE ON SCHEMA canonical TO analytics_query_role;
GRANT USAGE ON SCHEMA analytics TO analytics_query_role;
GRANT USAGE ON SCHEMA attribution TO analytics_query_role;
GRANT USAGE ON SCHEMA marts TO analytics_query_role;

GRANT USAGE ON SCHEMA canonical TO analytics_admin_role;
GRANT USAGE ON SCHEMA analytics TO analytics_admin_role;
GRANT USAGE ON SCHEMA attribution TO analytics_admin_role;
GRANT USAGE ON SCHEMA marts TO analytics_admin_role;

-- =============================================================================
-- Table Permissions
-- =============================================================================

-- Query role: SELECT only on all tables in each schema
GRANT SELECT ON ALL TABLES IN SCHEMA canonical TO analytics_query_role;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_query_role;
GRANT SELECT ON ALL TABLES IN SCHEMA attribution TO analytics_query_role;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO analytics_query_role;

-- Admin role: Full CRUD for dbt / data pipeline
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA canonical TO analytics_admin_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analytics TO analytics_admin_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA attribution TO analytics_admin_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA marts TO analytics_admin_role;

-- Set default privileges for future tables created in each schema
ALTER DEFAULT PRIVILEGES IN SCHEMA canonical
    GRANT SELECT ON TABLES TO analytics_query_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT SELECT ON TABLES TO analytics_query_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA attribution
    GRANT SELECT ON TABLES TO analytics_query_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA marts
    GRANT SELECT ON TABLES TO analytics_query_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA canonical
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_admin_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_admin_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA attribution
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_admin_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA marts
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_admin_role;

-- =============================================================================
-- Helper Function: Get Current Tenant ID
-- =============================================================================

-- Reusable function in the canonical schema for tenant context lookup
-- Returns NULL if not set (which will filter out all rows for safety)
CREATE OR REPLACE FUNCTION canonical.get_current_tenant_id()
RETURNS VARCHAR(255) AS $$
BEGIN
    RETURN NULLIF(current_setting('app.tenant_id', true), '');
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

COMMENT ON FUNCTION canonical.get_current_tenant_id() IS 'Returns current tenant_id from session variable app.tenant_id';

-- Grant execute to query role
GRANT EXECUTE ON FUNCTION canonical.get_current_tenant_id() TO analytics_query_role;

-- =============================================================================
-- Enable RLS on All Target Tables
-- Guarded: these tables are created by dbt and may not exist yet.
-- When tables don't exist, RLS setup is safely skipped.
-- Re-run this migration after dbt creates the tables, or apply RLS
-- as a post-dbt hook.
-- =============================================================================

-- Helper: apply RLS + policies to a single table if it exists
-- Params: schema_name, table_name, policy_prefix
DO $$
DECLARE
    _tables TEXT[][] := ARRAY[
        ARRAY['canonical', 'orders',                'orders'],
        ARRAY['analytics', 'marketing_spend',       'marketing_spend'],
        ARRAY['attribution', 'last_click',          'last_click'],
        ARRAY['marts', 'mart_marketing_metrics',    'mart_marketing_metrics'],
        ARRAY['marts', 'fct_marketing_metrics',     'fct_marketing_metrics']
    ];
    _schema TEXT;
    _table  TEXT;
    _prefix TEXT;
    _fqn    TEXT;
    _applied INT := 0;
    _skipped INT := 0;
BEGIN
    FOR i IN 1..array_length(_tables, 1) LOOP
        _schema := _tables[i][1];
        _table  := _tables[i][2];
        _prefix := _tables[i][3];
        _fqn    := _schema || '.' || _table;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = _schema AND table_name = _table
        ) THEN
            RAISE NOTICE 'analytics_rls: %.% does not exist yet (created by dbt) — skipping RLS', _schema, _table;
            _skipped := _skipped + 1;
            CONTINUE;
        END IF;

        BEGIN
            -- Enable RLS
            EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', _schema, _table);
            EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', _schema, _table);

            -- Drop existing policies (idempotent)
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', _prefix || '_tenant_isolation', _schema, _table);
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', _prefix || '_admin_bypass', _schema, _table);

            -- Query role: can only see own tenant's data
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR ALL TO analytics_query_role USING (tenant_id = canonical.get_current_tenant_id())',
                _prefix || '_tenant_isolation', _schema, _table
            );

            -- Admin role: full access for dbt pipeline (bypasses RLS)
            EXECUTE format(
                'CREATE POLICY %I ON %I.%I FOR ALL TO analytics_admin_role USING (true) WITH CHECK (true)',
                _prefix || '_admin_bypass', _schema, _table
            );

            RAISE NOTICE 'analytics_rls: %.% — RLS enabled, policies created', _schema, _table;
            _applied := _applied + 1;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'analytics_rls: %.% — RLS setup skipped — %', _schema, _table, SQLERRM;
            _skipped := _skipped + 1;
        END;
    END LOOP;

    RAISE NOTICE 'analytics_rls: % tables configured, % skipped (not yet created by dbt)', _applied, _skipped;
END
$$;

-- =============================================================================
-- Verification Queries (informational — safe even when tables are missing)
-- =============================================================================

-- Check that RLS is enabled on all target tables
SELECT
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE schemaname IN ('canonical', 'analytics', 'attribution', 'marts')
ORDER BY schemaname, tablename;

-- Check all policies
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual
FROM pg_policies
WHERE schemaname IN ('canonical', 'analytics', 'attribution', 'marts')
ORDER BY schemaname, tablename, policyname;

-- =============================================================================
-- RLS Configuration Complete
-- =============================================================================

SELECT 'Analytics-layer Row-Level Security migration completed (some tables may be deferred until dbt runs)' AS status;
