-- AI Recommendations Schema
-- Version: 1.0.0
-- Date: 2026-01-28
-- Story: 8.3 - AI Recommendations (No Actions)
--
-- Creates tables for:
--   - ai_recommendations: Stores tactical AI recommendations derived from insights
--   - recommendation_jobs: Tracks recommendation generation job execution
--
-- SECURITY:
--   - tenant_id column on all tables for tenant isolation
--   - RLS policies should be applied separately if needed
--   - No PII stored - recommendations generated from aggregated data only
--   - NO AUTO-EXECUTION - all recommendations are advisory only
--
-- LANGUAGE RULES:
--   - All recommendation_text uses conditional language ("consider", "may help")
--   - No imperative language ("must", "should", "do this")

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

-- Types of recommendations the system can generate
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_type') THEN
        CREATE TYPE recommendation_type AS ENUM (
            'reduce_spend',
            'increase_spend',
            'reallocate_budget',
            'pause_campaign',
            'scale_campaign',
            'optimize_targeting',
            'review_creative',
            'adjust_bidding'
        );
    END IF;
END
$$;

-- Priority levels for recommendations
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_priority') THEN
        CREATE TYPE recommendation_priority AS ENUM (
            'low',
            'medium',
            'high'
        );
    END IF;
END
$$;

-- Estimated impact (qualitative only - no specific numbers)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estimated_impact') THEN
        CREATE TYPE estimated_impact AS ENUM (
            'minimal',
            'moderate',
            'significant'
        );
    END IF;
END
$$;

-- Risk level for recommendations
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'risk_level') THEN
        CREATE TYPE risk_level AS ENUM (
            'low',
            'medium',
            'high'
        );
    END IF;
END
$$;

-- Affected entity type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'affected_entity_type') THEN
        CREATE TYPE affected_entity_type AS ENUM (
            'campaign',
            'platform',
            'account'
        );
    END IF;
END
$$;

-- Job status enumeration (reuse insight_job_status if exists, otherwise create)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_job_status') THEN
        CREATE TYPE recommendation_job_status AS ENUM (
            'queued',
            'running',
            'failed',
            'success',
            'skipped'
        );
    END IF;
END
$$;

-- Cadence for recommendation generation (reuse pattern from insights)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation_job_cadence') THEN
        CREATE TYPE recommendation_job_cadence AS ENUM (
            'daily',
            'hourly'
        );
    END IF;
END
$$;

-- =============================================================================
-- TABLES
-- =============================================================================

-- AI Recommendations table
-- Stores tactical AI recommendations derived from AI insights
-- NO AUTO-EXECUTION: All recommendations are advisory only
CREATE TABLE IF NOT EXISTS ai_recommendations (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Link to source insight (REQUIRED - recommendations tied to insights)
    related_insight_id VARCHAR(255) NOT NULL,

    -- Recommendation classification
    recommendation_type recommendation_type NOT NULL,
    priority recommendation_priority NOT NULL DEFAULT 'medium',

    -- Natural language recommendation (MUST use conditional language)
    -- Examples: "Consider...", "You may want...", "may help..."
    -- FORBIDDEN: "You should...", "You must...", "Do this..."
    recommendation_text TEXT NOT NULL,

    -- Explanation of why this recommendation is being made
    rationale TEXT,

    -- Impact and risk assessment (qualitative only)
    estimated_impact estimated_impact NOT NULL DEFAULT 'moderate',
    risk_level risk_level NOT NULL DEFAULT 'medium',

    -- Confidence score (0.0 to 1.0)
    confidence_score FLOAT NOT NULL,

    -- What entity this recommendation applies to
    affected_entity VARCHAR(255),  -- campaign_id, platform name, or null for account-level
    affected_entity_type affected_entity_type,

    -- Currency for monetary context
    currency VARCHAR(10),

    -- User feedback tracking
    is_accepted INTEGER NOT NULL DEFAULT 0,  -- User found this useful
    is_dismissed INTEGER NOT NULL DEFAULT 0,  -- User declined this recommendation

    -- Generation metadata
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    job_id VARCHAR(255),

    -- Determinism hash for deduplication
    content_hash VARCHAR(64) NOT NULL,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Foreign key to ai_insights
    CONSTRAINT fk_recommendations_insight
        FOREIGN KEY (related_insight_id)
        REFERENCES ai_insights(id)
        ON DELETE CASCADE
);

