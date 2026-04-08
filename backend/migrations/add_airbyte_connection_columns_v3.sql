-- =============================================================================
-- Migration: Add ALL remaining missing columns to platform.tenant_airbyte_connections
-- =============================================================================
-- The production table was created by SQLAlchemy ORM before several columns
-- were added to the model. Previous migrations (v2) added some columns but
-- missed connection_type (an enum) and configuration.
--
-- This migration idempotently adds any remaining missing columns.
-- =============================================================================

-- Ensure enum types exist (idempotent)
DO $$ BEGIN
    CREATE TYPE connectionstatus AS ENUM ('pending', 'active', 'inactive', 'failed', 'deleted');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE connectiontype AS ENUM ('source', 'destination');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Add all potentially missing columns to the platform-schema table
ALTER TABLE platform.tenant_airbyte_connections
    ADD COLUMN IF NOT EXISTS connection_type connectiontype NOT NULL DEFAULT 'source',
    ADD COLUMN IF NOT EXISTS configuration JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
