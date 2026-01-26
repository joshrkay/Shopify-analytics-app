-- Raw Warehouse Layer - Row-Level Security (RLS) Policies
-- Version: 1.0.0
-- Date: 2026-01-26
--
-- This script configures Row-Level Security for all raw warehouse tables.
-- RLS ensures that the query role can NEVER see data from another tenant.
--
-- PREREQUISITES:
--   - raw_schema.sql must be run first to create the tables
--   - PostgreSQL 9.5+ required for RLS support
--
-- SECURITY MODEL:
--   - Shared tables with tenant_id column
--   - RLS enabled on all raw tables
--   - Query role uses session variable 'app.tenant_id' for filtering
--   - Superuser/table owner bypasses RLS for administration
--
-- Usage: psql $DATABASE_URL -f raw_rls.sql
--
-- APPLICATION USAGE:
--   Before executing queries, set the tenant context:
--   SET app.tenant_id = 'tenant-123';
--   SELECT * FROM raw.raw_shopify_orders;  -- Returns only tenant-123 data

-- =============================================================================
-- Database Roles
-- =============================================================================

-- Create the query role if it doesn't exist
-- This role is used by the application for all data access
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'raw_query_role') THEN
        CREATE ROLE raw_query_role NOLOGIN;
        COMMENT ON ROLE raw_query_role IS 'Query role for raw warehouse access - RLS enforced';
    END IF;
END
$$;

-- Create the admin role for data loading (bypasses RLS)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'raw_admin_role') THEN
        CREATE ROLE raw_admin_role NOLOGIN;
        COMMENT ON ROLE raw_admin_role IS 'Admin role for raw warehouse data loading - bypasses RLS';
    END IF;
END
$$;

-- Create the retention role for cleanup jobs (bypasses RLS)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'raw_retention_role') THEN
        CREATE ROLE raw_retention_role NOLOGIN;
        COMMENT ON ROLE raw_retention_role IS 'Retention role for raw data cleanup - bypasses RLS';
    END IF;
END
$$;

-- =============================================================================
-- Grant Schema Access
-- =============================================================================

-- Grant schema usage to roles
GRANT USAGE ON SCHEMA raw TO raw_query_role;
GRANT USAGE ON SCHEMA raw TO raw_admin_role;
GRANT USAGE ON SCHEMA raw TO raw_retention_role;

-- =============================================================================
-- Table Permissions
-- =============================================================================

-- Query role: SELECT only on all raw tables
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO raw_query_role;

-- Admin role: Full CRUD for data loading
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw TO raw_admin_role;

-- Retention role: SELECT and DELETE for cleanup
GRANT SELECT, DELETE ON ALL TABLES IN SCHEMA raw TO raw_retention_role;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA raw
    GRANT SELECT ON TABLES TO raw_query_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA raw
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO raw_admin_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA raw
    GRANT SELECT, DELETE ON TABLES TO raw_retention_role;

-- =============================================================================
-- Helper Function: Get Current Tenant ID
-- =============================================================================

-- Function to get current tenant from session variable
-- Returns NULL if not set (which will filter out all rows for safety)
CREATE OR REPLACE FUNCTION raw.get_current_tenant_id()
RETURNS VARCHAR(255) AS $$
BEGIN
    RETURN NULLIF(current_setting('app.tenant_id', true), '');
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

COMMENT ON FUNCTION raw.get_current_tenant_id() IS 'Returns current tenant_id from session variable app.tenant_id';

-- Grant execute to query role
GRANT EXECUTE ON FUNCTION raw.get_current_tenant_id() TO raw_query_role;

-- =============================================================================
-- Enable RLS on All Raw Tables
-- =============================================================================

-- raw_shopify_orders
ALTER TABLE raw.raw_shopify_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_shopify_orders FORCE ROW LEVEL SECURITY;

-- raw_meta_ads_insights
ALTER TABLE raw.raw_meta_ads_insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_meta_ads_insights FORCE ROW LEVEL SECURITY;

