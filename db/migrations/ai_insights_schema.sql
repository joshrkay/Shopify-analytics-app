-- AI Insights Schema Migration
-- Version: 1.0.0
-- Date: 2026-01-28
--
-- This migration creates the AI insights tables for scheduled insight generation.
-- All tables enforce tenant isolation via tenant_id column.
--
-- CONSTRAINTS:
--   - No raw rows accessed (only dbt marts)
--   - No PII stored
--   - No cross-tenant access
--   - Insights generated on schedule only (not real-time)
--
-- Usage: psql $DATABASE_URL -f ai_insights_schema.sql

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- AI Insights Schema Setup
-- =============================================================================

-- Create schema namespace for AI insights (if using separate schema)
-- For now, using public schema to match existing pattern

-- =============================================================================
-- ai_insights
-- Stores scheduled AI-generated insights based on aggregated analytics marts
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_insights (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (REQUIRED - from JWT org_id only)
    tenant_id VARCHAR(255) NOT NULL,

    -- Insight identification
    insight_type VARCHAR(50) NOT NULL,
    insight_category VARCHAR(50) NOT NULL,

    -- Content
    summary TEXT NOT NULL,
    supporting_metrics JSONB NOT NULL DEFAULT '[]',

    -- Scoring
    confidence_score NUMERIC(3,2) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',

    -- Temporal context
    analysis_period_start DATE NOT NULL,
    analysis_period_end DATE NOT NULL,
    comparison_period_start DATE,
    comparison_period_end DATE,

    -- Generation metadata
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    generation_cadence VARCHAR(20) NOT NULL DEFAULT 'daily',
    model_version VARCHAR(20) NOT NULL DEFAULT 'v1.0',

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    dismissed_at TIMESTAMP WITH TIME ZONE,
    dismissed_by VARCHAR(255),

    -- Audit timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT ai_insights_confidence_range
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CONSTRAINT ai_insights_valid_severity
        CHECK (severity IN ('info', 'warning', 'critical')),
    CONSTRAINT ai_insights_valid_status
        CHECK (status IN ('active', 'dismissed', 'expired')),
    CONSTRAINT ai_insights_valid_cadence
        CHECK (generation_cadence IN ('daily', 'hourly')),
    CONSTRAINT ai_insights_valid_type
        CHECK (insight_type IN (
            'spend_anomaly',
            'roas_change',
            'revenue_spend_divergence',
            'channel_mix_shift',
            'aov_change',
            'conversion_rate_change',
            'cpa_anomaly'
        )),
    CONSTRAINT ai_insights_valid_category
        CHECK (insight_category IN (
            'anomaly',
            'trend',
            'opportunity',
            'risk'
        ))
);

-- Performance indexes (tenant_id first for partition pruning)
CREATE INDEX IF NOT EXISTS idx_ai_insights_tenant_id
    ON ai_insights(tenant_id);

CREATE INDEX IF NOT EXISTS idx_ai_insights_tenant_generated
    ON ai_insights(tenant_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_insights_tenant_type
    ON ai_insights(tenant_id, insight_type);

CREATE INDEX IF NOT EXISTS idx_ai_insights_tenant_status
    ON ai_insights(tenant_id, status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_ai_insights_cadence
    ON ai_insights(generation_cadence);

-- Comments
COMMENT ON TABLE ai_insights IS 'Scheduled AI-generated insights from aggregated analytics marts. No PII, no raw data access.';
COMMENT ON COLUMN ai_insights.tenant_id IS 'Tenant identifier from JWT org_id. NEVER from client input.';
COMMENT ON COLUMN ai_insights.insight_type IS 'Type of insight detected (spend_anomaly, roas_change, etc.)';
COMMENT ON COLUMN ai_insights.insight_category IS 'Category of insight (anomaly, trend, opportunity, risk)';
COMMENT ON COLUMN ai_insights.summary IS 'Natural language summary of the insight (1-2 sentences)';
COMMENT ON COLUMN ai_insights.supporting_metrics IS 'JSON array of metrics supporting this insight';
COMMENT ON COLUMN ai_insights.confidence_score IS 'Statistical confidence in the insight (0.0 to 1.0)';
COMMENT ON COLUMN ai_insights.severity IS 'Severity level: info, warning, or critical';
COMMENT ON COLUMN ai_insights.generation_cadence IS 'How often this insight type is generated: daily or hourly';
COMMENT ON COLUMN ai_insights.model_version IS 'Version of the insight detection model';

-- =============================================================================
-- ai_insight_generation_logs
-- Tracks each insight generation run for debugging and monitoring
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_insight_generation_logs (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Run identification
    run_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Execution details
    cadence VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'running',

    -- Results
    insights_generated INTEGER DEFAULT 0,
    detectors_run INTEGER DEFAULT 0,
    metrics_analyzed JSONB DEFAULT '{}',

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Analysis period
    analysis_date DATE NOT NULL,

    -- Audit
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT ai_insight_logs_valid_status
        CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    CONSTRAINT ai_insight_logs_valid_cadence
        CHECK (cadence IN ('daily', 'hourly'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ai_insight_logs_tenant
    ON ai_insight_generation_logs(tenant_id);

CREATE INDEX IF NOT EXISTS idx_ai_insight_logs_run
    ON ai_insight_generation_logs(run_id);

CREATE INDEX IF NOT EXISTS idx_ai_insight_logs_started
    ON ai_insight_generation_logs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_insight_logs_status
    ON ai_insight_generation_logs(status);

COMMENT ON TABLE ai_insight_generation_logs IS 'Tracks AI insight generation runs for monitoring and debugging';
COMMENT ON COLUMN ai_insight_generation_logs.run_id IS 'Unique identifier for this generation run';
COMMENT ON COLUMN ai_insight_generation_logs.metrics_analyzed IS 'Summary of metrics analyzed during this run';

-- =============================================================================
-- Migration Complete
-- =============================================================================

SELECT 'AI Insights schema migration completed successfully' AS status;
