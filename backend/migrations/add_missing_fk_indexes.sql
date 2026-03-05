-- Add missing foreign key indexes to prevent sequential scans on joins.
-- All statements use IF NOT EXISTS / CONCURRENTLY so this migration is safe
-- to run on a live database and idempotent on re-run.

-- tenant_subscriptions.store_id — used in billing queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tenant_subscriptions_store_id
    ON tenant_subscriptions(store_id);

-- billing_events.store_id — used in billing queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_billing_events_store_id
    ON billing_events(store_id);

-- ai_insights composite index — used in job-result lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_insights_job_tenant
    ON ai_insights(job_id, tenant_id);

-- ga_audit_logs composite index — used in filtered audit queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ga_audit_tenant_event_created
    ON ga_audit_logs(tenant_id, event_type, created_at DESC);
