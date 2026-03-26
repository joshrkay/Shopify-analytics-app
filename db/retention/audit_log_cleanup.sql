-- Audit Log Table - Retention Cleanup Job
-- Version: 1.0.0
-- Date: 2026-03-19
--
-- This script provides a function for purging audit_logs older than a configurable
-- retention period (default 730 days = 2 years).
-- All deletions are batched to avoid long locks.
--
-- RETENTION POLICY:
--   - Audit logs: 730 days (2 years) from created_at timestamp
--
-- SCHEDULING:
--   Option 1: pg_cron (PostgreSQL extension)
--   Option 2: External scheduler (cron, Render cron job, etc.)
--
-- Usage:
--   Manual:   SELECT public.execute_audit_log_cleanup();
--   Dry run:  SELECT public.execute_audit_log_cleanup(retention_days := 730, dry_run := TRUE);
--   pg_cron:  SELECT cron.schedule('audit-log-cleanup', '0 4 * * 0', 'SELECT public.execute_audit_log_cleanup()');

-- =============================================================================
-- Main Cleanup Function
-- =============================================================================

CREATE OR REPLACE FUNCTION public.execute_audit_log_cleanup(
    retention_days INTEGER DEFAULT 730,
    dry_run BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    run_id VARCHAR(255),
    table_name VARCHAR(255),
    records_deleted BIGINT,
    execution_time_ms BIGINT,
    status VARCHAR(50)
) AS $$
DECLARE
    v_run_id VARCHAR(255);
    v_cutoff_date TIMESTAMP WITH TIME ZONE;
    v_total_deleted BIGINT := 0;
    v_batch_deleted BIGINT;
    v_batch_size INTEGER := 10000;
    v_start_time TIMESTAMP WITH TIME ZONE;
    v_preview_count BIGINT;
    v_oldest_date TIMESTAMP WITH TIME ZONE;
    v_newest_date TIMESTAMP WITH TIME ZONE;
BEGIN
    v_start_time := NOW();
    v_run_id := 'audit-cleanup-' || to_char(NOW(), 'YYYYMMDD-HH24MISS') || '-' || substr(uuid_generate_v4()::TEXT, 1, 8);
    v_cutoff_date := NOW() - (retention_days || ' days')::INTERVAL;

    RAISE NOTICE 'Starting audit log cleanup run: %', v_run_id;
    RAISE NOTICE 'Retention period: % days, Cutoff date: %, Dry run: %', retention_days, v_cutoff_date, dry_run;

    -- Get date range and count of records to be deleted
    SELECT COUNT(*), MIN(created_at), MAX(created_at)
    INTO v_preview_count, v_oldest_date, v_newest_date
    FROM public.audit_logs
    WHERE created_at < v_cutoff_date;

    RAISE NOTICE 'Records eligible for deletion: %, Oldest: %, Newest: %', v_preview_count, v_oldest_date, v_newest_date;

    -- If dry run, return preview without deleting
    IF dry_run THEN
        RAISE NOTICE 'DRY RUN — no records deleted';
        RETURN QUERY SELECT
            v_run_id,
            'audit_logs'::VARCHAR(255),
            v_preview_count,
            EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT,
            'dry_run'::VARCHAR(50);
        RETURN;
    END IF;

    -- Delete in batches to avoid long locks
    LOOP
        WITH to_delete AS (
            SELECT id FROM public.audit_logs
            WHERE created_at < v_cutoff_date
            LIMIT v_batch_size
            FOR UPDATE SKIP LOCKED
        )
        DELETE FROM public.audit_logs
        WHERE id IN (SELECT id FROM to_delete);

        GET DIAGNOSTICS v_batch_deleted = ROW_COUNT;
        v_total_deleted := v_total_deleted + v_batch_deleted;

        -- Exit when no more records to delete
        EXIT WHEN v_batch_deleted = 0;

        -- Brief pause between batches to reduce lock contention
        PERFORM pg_sleep(0.1);
    END LOOP;

    RAISE NOTICE 'Audit log cleanup completed. Run ID: %, Records deleted: %', v_run_id, v_total_deleted;
    RAISE NOTICE 'Total execution time: % ms', EXTRACT(MILLISECONDS FROM (NOW() - v_start_time));

    -- Return summary
    RETURN QUERY SELECT
        v_run_id,
        'audit_logs'::VARCHAR(255),
        v_total_deleted,
        EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT,
        'success'::VARCHAR(50);

EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Audit log cleanup failed: %', SQLERRM;
    RETURN QUERY SELECT
        v_run_id,
        'audit_logs'::VARCHAR(255),
        0::BIGINT,
        EXTRACT(MILLISECONDS FROM (NOW() - v_start_time))::BIGINT,
        'failed'::VARCHAR(50);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION public.execute_audit_log_cleanup IS 'Purge audit_logs older than retention_days (default 730 = 2 years) in batches. Supports dry_run mode for preview.';

-- =============================================================================
-- Audit Log Cleanup Configuration Complete
-- =============================================================================

SELECT 'Audit log cleanup function created successfully' AS status;
SELECT 'Run SELECT * FROM public.execute_audit_log_cleanup(dry_run := TRUE) to preview deletions' AS usage_preview;
SELECT 'Run SELECT * FROM public.execute_audit_log_cleanup() to execute cleanup' AS usage_execute;
