-- =============================================================================
-- Migration: Add missing columns to platform.tenant_airbyte_connections
-- =============================================================================
-- The production table was originally created via SQLAlchemy ORM auto-migration
-- before airbyte_source_id, airbyte_destination_id, source_type, last_sync_status,
-- and sync_frequency_minutes columns were added to the model.
-- This ALTER TABLE adds those columns if they don't already exist.
-- =============================================================================

ALTER TABLE tenant_airbyte_connections
    ADD COLUMN IF NOT EXISTS airbyte_source_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS airbyte_destination_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS last_sync_status VARCHAR(50),
    ADD COLUMN IF NOT EXISTS sync_frequency_minutes VARCHAR(50) DEFAULT '60';
