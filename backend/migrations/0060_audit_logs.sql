-- GA Audit Logs Schema
-- Migration 0060 - Canonical append-only audit log for auth + dashboard access
--
-- GA Scope: auth events + dashboard access only
-- Retention: 90 days (enforced by daily worker)
-- PII: automatically redacted before insertion
-- Multi-tenant: tenant_id on every row
--
-- CRITICAL: This table is append-only. UPDATE/DELETE blocked by trigger
-- (except retention job which temporarily disables the trigger).

-- ==========================================================================
-- Create ga_audit_logs table
-- ==========================================================================

CREATE TABLE IF NOT EXISTS ga_audit_logs (
    -- Primary identifier
    id              VARCHAR(36)     PRIMARY KEY,

    -- Event classification
    event_type      VARCHAR(100)    NOT NULL,

    -- Actor & tenant context (nullable for pre-auth failures)
    user_id         VARCHAR(255),
    tenant_id       VARCHAR(255),

    -- Dashboard context (nullable for auth-only events)
    dashboard_id    VARCHAR(255),

    -- Where the access occurred
    access_surface  VARCHAR(50)     NOT NULL DEFAULT 'external_app',

    -- Outcome
    success         BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Flexible payload (PII-sanitized before storage)
    metadata        JSONB           NOT NULL DEFAULT '{}',

    -- Request tracing
    correlation_id  VARCHAR(36)     NOT NULL,

    -- Timing (server-side only, never from client)
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes for common query patterns
-- ==========================================================================

-- Primary query: Recent logs by tenant (DESC for "most recent first")
CREATE INDEX IF NOT EXISTS ix_ga_audit_tenant_created
    ON ga_audit_logs (tenant_id, created_at DESC);

-- Query by event type within tenant
CREATE INDEX IF NOT EXISTS ix_ga_audit_tenant_event_type
    ON ga_audit_logs (tenant_id, event_type);

-- Dashboard-specific queries (which dashboards were accessed)
CREATE INDEX IF NOT EXISTS ix_ga_audit_tenant_dashboard
    ON ga_audit_logs (tenant_id, dashboard_id, created_at DESC)
    WHERE dashboard_id IS NOT NULL;

-- Correlation tracing (find all events for a request)
CREATE INDEX IF NOT EXISTS ix_ga_audit_correlation
    ON ga_audit_logs (correlation_id);

-- Failure analysis (find all failed events for a tenant)
CREATE INDEX IF NOT EXISTS ix_ga_audit_tenant_success
    ON ga_audit_logs (tenant_id, success, created_at DESC);

-- User activity history
CREATE INDEX IF NOT EXISTS ix_ga_audit_tenant_user
    ON ga_audit_logs (tenant_id, user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Retention job: efficient deletion of old records per tenant
CREATE INDEX IF NOT EXISTS ix_ga_audit_retention
    ON ga_audit_logs (created_at)
    WHERE created_at < NOW() - INTERVAL '90 days';

-- ==========================================================================
-- Immutability trigger (defense in depth)
-- ==========================================================================

CREATE OR REPLACE FUNCTION prevent_ga_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'GA audit logs are immutable. UPDATE and DELETE operations are not permitted.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ga_audit_log_immutable ON ga_audit_logs;

CREATE TRIGGER ga_audit_log_immutable
    BEFORE UPDATE OR DELETE ON ga_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_ga_audit_log_modification();

-- ==========================================================================
-- Validate event_type values via CHECK constraint
-- ==========================================================================

ALTER TABLE ga_audit_logs
    ADD CONSTRAINT chk_ga_audit_event_type
    CHECK (event_type IN (
        'auth.login_success',
        'auth.login_failed',
        'auth.jwt_issued',
        'auth.jwt_refresh',
        'auth.jwt_revoked',
        'dashboard.viewed',
        'dashboard.load_failed',
        'dashboard.access_denied'
    ));

-- Validate access_surface values
ALTER TABLE ga_audit_logs
    ADD CONSTRAINT chk_ga_audit_access_surface
    CHECK (access_surface IN ('shopify_embed', 'external_app'));

-- ==========================================================================
-- Table and column comments
-- ==========================================================================

COMMENT ON TABLE ga_audit_logs IS
    'GA-scope append-only audit log for auth and dashboard access. 90-day retention.';
COMMENT ON COLUMN ga_audit_logs.id IS
    'Unique event identifier (UUID v4).';
COMMENT ON COLUMN ga_audit_logs.event_type IS
    'Event classification: auth.login_success, dashboard.viewed, etc.';
COMMENT ON COLUMN ga_audit_logs.user_id IS
    'Actor user ID from JWT sub claim. NULL for pre-auth failures.';
COMMENT ON COLUMN ga_audit_logs.tenant_id IS
    'Tenant identifier from JWT org_id. NULL for pre-auth failures.';
COMMENT ON COLUMN ga_audit_logs.dashboard_id IS
    'Dashboard identifier. NULL for auth-only events.';
COMMENT ON COLUMN ga_audit_logs.access_surface IS
    'Where the access occurred: shopify_embed or external_app.';
COMMENT ON COLUMN ga_audit_logs.success IS
    'Whether the action succeeded (true) or failed/was denied (false).';
COMMENT ON COLUMN ga_audit_logs.metadata IS
    'Event-specific JSON payload. PII is automatically sanitized before storage.';
COMMENT ON COLUMN ga_audit_logs.correlation_id IS
    'UUID for correlating related events across a single request.';
COMMENT ON COLUMN ga_audit_logs.created_at IS
    'Server-side timestamp. Never set from client input.';
