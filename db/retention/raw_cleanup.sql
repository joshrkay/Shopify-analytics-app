-- Raw Warehouse Layer - Retention Cleanup Job
-- Version: 1.0.0
-- Date: 2026-01-26
--
-- This script provides functions and procedures for purging raw data older than 13 months.
-- All deletions are audited for compliance.
--
-- RETENTION POLICY:
--   - Raw data: 13 months from extracted_at timestamp
--   - Audit logs: Retained separately per compliance requirements
--   - Pipeline runs: Same 13-month retention
--
-- SCHEDULING:
--   Option 1: pg_cron (PostgreSQL extension)
--   Option 2: External scheduler (cron, Airflow, etc.)
--
-- Usage:
--   Manual: SELECT raw.execute_retention_cleanup();
--   pg_cron: SELECT cron.schedule('raw-cleanup', '0 3 * * *', 'SELECT raw.execute_retention_cleanup()');

-- =============================================================================
-- Retention Configuration
-- =============================================================================

-- Create configuration table for retention settings
CREATE TABLE IF NOT EXISTS raw.retention_config (
    id VARCHAR(255) PRIMARY KEY DEFAULT 'default',
    retention_months INTEGER NOT NULL DEFAULT 13,
    batch_size INTEGER NOT NULL DEFAULT 10000,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Insert default configuration
INSERT INTO raw.retention_config (id, retention_months, batch_size, is_enabled)
VALUES ('default', 13, 10000, TRUE)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE raw.retention_config IS 'Configuration for raw data retention cleanup';
COMMENT ON COLUMN raw.retention_config.retention_months IS 'Data older than this many months will be purged';
COMMENT ON COLUMN raw.retention_config.batch_size IS 'Number of records to delete per batch to avoid long locks';

-- =============================================================================
-- Retention Audit Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.retention_audit_log (
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    run_id VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255),
    records_deleted BIGINT NOT NULL DEFAULT 0,
    oldest_record_date TIMESTAMP WITH TIME ZONE,
    newest_record_date TIMESTAMP WITH TIME ZONE,
    cutoff_date TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL DEFAULT 'running',  -- running, success, failed
    error_message TEXT,
    execution_time_ms BIGINT
);

CREATE INDEX IF NOT EXISTS idx_retention_audit_log_run
    ON raw.retention_audit_log(run_id);