-- Recommendation Jobs table
-- Tracks recommendation generation job execution
CREATE TABLE IF NOT EXISTS recommendation_jobs (
    -- Primary key
    job_id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Cadence
    cadence recommendation_job_cadence NOT NULL DEFAULT 'daily',

    -- Status tracking
    status recommendation_job_status NOT NULL DEFAULT 'queued',

    -- Results
    recommendations_generated INTEGER NOT NULL DEFAULT 0,

    -- Which insights were processed
    insights_processed INTEGER NOT NULL DEFAULT 0,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error tracking
    error_message TEXT,

    -- Job metadata (insights analyzed, skip reasons, etc.)
    job_metadata JSONB DEFAULT '{}'::JSONB,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES FOR ai_recommendations
-- =============================================================================

-- Single column indexes
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_tenant_id
    ON ai_recommendations(tenant_id);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_related_insight_id
    ON ai_recommendations(related_insight_id);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_recommendation_type
    ON ai_recommendations(recommendation_type);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_priority
    ON ai_recommendations(priority);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_risk_level
    ON ai_recommendations(risk_level);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_generated_at
    ON ai_recommendations(generated_at);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_job_id
    ON ai_recommendations(job_id);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_content_hash
    ON ai_recommendations(content_hash);

-- Composite indexes for common query patterns
-- Tenant + generated_at for listing recent recommendations
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_tenant_generated
    ON ai_recommendations(tenant_id, generated_at DESC);

-- Tenant + type for filtering by recommendation type
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_tenant_type
    ON ai_recommendations(tenant_id, recommendation_type);

-- Tenant + priority for filtering by priority
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_tenant_priority
    ON ai_recommendations(tenant_id, priority);

-- Tenant + insight for getting recommendations for a specific insight
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_tenant_insight
    ON ai_recommendations(tenant_id, related_insight_id);

-- =============================================================================
-- INDEXES FOR recommendation_jobs
-- =============================================================================

-- Single column indexes
CREATE INDEX IF NOT EXISTS ix_recommendation_jobs_tenant_id
    ON recommendation_jobs(tenant_id);

CREATE INDEX IF NOT EXISTS ix_recommendation_jobs_status
    ON recommendation_jobs(status);

-- Composite indexes
-- Tenant + status for filtered status queries
CREATE INDEX IF NOT EXISTS ix_recommendation_jobs_tenant_status
    ON recommendation_jobs(tenant_id, status);

-- Tenant + created_at for finding recent jobs
CREATE INDEX IF NOT EXISTS ix_recommendation_jobs_tenant_created
    ON recommendation_jobs(tenant_id, created_at DESC);

-- =============================================================================
-- CONSTRAINTS
-- =============================================================================

-- Deduplication: prevent identical recommendations for same insight
-- Content hash + related_insight_id ensures we don't create duplicate recommendations
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ai_recommendations_dedup'
    ) THEN
        ALTER TABLE ai_recommendations ADD CONSTRAINT uq_ai_recommendations_dedup
            UNIQUE (tenant_id, content_hash, related_insight_id);
    END IF;
END
$$;

-- Partial unique index: only ONE queued/running job per tenant at a time
-- This prevents duplicate active jobs
CREATE UNIQUE INDEX IF NOT EXISTS ix_recommendation_jobs_active_unique
    ON recommendation_jobs(tenant_id)
    WHERE status IN ('queued', 'running');

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Trigger for ai_recommendations (uses shared update_updated_at_column function)
DROP TRIGGER IF EXISTS tr_ai_recommendations_updated_at ON ai_recommendations;
CREATE TRIGGER tr_ai_recommendations_updated_at
    BEFORE UPDATE ON ai_recommendations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for recommendation_jobs
DROP TRIGGER IF EXISTS tr_recommendation_jobs_updated_at ON recommendation_jobs;
CREATE TRIGGER tr_recommendation_jobs_updated_at
    BEFORE UPDATE ON recommendation_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE ai_recommendations IS 'Tactical AI recommendations derived from insights. Story 8.3. NO AUTO-EXECUTION - advisory only.';
COMMENT ON TABLE recommendation_jobs IS 'Tracks recommendation generation job execution. Story 8.3.';

COMMENT ON COLUMN ai_recommendations.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN ai_recommendations.related_insight_id IS 'FK to ai_insights - recommendations are always tied to insights';
COMMENT ON COLUMN ai_recommendations.recommendation_text IS 'Natural language using conditional phrasing (consider, may help). NO imperative language.';
COMMENT ON COLUMN ai_recommendations.estimated_impact IS 'Qualitative only - minimal/moderate/significant. No specific numbers or guarantees.';
COMMENT ON COLUMN ai_recommendations.risk_level IS 'Risk assessment - low/medium/high';
COMMENT ON COLUMN ai_recommendations.content_hash IS 'SHA256 hash of input data for deduplication';
COMMENT ON COLUMN ai_recommendations.is_accepted IS 'User feedback - did they find this recommendation useful? (0=no feedback, 1=accepted)';
COMMENT ON COLUMN ai_recommendations.is_dismissed IS 'User dismissed this recommendation (0=active, 1=dismissed)';

COMMENT ON COLUMN recommendation_jobs.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN recommendation_jobs.cadence IS 'Job cadence: daily (standard plans) or hourly (enterprise only)';
COMMENT ON COLUMN recommendation_jobs.insights_processed IS 'Number of insights analyzed to generate recommendations';