-- raw_google_ads_campaigns
ALTER TABLE raw.raw_google_ads_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_google_ads_campaigns FORCE ROW LEVEL SECURITY;

-- raw_shopify_customers
ALTER TABLE raw.raw_shopify_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_shopify_customers FORCE ROW LEVEL SECURITY;

-- raw_shopify_products
ALTER TABLE raw.raw_shopify_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_shopify_products FORCE ROW LEVEL SECURITY;

-- raw_pipeline_runs (tenant_id is optional - only filter when set)
ALTER TABLE raw.raw_pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw.raw_pipeline_runs FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- RLS Policies: raw_shopify_orders
-- =============================================================================

-- Drop existing policies (idempotent)
DROP POLICY IF EXISTS raw_shopify_orders_tenant_isolation ON raw.raw_shopify_orders;
DROP POLICY IF EXISTS raw_shopify_orders_admin_bypass ON raw.raw_shopify_orders;
DROP POLICY IF EXISTS raw_shopify_orders_retention_bypass ON raw.raw_shopify_orders;

-- Query role: Can only see own tenant's data
CREATE POLICY raw_shopify_orders_tenant_isolation
    ON raw.raw_shopify_orders
    FOR ALL
    TO raw_query_role
    USING (tenant_id = raw.get_current_tenant_id());

-- Admin role: Full access for data loading (bypasses RLS)
CREATE POLICY raw_shopify_orders_admin_bypass
    ON raw.raw_shopify_orders
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

-- Retention role: Full access for cleanup (bypasses RLS)
CREATE POLICY raw_shopify_orders_retention_bypass
    ON raw.raw_shopify_orders
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- RLS Policies: raw_meta_ads_insights
-- =============================================================================

DROP POLICY IF EXISTS raw_meta_ads_insights_tenant_isolation ON raw.raw_meta_ads_insights;
DROP POLICY IF EXISTS raw_meta_ads_insights_admin_bypass ON raw.raw_meta_ads_insights;
DROP POLICY IF EXISTS raw_meta_ads_insights_retention_bypass ON raw.raw_meta_ads_insights;

CREATE POLICY raw_meta_ads_insights_tenant_isolation
    ON raw.raw_meta_ads_insights
    FOR ALL
    TO raw_query_role
    USING (tenant_id = raw.get_current_tenant_id());

CREATE POLICY raw_meta_ads_insights_admin_bypass
    ON raw.raw_meta_ads_insights
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY raw_meta_ads_insights_retention_bypass
    ON raw.raw_meta_ads_insights
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- RLS Policies: raw_google_ads_campaigns
-- =============================================================================

DROP POLICY IF EXISTS raw_google_ads_campaigns_tenant_isolation ON raw.raw_google_ads_campaigns;
DROP POLICY IF EXISTS raw_google_ads_campaigns_admin_bypass ON raw.raw_google_ads_campaigns;
DROP POLICY IF EXISTS raw_google_ads_campaigns_retention_bypass ON raw.raw_google_ads_campaigns;

CREATE POLICY raw_google_ads_campaigns_tenant_isolation
    ON raw.raw_google_ads_campaigns
    FOR ALL
    TO raw_query_role
    USING (tenant_id = raw.get_current_tenant_id());

CREATE POLICY raw_google_ads_campaigns_admin_bypass
    ON raw.raw_google_ads_campaigns
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY raw_google_ads_campaigns_retention_bypass
    ON raw.raw_google_ads_campaigns
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- RLS Policies: raw_shopify_customers
-- =============================================================================

DROP POLICY IF EXISTS raw_shopify_customers_tenant_isolation ON raw.raw_shopify_customers;
DROP POLICY IF EXISTS raw_shopify_customers_admin_bypass ON raw.raw_shopify_customers;
DROP POLICY IF EXISTS raw_shopify_customers_retention_bypass ON raw.raw_shopify_customers;

CREATE POLICY raw_shopify_customers_tenant_isolation
    ON raw.raw_shopify_customers
    FOR ALL
    TO raw_query_role
    USING (tenant_id = raw.get_current_tenant_id());

