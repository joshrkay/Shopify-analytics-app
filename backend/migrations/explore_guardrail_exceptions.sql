-- Migration: Create explore_guardrail_exceptions table
-- Story 5.4 - Explore Mode Guardrails Bypass
-- Stores time-boxed, approval-based guardrail exceptions (per user + datasets)

CREATE TABLE IF NOT EXISTS explore_guardrail_exceptions (
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    user_id VARCHAR(255) NOT NULL,
    approved_by VARCHAR(255),
    dataset_names TEXT[] NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_explore_guardrail_user
    ON explore_guardrail_exceptions(user_id);

CREATE INDEX IF NOT EXISTS idx_explore_guardrail_expires
    ON explore_guardrail_exceptions(expires_at);

CREATE INDEX IF NOT EXISTS idx_explore_guardrail_approved_by
    ON explore_guardrail_exceptions(approved_by);

-- GIN index for dataset name lookup
CREATE INDEX IF NOT EXISTS idx_explore_guardrail_datasets
    ON explore_guardrail_exceptions USING GIN (dataset_names);
