-- Migration: Create audit_export_jobs queue table for async audit exports.

CREATE TABLE IF NOT EXISTS audit_export_jobs (
    id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    format VARCHAR(16) NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    claimed_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    artifact_location TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    result_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_export_jobs_status_created
    ON audit_export_jobs (status, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_export_jobs_retry
    ON audit_export_jobs (status, next_retry_at);

CREATE INDEX IF NOT EXISTS idx_audit_export_jobs_tenant_status
    ON audit_export_jobs (tenant_id, status);

DO $$ BEGIN
    ALTER TABLE audit_export_jobs
        ADD CONSTRAINT chk_audit_export_jobs_status
        CHECK (status IN ('queued', 'in_progress', 'completed', 'failed'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DROP TRIGGER IF EXISTS update_audit_export_jobs_updated_at ON audit_export_jobs;
CREATE TRIGGER update_audit_export_jobs_updated_at
    BEFORE UPDATE ON audit_export_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
