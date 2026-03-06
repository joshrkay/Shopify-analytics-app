-- Migration: Create tenant_airbyte_connections table
-- Maps Airbyte connections to tenants for multi-tenant data source isolation.
-- Derived from SQLAlchemy model: backend/src/models/airbyte_connection.py

-- Create enum types if they don't exist
DO $$ BEGIN
    CREATE TYPE connectionstatus AS ENUM ('pending', 'active', 'inactive', 'failed', 'deleted');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE connectiontype AS ENUM ('source', 'destination');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS tenant_airbyte_connections (
    id                      VARCHAR(255)    PRIMARY KEY,
    tenant_id               VARCHAR(255)    NOT NULL,
    airbyte_connection_id   VARCHAR(255)    NOT NULL UNIQUE,
    airbyte_source_id       VARCHAR(255),
    airbyte_destination_id  VARCHAR(255),
    connection_name         VARCHAR(255)    NOT NULL,
    connection_type         connectiontype  NOT NULL DEFAULT 'source',
    source_type             VARCHAR(100),
    status                  connectionstatus NOT NULL DEFAULT 'pending',
    configuration           JSONB           DEFAULT '{}'::jsonb,
    last_sync_at            TIMESTAMP WITH TIME ZONE,
    last_sync_status        VARCHAR(50),
    sync_frequency_minutes  VARCHAR(50)     DEFAULT '60',
    is_enabled              BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes matching SQLAlchemy model __table_args__
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_airbyte_connection_id
    ON tenant_airbyte_connections (airbyte_connection_id);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_airbyte_source_id
    ON tenant_airbyte_connections (airbyte_source_id);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_airbyte_destination_id
    ON tenant_airbyte_connections (airbyte_destination_id);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_status
    ON tenant_airbyte_connections (status);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_tenant_status
    ON tenant_airbyte_connections (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_tenant_type
    ON tenant_airbyte_connections (tenant_id, connection_type);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_tenant_source
    ON tenant_airbyte_connections (tenant_id, source_type);
CREATE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_tenant_enabled
    ON tenant_airbyte_connections (tenant_id, is_enabled)
    WHERE is_enabled = TRUE;
