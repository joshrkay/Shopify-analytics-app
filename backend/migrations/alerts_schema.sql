-- Alerts Schema
-- Version: 1.0.0
-- Date: 2026-03-04
--
-- Creates tables for:
--   - alert_rules: User-defined threshold monitoring rules
--   - alert_executions: History of when rules fired
--
-- SECURITY:
--   - tenant_id column on all tables for tenant isolation
--   - RLS policies should be applied separately if needed

-- Ensure uuid-ossp extension is available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'comparison_operator_type') THEN
        CREATE TYPE comparison_operator_type AS ENUM (
            'gt',
            'lt',
            'eq',
            'gte',
            'lte'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'evaluation_period_type') THEN
        CREATE TYPE evaluation_period_type AS ENUM (
            'daily',
            'weekly',
            'monthly'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_severity_type') THEN
        CREATE TYPE alert_severity_type AS ENUM (
            'info',
            'warning',
            'critical'
        );
    END IF;
END
$$;

-- =============================================================================
-- TABLES
-- =============================================================================

-- Alert Rules table
CREATE TABLE IF NOT EXISTS alert_rules (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Rule creator
    user_id VARCHAR(255),

    -- Rule definition
    name VARCHAR(255) NOT NULL,
    description TEXT,
    metric_name VARCHAR(100) NOT NULL,
    comparison_operator comparison_operator_type NOT NULL,
    threshold_value DOUBLE PRECISION NOT NULL,
    evaluation_period evaluation_period_type NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    severity alert_severity_type NOT NULL DEFAULT 'warning',

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Alert Executions table
CREATE TABLE IF NOT EXISTS alert_executions (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Link to parent rule
    alert_rule_id VARCHAR(255) NOT NULL,

    -- Execution data
    fired_at TIMESTAMP WITH TIME ZONE NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    threshold_value DOUBLE PRECISION NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    notification_id VARCHAR(255),

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Foreign key to alert_rules
    CONSTRAINT fk_executions_rule
        FOREIGN KEY (alert_rule_id)
        REFERENCES alert_rules(id)
        ON DELETE CASCADE
);

-- =============================================================================
-- INDEXES
-- =============================================================================

-- alert_rules indexes
CREATE INDEX IF NOT EXISTS ix_alert_rules_tenant_id
    ON alert_rules(tenant_id);

CREATE INDEX IF NOT EXISTS ix_alert_rules_user_id
    ON alert_rules(user_id);

CREATE INDEX IF NOT EXISTS ix_alert_rules_tenant_enabled
    ON alert_rules(tenant_id, enabled);

-- alert_executions indexes
CREATE INDEX IF NOT EXISTS ix_alert_executions_tenant_id
    ON alert_executions(tenant_id);

CREATE INDEX IF NOT EXISTS ix_alert_executions_alert_rule_id
    ON alert_executions(alert_rule_id);

CREATE INDEX IF NOT EXISTS ix_alert_executions_tenant_rule
    ON alert_executions(tenant_id, alert_rule_id);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

DROP TRIGGER IF EXISTS tr_alert_rules_updated_at ON alert_rules;
CREATE TRIGGER tr_alert_rules_updated_at
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS tr_alert_executions_updated_at ON alert_executions;
CREATE TRIGGER tr_alert_executions_updated_at
    BEFORE UPDATE ON alert_executions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE alert_rules IS 'User-defined threshold monitoring rules for metrics like ROAS, spend, revenue.';
COMMENT ON TABLE alert_executions IS 'History of when alert rules fired, with metric values at time of firing.';

COMMENT ON COLUMN alert_rules.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN alert_rules.metric_name IS 'Metric to monitor: roas, spend, revenue, etc.';
COMMENT ON COLUMN alert_rules.comparison_operator IS 'Comparison: gt, lt, eq, gte, lte';
COMMENT ON COLUMN alert_rules.threshold_value IS 'Value to compare metric against';
COMMENT ON COLUMN alert_rules.evaluation_period IS 'How often to evaluate: daily, weekly, monthly';

COMMENT ON COLUMN alert_executions.alert_rule_id IS 'FK to alert_rules - which rule fired';
COMMENT ON COLUMN alert_executions.fired_at IS 'When the alert was triggered';
COMMENT ON COLUMN alert_executions.metric_value IS 'Actual metric value when alert fired';
COMMENT ON COLUMN alert_executions.threshold_value IS 'Threshold value at time of firing (snapshot)';