CREATE INDEX IF NOT EXISTS idx_retention_audit_log_table
    ON raw.retention_audit_log(table_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_retention_audit_log_tenant
    ON raw.retention_audit_log(tenant_id) WHERE tenant_id IS NOT NULL;

COMMENT ON TABLE raw.retention_audit_log IS 'Audit trail for all retention cleanup operations';

-- Grant access to retention role
GRANT SELECT, INSERT, UPDATE ON raw.retention_config TO raw_retention_role;
GRANT SELECT, INSERT, UPDATE ON raw.retention_audit_log TO raw_retention_role;

-- =============================================================================
-- Cleanup Function: Single Table
-- =============================================================================

-- Function to cleanup a single table with batching and audit logging
CREATE OR REPLACE FUNCTION raw.cleanup_table_retention(
    p_table_name VARCHAR(255),
    p_run_id VARCHAR(255),
    p_retention_months INTEGER DEFAULT 13,
    p_batch_size INTEGER DEFAULT 10000
)
RETURNS TABLE (
    table_name VARCHAR(255),
    records_deleted BIGINT,
    execution_time_ms BIGINT
) AS $$
DECLARE
    v_cutoff_date TIMESTAMP WITH TIME ZONE;
    v_total_deleted BIGINT := 0;
    v_batch_deleted BIGINT;
    v_oldest_date TIMESTAMP WITH TIME ZONE;
    v_newest_date TIMESTAMP WITH TIME ZONE;
    v_start_time TIMESTAMP WITH TIME ZONE;
    v_audit_id VARCHAR(255);
BEGIN
    v_start_time := NOW();
    v_cutoff_date := NOW() - (p_retention_months || ' months')::INTERVAL;
    v_audit_id := uuid_generate_v4()::TEXT;

    -- Insert audit record (started)
    INSERT INTO raw.retention_audit_log (id, run_id, table_name, cutoff_date, status)
    VALUES (v_audit_id, p_run_id, p_table_name, v_cutoff_date, 'running');

    -- Get date range of records to be deleted
    EXECUTE format(
        'SELECT MIN(extracted_at), MAX(extracted_at) FROM raw.%I WHERE extracted_at < $1',
        p_table_name
    ) INTO v_oldest_date, v_newest_date USING v_cutoff_date;

    -- Delete in batches to avoid long locks
    LOOP
        EXECUTE format(
            'WITH to_delete AS (
                SELECT id FROM raw.%I
                WHERE extracted_at < $1
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            DELETE FROM raw.%I
            WHERE id IN (SELECT id FROM to_delete)',
            p_table_name, p_table_name
        ) USING v_cutoff_date, p_batch_size;

        GET DIAGNOSTICS v_batch_deleted = ROW_COUNT;
        v_total_deleted := v_total_deleted + v_batch_deleted;

        -- Exit when no more records to delete
        EXIT WHEN v_batch_deleted = 0;

        -- Brief pause between batches to reduce lock contention
        PERFORM pg_sleep(0.1);
    END LOOP;

    -- Update audit record (completed)
    UPDATE raw.retention_audit_log
    SET records_deleted = v_total_deleted,
        oldest_record_date = v_oldest_date,
        newest_record_date = v_newest_date,
        completed_at = NOW(),
        status = 'success',
        execution_time_ms = EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT
    WHERE id = v_audit_id;

    -- Return results
    RETURN QUERY SELECT
        p_table_name::VARCHAR(255),
        v_total_deleted,
        EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT;

EXCEPTION WHEN OTHERS THEN
    -- Log error in audit
    UPDATE raw.retention_audit_log
    SET status = 'failed',
        error_message = SQLERRM,
        completed_at = NOW(),
        execution_time_ms = EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT
    WHERE id = v_audit_id;

    RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION raw.cleanup_table_retention IS 'Cleanup old records from a single raw table with batching and audit logging';

-- =============================================================================
-- Cleanup Function: Per-Tenant (for selective cleanup)
-- =============================================================================

CREATE OR REPLACE FUNCTION raw.cleanup_tenant_retention(
    p_tenant_id VARCHAR(255),
    p_table_name VARCHAR(255),
    p_run_id VARCHAR(255),
    p_retention_months INTEGER DEFAULT 13,
    p_batch_size INTEGER DEFAULT 10000
)
RETURNS TABLE (
    table_name VARCHAR(255),
    tenant_id VARCHAR(255),
    records_deleted BIGINT,
    execution_time_ms BIGINT
) AS $$
DECLARE
    v_cutoff_date TIMESTAMP WITH TIME ZONE;
    v_total_deleted BIGINT := 0;
    v_batch_deleted BIGINT;
    v_start_time TIMESTAMP WITH TIME ZONE;
    v_audit_id VARCHAR(255);
BEGIN
    v_start_time := NOW();
    v_cutoff_date := NOW() - (p_retention_months || ' months')::INTERVAL;
    v_audit_id := uuid_generate_v4()::TEXT;

    -- Insert audit record
    INSERT INTO raw.retention_audit_log (id, run_id, table_name, tenant_id, cutoff_date, status)
    VALUES (v_audit_id, p_run_id, p_table_name, p_tenant_id, v_cutoff_date, 'running');

    -- Delete in batches
    LOOP
        EXECUTE format(
            'WITH to_delete AS (
                SELECT id FROM raw.%I
                WHERE tenant_id = $1 AND extracted_at < $2
                LIMIT $3
                FOR UPDATE SKIP LOCKED
            )
            DELETE FROM raw.%I
            WHERE id IN (SELECT id FROM to_delete)',
            p_table_name, p_table_name
        ) USING p_tenant_id, v_cutoff_date, p_batch_size;

        GET DIAGNOSTICS v_batch_deleted = ROW_COUNT;
        v_total_deleted := v_total_deleted + v_batch_deleted;

        EXIT WHEN v_batch_deleted = 0;
        PERFORM pg_sleep(0.1);
    END LOOP;

    -- Update audit record
    UPDATE raw.retention_audit_log
    SET records_deleted = v_total_deleted,
        completed_at = NOW(),
        status = 'success',
        execution_time_ms = EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT
    WHERE id = v_audit_id;

    RETURN QUERY SELECT
        p_table_name::VARCHAR(255),
        p_tenant_id::VARCHAR(255),
        v_total_deleted,
        EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT;

