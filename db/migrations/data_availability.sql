-- Data Availability State Machine Schema Migration
-- Version: 1.0.0
-- Date: 2026-01-26
--
-- This migration creates the data_availability table for per-tenant, per-source
-- freshness tracking. Implements a computed state machine with three states:
--
--   FRESH:       Data within SLA threshold (warn_threshold_minutes)
--   STALE:       SLA exceeded but within grace window (error_threshold_minutes)
--   UNAVAILABLE: Beyond grace window or ingestion failed
--
-- State is derived from sync timestamps and SLA thresholds defined in
-- config/data_freshness_sla.yml — never set manually.
--
-- One row per (tenant_id, source_type) pair. Updated by
-- DataAvailabilityService.evaluate(); never written directly.
--
-- SECURITY: All rows are tenant-scoped via tenant_id from JWT.
--           RLS policies are configured separately (not in this file).
--
-- Usage: psql $DATABASE_URL -f data_availability.sql
--
-- IMPORTANT: Run the corresponding RLS migration AFTER this file to enable
--            Row-Level Security policies.

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- data_availability
-- Per-tenant, per-source data freshness state machine
-- =============================================================================

CREATE TABLE IF NOT EXISTS data_availability (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation
    tenant_id VARCHAR(255) NOT NULL,

    -- Source identification
    source_type VARCHAR(100) NOT NULL,

    -- Computed state machine fields
    state VARCHAR(20) NOT NULL,              -- fresh, stale, unavailable
    reason VARCHAR(50) NOT NULL,             -- sync_ok, sla_exceeded, grace_window_exceeded, sync_failed, never_synced

    -- SLA thresholds captured at evaluation time (for auditability)
    warn_threshold_minutes INTEGER NOT NULL,
    error_threshold_minutes INTEGER NOT NULL,

    -- Sync metadata
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(50),
    minutes_since_sync INTEGER,

    -- State transition tracking
    state_changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    previous_state VARCHAR(20),

    -- Evaluation metadata
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    billing_tier VARCHAR(50) NOT NULL DEFAULT 'free',

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Unique constraint: one row per tenant + source pair
CREATE UNIQUE INDEX IF NOT EXISTS ix_data_availability_tenant_source
    ON data_availability(tenant_id, source_type);

-- Lookup by state (e.g. find all stale/unavailable sources)
CREATE INDEX IF NOT EXISTS ix_data_availability_state
    ON data_availability(state);

-- Lookup by tenant + state (e.g. dashboard showing unhealthy sources for a tenant)
CREATE INDEX IF NOT EXISTS ix_data_availability_tenant_state
    ON data_availability(tenant_id, state);

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE data_availability IS 'Per-tenant, per-source data freshness state machine. One row per (tenant_id, source_type). State is computed by DataAvailabilityService, never set manually.';

COMMENT ON COLUMN data_availability.tenant_id IS 'Tenant identifier from JWT org_id - enforced by RLS';
COMMENT ON COLUMN data_availability.source_type IS 'SLA config source key (e.g. shopify_orders, facebook_ads)';
COMMENT ON COLUMN data_availability.state IS 'Current availability state: fresh, stale, or unavailable';
COMMENT ON COLUMN data_availability.reason IS 'Reason code for current state: sync_ok, sla_exceeded, grace_window_exceeded, sync_failed, never_synced';
COMMENT ON COLUMN data_availability.warn_threshold_minutes IS 'SLA warn threshold (minutes) used for this evaluation - captured for auditability';
COMMENT ON COLUMN data_availability.error_threshold_minutes IS 'SLA error threshold (minutes) used for this evaluation - captured for auditability';
COMMENT ON COLUMN data_availability.last_sync_at IS 'Timestamp of most recent successful sync';
COMMENT ON COLUMN data_availability.last_sync_status IS 'Status of most recent sync attempt';
COMMENT ON COLUMN data_availability.minutes_since_sync IS 'Minutes elapsed since last successful sync';
COMMENT ON COLUMN data_availability.state_changed_at IS 'Timestamp when state last transitioned';
COMMENT ON COLUMN data_availability.previous_state IS 'State before the most recent transition';
COMMENT ON COLUMN data_availability.evaluated_at IS 'Timestamp of the evaluation that produced this state';
COMMENT ON COLUMN data_availability.billing_tier IS 'Billing tier used for SLA lookup';

-- =============================================================================
-- Migration Complete
-- =============================================================================

SELECT 'data_availability schema migration completed successfully' AS status;
SELECT 'IMPORTANT: Run the corresponding RLS migration to enable Row-Level Security policies' AS next_step;
