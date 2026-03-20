-- =============================================================================
-- Tenant ID Indexes for Application Tables
--
-- Adds B-tree indexes on tenant_id for all identity/app tables that filter
-- by tenant. These tables are queried on every authenticated request via
-- RLS or application-level tenant filtering.
--
-- SAFETY: All CREATE INDEX use IF NOT EXISTS to ensure idempotency.
-- =============================================================================

BEGIN;

-- Identity & access tables
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id);
CREATE INDEX IF NOT EXISTS idx_custom_dashboards_tenant_id ON custom_dashboards (tenant_id);
CREATE INDEX IF NOT EXISTS idx_custom_reports_tenant_id ON custom_reports (tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_proposals_tenant_id ON action_proposals (tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_proposal_jobs_tenant_id ON action_proposal_jobs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_tenant_id ON tenant_subscriptions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_connector_credentials_tenant_id ON connector_credentials (tenant_id);
CREATE INDEX IF NOT EXISTS idx_connection_consents_tenant_id ON connection_consents (tenant_id);

-- Dashboard & report tables
CREATE INDEX IF NOT EXISTS idx_report_templates_tenant_id ON report_templates (tenant_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_shares_tenant_id ON dashboard_shares (tenant_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_audit_tenant_id ON dashboard_audit (tenant_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_metric_bindings_tenant_id ON dashboard_metric_bindings (tenant_id);

-- Billing & usage tables
CREATE INDEX IF NOT EXISTS idx_billing_events_tenant_id ON billing_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_historical_backfill_requests_tenant_id ON historical_backfill_requests (tenant_id);
CREATE INDEX IF NOT EXISTS idx_backfill_executions_tenant_id ON backfill_executions (tenant_id);

-- Audit & logging tables
CREATE INDEX IF NOT EXISTS idx_ga_audit_logs_tenant_id ON ga_audit_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_approval_audit_tenant_id ON action_approval_audit (tenant_id);
CREATE INDEX IF NOT EXISTS idx_action_execution_logs_tenant_id ON action_execution_logs (tenant_id);

-- AI & analytics tables
CREATE INDEX IF NOT EXISTS idx_recommendation_jobs_tenant_id ON recommendation_jobs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_dataset_metrics_tenant_id ON dataset_metrics (tenant_id);
CREATE INDEX IF NOT EXISTS idx_dataset_version_tenant_id ON dataset_version (tenant_id);
CREATE INDEX IF NOT EXISTS idx_llm_model_registry_tenant_id ON llm_model_registry (tenant_id);

-- Access & notification tables
CREATE INDEX IF NOT EXISTS idx_access_revocations_tenant_id ON access_revocations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_changelog_read_status_tenant_id ON changelog_read_status (tenant_id);
CREATE INDEX IF NOT EXISTS idx_data_change_events_tenant_id ON data_change_events (tenant_id);

COMMIT;