EXCEPTION WHEN OTHERS THEN
    UPDATE raw.retention_audit_log
    SET status = 'failed',
        error_message = SQLERRM,
        completed_at = NOW()
    WHERE id = v_audit_id;

    RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION raw.cleanup_tenant_retention IS 'Cleanup old records for a specific tenant from a raw table';

-- =============================================================================
-- Main Cleanup Orchestrator
-- =============================================================================

CREATE OR REPLACE FUNCTION raw.execute_retention_cleanup()
RETURNS TABLE (
    run_id VARCHAR(255),
    table_name VARCHAR(255),
    records_deleted BIGINT,
    execution_time_ms BIGINT,
    status VARCHAR(50)
) AS $$
DECLARE
    v_run_id VARCHAR(255);
    v_config RECORD;
    v_table_name VARCHAR(255);
    v_tables VARCHAR(255)[] := ARRAY[
        'raw_shopify_orders',
        'raw_meta_ads_insights',
        'raw_google_ads_campaigns',
        'raw_shopify_customers',
        'raw_shopify_products',
        'raw_pipeline_runs'
    ];
    v_result RECORD;
    v_total_start TIMESTAMP WITH TIME ZONE;
BEGIN
    v_total_start := NOW();
    v_run_id := 'cleanup-' || to_char(NOW(), 'YYYYMMDD-HH24MISS') || '-' || substr(uuid_generate_v4()::TEXT, 1, 8);

    -- Get configuration
    SELECT * INTO v_config FROM raw.retention_config WHERE id = 'default';

    -- Check if cleanup is enabled
    IF NOT v_config.is_enabled THEN
        RAISE NOTICE 'Retention cleanup is disabled';
        RETURN;
    END IF;

    RAISE NOTICE 'Starting retention cleanup run: %', v_run_id;
    RAISE NOTICE 'Retention period: % months, Batch size: %', v_config.retention_months, v_config.batch_size;

    -- Process each table
    FOREACH v_table_name IN ARRAY v_tables
    LOOP
        RAISE NOTICE 'Processing table: %', v_table_name;

        BEGIN
            FOR v_result IN
                SELECT * FROM raw.cleanup_table_retention(
                    v_table_name,
                    v_run_id,
                    v_config.retention_months,
                    v_config.batch_size
                )
            LOOP
                RETURN QUERY SELECT
                    v_run_id,
                    v_result.table_name,
                    v_result.records_deleted,
                    v_result.execution_time_ms,
                    'success'::VARCHAR(50);
            END LOOP;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Error cleaning table %: %', v_table_name, SQLERRM;
            RETURN QUERY SELECT
                v_run_id,
                v_table_name,
                0::BIGINT,
                0::BIGINT,
                'failed'::VARCHAR(50);
        END;
    END LOOP;

    -- Update last run timestamp
    UPDATE raw.retention_config
    SET last_run_at = NOW(),
        updated_at = NOW()
    WHERE id = 'default';

    RAISE NOTICE 'Retention cleanup completed. Run ID: %', v_run_id;
    RAISE NOTICE 'Total execution time: % ms', EXTRACT(MILLISECONDS FROM (NOW() - v_total_start));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION raw.execute_retention_cleanup IS 'Main orchestrator for raw data retention cleanup - runs across all tables';

