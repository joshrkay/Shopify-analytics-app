-- Migration: add airbyte_workspace_id to tenants
-- Each tenant gets an isolated Airbyte workspace provisioned on first data source connection.
-- The workspace_id is stored here so it can be resolved without an Airbyte API call on
-- subsequent requests.

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS airbyte_workspace_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_tenants_airbyte_workspace_id
    ON tenants (airbyte_workspace_id)
    WHERE airbyte_workspace_id IS NOT NULL;
