-- AI Insights Schema
-- Version: 1.0.0
-- Date: 2026-01-28
-- Story: 8.1 - AI Insight Generation (Read-Only Analytics)
--
-- Creates tables for:
--   - ai_insights: Stores AI-generated business insights from aggregated dbt mart data
--   - insight_jobs: Tracks insight generation job execution
--
-- SECURITY:
--   - tenant_id column on all tables for tenant isolation
--   - RLS policies should be applied separately if needed
--   - No PII stored - insights generated from aggregated data only

-- Ensure uuid-ossp extension is available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

-- Types of insights the system can generate
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insight_type') THEN
        CREATE TYPE insight_type AS ENUM (
            'spend_anomaly',
            'roas_change',
            'revenue_vs_spend_divergence',
            'channel_mix_shift',
            'cac_anomaly',
            'aov_change'
        );
    END IF;
END
$$;

-- Severity levels for prioritization
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insight_severity') THEN
        CREATE TYPE insight_severity AS ENUM (
            'info',
            'warning',
            'critical'
        );
    END IF;
END
$$;

-- Job status enumeration
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insight_job_status') THEN
        CREATE TYPE insight_job_status AS ENUM (
            'queued',
            'running',
            'failed',
            'success',
            'skipped'
        );
    END IF;
END
$$;

-- Cadence for insight generation
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'insight_job_cadence') THEN
        CREATE TYPE insight_job_cadence AS ENUM (
            'daily',
            'hourly'
        );
    END IF;
END
$$;

-- =============================================================================
-- TABLES
-- =============================================================================

-- AI Insights table
-- Stores AI-generated business insights from aggregated marketing/revenue metrics
CREATE TABLE IF NOT EXISTS ai_insights (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Insight classification
    insight_type insight_type NOT NULL,
    severity insight_severity NOT NULL DEFAULT 'info',

    -- Natural language summary (template-based for determinism)
    summary TEXT NOT NULL,

    -- Supporting metrics: Array of {metric, current_value, prior_value, delta, delta_pct, timeframe}
    supporting_metrics JSONB NOT NULL DEFAULT '[]'::JSONB,

    -- Confidence score (0.0 to 1.0)
    confidence_score FLOAT NOT NULL,

    -- Period context
    period_type VARCHAR(50) NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    comparison_type VARCHAR(50) NOT NULL,

    -- Optional filters (platform/campaign specific insights)
    platform VARCHAR(50),
    campaign_id VARCHAR(255),
    currency VARCHAR(10),

    -- Generation metadata
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    job_id VARCHAR(255),

    -- Determinism hash for deduplication
    content_hash VARCHAR(64) NOT NULL,

    -- Read/dismiss status (for UI)
    is_read INTEGER NOT NULL DEFAULT 0,
    is_dismissed INTEGER NOT NULL DEFAULT 0,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Insight Jobs table
-- Tracks insight generation job execution
CREATE TABLE IF NOT EXISTS insight_jobs (
    -- Primary key
    job_id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Cadence
    cadence insight_job_cadence NOT NULL DEFAULT 'daily',

    -- Status tracking
    status insight_job_status NOT NULL DEFAULT 'queued',

    -- Results
    insights_generated INTEGER NOT NULL DEFAULT 0,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error tracking
    error_message TEXT,

    -- Job metadata (periods analyzed, skip reasons, etc.)
    job_metadata JSONB DEFAULT '{}'::JSONB,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES FOR ai_insights
-- =============================================================================

-- Single column indexes
CREATE INDEX IF NOT EXISTS ix_ai_insights_tenant_id
    ON ai_insights(tenant_id);

CREATE INDEX IF NOT EXISTS ix_ai_insights_insight_type
    ON ai_insights(insight_type);

CREATE INDEX IF NOT EXISTS ix_ai_insights_severity
    ON ai_insights(severity);

CREATE INDEX IF NOT EXISTS ix_ai_insights_platform
    ON ai_insights(platform);

CREATE INDEX IF NOT EXISTS ix_ai_insights_campaign_id
    ON ai_insights(campaign_id);

CREATE INDEX IF NOT EXISTS ix_ai_insights_generated_at
    ON ai_insights(generated_at);

CREATE INDEX IF NOT EXISTS ix_ai_insights_job_id
    ON ai_insights(job_id);

CREATE INDEX IF NOT EXISTS ix_ai_insights_content_hash
    ON ai_insights(content_hash);

-- Composite indexes for common query patterns
-- Tenant + generated_at for listing recent insights
CREATE INDEX IF NOT EXISTS ix_ai_insights_tenant_generated
    ON ai_insights(tenant_id, generated_at DESC);

-- Tenant + type for filtering by insight type
CREATE INDEX IF NOT EXISTS ix_ai_insights_tenant_type
    ON ai_insights(tenant_id, insight_type);

-- =============================================================================
-- INDEXES FOR insight_jobs
-- =============================================================================

-- Single column indexes
CREATE INDEX IF NOT EXISTS ix_insight_jobs_tenant_id
    ON insight_jobs(tenant_id);

CREATE INDEX IF NOT EXISTS ix_insight_jobs_status
    ON insight_jobs(status);

-- Composite indexes
-- Tenant + status for filtered status queries
CREATE INDEX IF NOT EXISTS ix_insight_jobs_tenant_status
    ON insight_jobs(tenant_id, status);

-- Tenant + created_at for finding recent jobs
CREATE INDEX IF NOT EXISTS ix_insight_jobs_tenant_created
    ON insight_jobs(tenant_id, created_at DESC);

-- =============================================================================
-- CONSTRAINTS
-- =============================================================================

-- Deduplication: prevent identical insights for same period
-- Content hash + period_end ensures we don't create duplicate insights
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ai_insights_dedup'
    ) THEN
        ALTER TABLE ai_insights ADD CONSTRAINT uq_ai_insights_dedup
            UNIQUE (tenant_id, content_hash, period_end);
    END IF;
END
$$;

-- Partial unique index: only ONE queued/running job per tenant at a time
-- This prevents duplicate active jobs
CREATE UNIQUE INDEX IF NOT EXISTS ix_insight_jobs_active_unique
    ON insight_jobs(tenant_id)
    WHERE status IN ('queued', 'running');

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for ai_insights
DROP TRIGGER IF EXISTS tr_ai_insights_updated_at ON ai_insights;
CREATE TRIGGER tr_ai_insights_updated_at
    BEFORE UPDATE ON ai_insights
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for insight_jobs
DROP TRIGGER IF EXISTS tr_insight_jobs_updated_at ON insight_jobs;
CREATE TRIGGER tr_insight_jobs_updated_at
    BEFORE UPDATE ON insight_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE ai_insights IS 'AI-generated business insights from aggregated dbt mart data. Story 8.1.';
COMMENT ON TABLE insight_jobs IS 'Tracks insight generation job execution. Story 8.1.';

COMMENT ON COLUMN ai_insights.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN ai_insights.content_hash IS 'SHA256 hash of input data for deduplication';
COMMENT ON COLUMN ai_insights.supporting_metrics IS 'Array of {metric, current_value, prior_value, delta, delta_pct, timeframe}';

COMMENT ON COLUMN insight_jobs.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN insight_jobs.cadence IS 'Job cadence: daily (standard plans) or hourly (enterprise only)';