-- Grant execute to retention role
GRANT EXECUTE ON FUNCTION raw.cleanup_table_retention TO raw_retention_role;
GRANT EXECUTE ON FUNCTION raw.cleanup_tenant_retention TO raw_retention_role;
GRANT EXECUTE ON FUNCTION raw.execute_retention_cleanup TO raw_retention_role;

-- =============================================================================
-- Dry Run Function (Preview what would be deleted)
-- =============================================================================

CREATE OR REPLACE FUNCTION raw.preview_retention_cleanup(
    p_retention_months INTEGER DEFAULT NULL
)
RETURNS TABLE (
    table_name VARCHAR(255),
    records_to_delete BIGINT,
    oldest_record TIMESTAMP WITH TIME ZONE,
    newest_record TIMESTAMP WITH TIME ZONE,
    cutoff_date TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    v_cutoff_date TIMESTAMP WITH TIME ZONE;
    v_retention_months INTEGER;
BEGIN
    -- Get retention months from config or parameter
    IF p_retention_months IS NULL THEN
        SELECT retention_months INTO v_retention_months
        FROM raw.retention_config WHERE id = 'default';
    ELSE
        v_retention_months := p_retention_months;
    END IF;

    v_cutoff_date := NOW() - (v_retention_months || ' months')::INTERVAL;

    -- Preview each table
    RETURN QUERY
    SELECT
        'raw_shopify_orders'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(extracted_at),
        MAX(extracted_at),
        v_cutoff_date
    FROM raw.raw_shopify_orders
    WHERE extracted_at < v_cutoff_date;

    RETURN QUERY
    SELECT
        'raw_meta_ads_insights'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(extracted_at),
        MAX(extracted_at),
        v_cutoff_date
    FROM raw.raw_meta_ads_insights
    WHERE extracted_at < v_cutoff_date;

    RETURN QUERY
    SELECT
        'raw_google_ads_campaigns'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(extracted_at),
        MAX(extracted_at),
        v_cutoff_date
    FROM raw.raw_google_ads_campaigns
    WHERE extracted_at < v_cutoff_date;

    RETURN QUERY
    SELECT
        'raw_shopify_customers'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(extracted_at),
        MAX(extracted_at),
        v_cutoff_date
    FROM raw.raw_shopify_customers
    WHERE extracted_at < v_cutoff_date;

    RETURN QUERY
    SELECT
        'raw_shopify_products'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(extracted_at),
        MAX(extracted_at),
        v_cutoff_date
    FROM raw.raw_shopify_products
    WHERE extracted_at < v_cutoff_date;

    RETURN QUERY
    SELECT
        'raw_pipeline_runs'::VARCHAR(255),
        COUNT(*)::BIGINT,
        MIN(started_at),
        MAX(started_at),
        v_cutoff_date
    FROM raw.raw_pipeline_runs
    WHERE started_at < v_cutoff_date;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

COMMENT ON FUNCTION raw.preview_retention_cleanup IS 'Preview what would be deleted without actually deleting - use for validation';

GRANT EXECUTE ON FUNCTION raw.preview_retention_cleanup TO raw_retention_role;
GRANT EXECUTE ON FUNCTION raw.preview_retention_cleanup TO raw_admin_role;

-- =============================================================================
-- pg_cron Scheduling (if extension available)
-- =============================================================================

-- Uncomment and run if pg_cron is available:
--
-- -- Schedule daily cleanup at 3 AM UTC
-- SELECT cron.schedule(
--     'raw-retention-cleanup',
--     '0 3 * * *',
--     $$SELECT * FROM raw.execute_retention_cleanup()$$
-- );
--
-- -- View scheduled jobs
-- SELECT * FROM cron.job;
--
-- -- Unschedule if needed
-- SELECT cron.unschedule('raw-retention-cleanup');

-- =============================================================================
-- Retention Cleanup Configuration Complete
-- =============================================================================

SELECT 'Retention cleanup functions created successfully' AS status;
SELECT 'Run SELECT * FROM raw.preview_retention_cleanup() to preview deletions' AS usage_preview;
SELECT 'Run SELECT * FROM raw.execute_retention_cleanup() to execute cleanup' AS usage_execute;