CREATE POLICY raw_shopify_customers_admin_bypass
    ON raw.raw_shopify_customers
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY raw_shopify_customers_retention_bypass
    ON raw.raw_shopify_customers
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- RLS Policies: raw_shopify_products
-- =============================================================================

DROP POLICY IF EXISTS raw_shopify_products_tenant_isolation ON raw.raw_shopify_products;
DROP POLICY IF EXISTS raw_shopify_products_admin_bypass ON raw.raw_shopify_products;
DROP POLICY IF EXISTS raw_shopify_products_retention_bypass ON raw.raw_shopify_products;

CREATE POLICY raw_shopify_products_tenant_isolation
    ON raw.raw_shopify_products
    FOR ALL
    TO raw_query_role
    USING (tenant_id = raw.get_current_tenant_id());

CREATE POLICY raw_shopify_products_admin_bypass
    ON raw.raw_shopify_products
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY raw_shopify_products_retention_bypass
    ON raw.raw_shopify_products
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- RLS Policies: raw_pipeline_runs
-- Pipeline runs may or may not have tenant_id (system-wide vs tenant-specific)
-- =============================================================================

DROP POLICY IF EXISTS raw_pipeline_runs_tenant_isolation ON raw.raw_pipeline_runs;
DROP POLICY IF EXISTS raw_pipeline_runs_admin_bypass ON raw.raw_pipeline_runs;
DROP POLICY IF EXISTS raw_pipeline_runs_retention_bypass ON raw.raw_pipeline_runs;

-- Query role: Can see own tenant's runs OR runs with NULL tenant_id (system runs)
-- When app.tenant_id is not set, only NULL tenant_id records are visible
CREATE POLICY raw_pipeline_runs_tenant_isolation
    ON raw.raw_pipeline_runs
    FOR ALL
    TO raw_query_role
    USING (
        tenant_id IS NULL
        OR tenant_id = raw.get_current_tenant_id()
    );

CREATE POLICY raw_pipeline_runs_admin_bypass
    ON raw.raw_pipeline_runs
    FOR ALL
    TO raw_admin_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY raw_pipeline_runs_retention_bypass
    ON raw.raw_pipeline_runs
    FOR ALL
    TO raw_retention_role
    USING (true);

-- =============================================================================
-- Audit Table for RLS Events (Optional - for compliance)
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.raw_rls_audit_log (
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    event_type VARCHAR(50) NOT NULL,  -- 'policy_violation', 'context_missing', 'access_granted'
    attempted_tenant_id VARCHAR(255),
    actual_tenant_id VARCHAR(255),
    table_name VARCHAR(255) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    query_user VARCHAR(255) NOT NULL DEFAULT current_user,
    client_ip INET,
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    details JSONB
);

CREATE INDEX IF NOT EXISTS idx_raw_rls_audit_log_timestamp
    ON raw.raw_rls_audit_log(event_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_raw_rls_audit_log_tenant
    ON raw.raw_rls_audit_log(attempted_tenant_id);

COMMENT ON TABLE raw.raw_rls_audit_log IS 'Audit log for RLS policy events - used for security monitoring';

-- Admin role needs to write audit logs
GRANT INSERT ON raw.raw_rls_audit_log TO raw_query_role;
GRANT SELECT, INSERT, DELETE ON raw.raw_rls_audit_log TO raw_admin_role;
GRANT SELECT, DELETE ON raw.raw_rls_audit_log TO raw_retention_role;

-- =============================================================================
-- Verification Queries (Run these to validate RLS is working)
-- =============================================================================

-- Check that RLS is enabled on all tables
SELECT
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE schemaname = 'raw'
ORDER BY tablename;

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
WHERE schemaname = 'raw'
ORDER BY tablename, policyname;

-- =============================================================================
-- RLS Configuration Complete
-- =============================================================================

SELECT 'Row-Level Security policies configured successfully' AS status;
SELECT 'IMPORTANT: Application must SET app.tenant_id before querying' AS usage_note;
