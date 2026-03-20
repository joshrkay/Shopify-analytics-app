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
-- =============================================================================

-- canonical.orders
ALTER TABLE canonical.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical.orders FORCE ROW LEVEL SECURITY;

-- analytics.marketing_spend
ALTER TABLE analytics.marketing_spend ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics.marketing_spend FORCE ROW LEVEL SECURITY;

-- attribution.last_click
ALTER TABLE attribution.last_click ENABLE ROW LEVEL SECURITY;
ALTER TABLE attribution.last_click FORCE ROW LEVEL SECURITY;

-- marts.mart_marketing_metrics
ALTER TABLE marts.mart_marketing_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE marts.mart_marketing_metrics FORCE ROW LEVEL SECURITY;

-- marts.fct_marketing_metrics
ALTER TABLE marts.fct_marketing_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE marts.fct_marketing_metrics FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- RLS Policies: canonical.orders
-- =============================================================================

-- Drop existing policies (idempotent)
DROP POLICY IF EXISTS orders_tenant_isolation ON canonical.orders;
DROP POLICY IF EXISTS orders_admin_bypass ON canonical.orders;

-- Query role: Can only see own tenant's data
CREATE POLICY orders_tenant_isolation
    ON canonical.orders
    FOR ALL
    TO analytics_query_role
    USING (tenant_id = canonical.get_current_tenant_id());

-- Admin role: Full access for dbt pipeline (bypasses RLS)
CREATE POLICY orders_admin_bypass
    ON canonical.orders
    FOR ALL
    TO analytics_admin_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- RLS Policies: analytics.marketing_spend
-- =============================================================================

DROP POLICY IF EXISTS marketing_spend_tenant_isolation ON analytics.marketing_spend;
DROP POLICY IF EXISTS marketing_spend_admin_bypass ON analytics.marketing_spend;

CREATE POLICY marketing_spend_tenant_isolation
    ON analytics.marketing_spend
    FOR ALL
    TO analytics_query_role
    USING (tenant_id = canonical.get_current_tenant_id());

CREATE POLICY marketing_spend_admin_bypass
    ON analytics.marketing_spend
    FOR ALL
    TO analytics_admin_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- RLS Policies: attribution.last_click
-- =============================================================================

DROP POLICY IF EXISTS last_click_tenant_isolation ON attribution.last_click;
DROP POLICY IF EXISTS last_click_admin_bypass ON attribution.last_click;

CREATE POLICY last_click_tenant_isolation
    ON attribution.last_click
    FOR ALL
    TO analytics_query_role
    USING (tenant_id = canonical.get_current_tenant_id());

CREATE POLICY last_click_admin_bypass
    ON attribution.last_click
    FOR ALL
    TO analytics_admin_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- RLS Policies: marts.mart_marketing_metrics
-- =============================================================================

DROP POLICY IF EXISTS mart_marketing_metrics_tenant_isolation ON marts.mart_marketing_metrics;
DROP POLICY IF EXISTS mart_marketing_metrics_admin_bypass ON marts.mart_marketing_metrics;

CREATE POLICY mart_marketing_metrics_tenant_isolation
    ON marts.mart_marketing_metrics
    FOR ALL
    TO analytics_query_role
    USING (tenant_id = canonical.get_current_tenant_id());

CREATE POLICY mart_marketing_metrics_admin_bypass
    ON marts.mart_marketing_metrics
    FOR ALL
    TO analytics_admin_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- RLS Policies: marts.fct_marketing_metrics
-- =============================================================================

DROP POLICY IF EXISTS fct_marketing_metrics_tenant_isolation ON marts.fct_marketing_metrics;
DROP POLICY IF EXISTS fct_marketing_metrics_admin_bypass ON marts.fct_marketing_metrics;

CREATE POLICY fct_marketing_metrics_tenant_isolation
    ON marts.fct_marketing_metrics
    FOR ALL
    TO analytics_query_role
    USING (tenant_id = canonical.get_current_tenant_id());

CREATE POLICY fct_marketing_metrics_admin_bypass
    ON marts.fct_marketing_metrics
    FOR ALL
    TO analytics_admin_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- Verification Queries (Run these to validate RLS is working)
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

SELECT 'Analytics-layer Row-Level Security policies configured successfully' AS status;
SELECT 'IMPORTANT: Application must SET app.tenant_id before querying' AS usage_note;
