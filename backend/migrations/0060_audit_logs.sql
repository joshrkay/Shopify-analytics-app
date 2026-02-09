-- Story 5.7.1 - Canonical Audit Log Data Model extensions
-- Adds dashboard/access surface fields and canonical columns for audit logs.

ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS event_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS dashboard_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS access_surface VARCHAR(50),
    ADD COLUMN IF NOT EXISTS success BOOLEAN;

UPDATE audit_logs
SET event_type = action
WHERE event_type IS NULL;

UPDATE audit_logs
SET created_at = timestamp
WHERE created_at IS NULL;

UPDATE audit_logs
SET success = CASE WHEN outcome = 'success' THEN TRUE ELSE FALSE END
WHERE success IS NULL;

CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type
    ON audit_logs (event_type);

CREATE INDEX IF NOT EXISTS ix_audit_logs_dashboard
    ON audit_logs (tenant_id, dashboard_id);
