"""
Unit tests for Airbyte workspace provisioning service.

Tests cover:
- ensure_tenant_workspace() — idempotent per-tenant workspace provisioning
- parse_db_connection_config() — DATABASE_URL parsing + env overrides
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.integrations.airbyte.exceptions import AirbyteError
from src.integrations.airbyte.models import (
    AirbyteWorkspace,
    AirbyteDestination,
)
from src.services.airbyte_workspace import (
    ensure_tenant_workspace,
    parse_db_connection_config,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_tenant(tenant_id="tenant-001", name="Acme Store", workspace_id=None):
    """Create a mock Tenant object."""
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.name = name
    tenant.airbyte_workspace_id = workspace_id
    return tenant


def _make_mock_db(tenant):
    """Create a mock SQLAlchemy session that returns the given tenant."""
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.first.return_value = tenant
    db.query.return_value = query
    return db


def _make_mock_client(workspace_id="ws-new-abc", dest_id="dest-new-xyz"):
    """Create a mock AirbyteClient with successful responses."""
    client = AsyncMock()
    client.create_workspace.return_value = AirbyteWorkspace(
        workspace_id=workspace_id,
        name="Acme Store (tenant-0)",
    )
    client.create_destination.return_value = AirbyteDestination(
        destination_id=dest_id,
        name="PostgreSQL - tenant-0",
        destination_type="destination-postgres",
        workspace_id=workspace_id,
    )
    return client


# =============================================================================
# parse_db_connection_config
# =============================================================================

class TestParseDbConnectionConfig:
    """Tests for DATABASE_URL parsing and env override behavior."""

    def test_parses_database_url(self, monkeypatch):
        """Should parse a standard postgresql:// URL correctly."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://dbuser:dbpass@db.example.com:5433/mydb",
        )
        # Clear any overrides
        for key in (
            "AIRBYTE_DESTINATION_HOST",
            "AIRBYTE_DESTINATION_PORT",
            "AIRBYTE_DESTINATION_DATABASE",
            "AIRBYTE_DESTINATION_USERNAME",
            "AIRBYTE_DESTINATION_PASSWORD",
            "AIRBYTE_DESTINATION_SCHEMA",
        ):
            monkeypatch.delenv(key, raising=False)

        config = parse_db_connection_config()

        assert config["host"] == "db.example.com"
        assert config["port"] == 5433
        assert config["database"] == "mydb"
        assert config["username"] == "dbuser"
        assert config["password"] == "dbpass"
        assert config["schema"] == "airbyte_raw"

    def test_env_overrides_take_precedence(self, monkeypatch):
        """Explicit AIRBYTE_DESTINATION_* env vars override DATABASE_URL."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://dbuser:dbpass@db.example.com:5432/mydb",
        )
        monkeypatch.setenv("AIRBYTE_DESTINATION_HOST", "override-host")
        monkeypatch.setenv("AIRBYTE_DESTINATION_PORT", "9999")
        monkeypatch.setenv("AIRBYTE_DESTINATION_DATABASE", "override-db")
        monkeypatch.setenv("AIRBYTE_DESTINATION_USERNAME", "override-user")
        monkeypatch.setenv("AIRBYTE_DESTINATION_PASSWORD", "override-pass")

        config = parse_db_connection_config()

        assert config["host"] == "override-host"
        assert config["port"] == 9999
        assert config["database"] == "override-db"
        assert config["username"] == "override-user"
        assert config["password"] == "override-pass"

    def test_defaults_when_no_url(self, monkeypatch):
        """Should fall back to localhost/postgres when DATABASE_URL is empty."""
        monkeypatch.setenv("DATABASE_URL", "")
        for key in (
            "AIRBYTE_DESTINATION_HOST",
            "AIRBYTE_DESTINATION_PORT",
            "AIRBYTE_DESTINATION_DATABASE",
            "AIRBYTE_DESTINATION_USERNAME",
            "AIRBYTE_DESTINATION_PASSWORD",
        ):
            monkeypatch.delenv(key, raising=False)

        config = parse_db_connection_config()

        assert config["host"] == "localhost"
        assert config["port"] == 5432
        assert config["database"] == "postgres"
        assert config["username"] == "postgres"
        assert config["password"] == ""

    def test_schema_from_module_var(self, monkeypatch):
        """_DESTINATION_SCHEMA (set from AIRBYTE_DESTINATION_SCHEMA env) controls schema."""
        monkeypatch.setenv("DATABASE_URL", "")
        # _DESTINATION_SCHEMA is resolved at module load time, so patch it directly
        monkeypatch.setattr(
            "src.services.airbyte_workspace._DESTINATION_SCHEMA", "custom_raw"
        )

        config = parse_db_connection_config()

        assert config["schema"] == "custom_raw"


# =============================================================================
# ensure_tenant_workspace
# =============================================================================

class TestEnsureTenantWorkspace:
    """Tests for idempotent workspace provisioning."""

    @pytest.mark.asyncio
    async def test_returns_existing_workspace_id(self):
        """If tenant already has a workspace, return it immediately — no API calls."""
        tenant = _make_mock_tenant(workspace_id="ws-existing-123")
        db = _make_mock_db(tenant)
        client = _make_mock_client()

        result = await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Acme Store",
            db=db,
            airbyte_client=client,
        )

        assert result == "ws-existing-123"
        # No Airbyte API calls should have been made
        client.create_workspace.assert_not_called()
        client.create_destination.assert_not_called()
        # DB should not have been committed (no changes)
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_provisions_new_workspace_and_destination(self, monkeypatch):
        """Full happy path: create workspace + destination + persist."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        tenant = _make_mock_tenant(workspace_id=None)
        db = _make_mock_db(tenant)
        client = _make_mock_client(workspace_id="ws-new-abc")

        result = await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Acme Store",
            db=db,
            airbyte_client=client,
        )

        assert result == "ws-new-abc"
        client.create_workspace.assert_called_once()
        client.create_destination.assert_called_once()
        db.commit.assert_called_once()
        # Verify workspace_id was persisted on tenant
        assert tenant.airbyte_workspace_id == "ws-new-abc"

    @pytest.mark.asyncio
    async def test_destination_failure_is_non_fatal(self, monkeypatch):
        """workspace_id should still be persisted even if destination creation fails."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        tenant = _make_mock_tenant(workspace_id=None)
        db = _make_mock_db(tenant)
        client = _make_mock_client(workspace_id="ws-dest-fail")
        client.create_destination.side_effect = AirbyteError("Destination creation failed")

        result = await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Acme Store",
            db=db,
            airbyte_client=client,
        )

        assert result == "ws-dest-fail"
        assert tenant.airbyte_workspace_id == "ws-dest-fail"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_tenant_not_found_raises_value_error(self):
        """Should raise ValueError if tenant record does not exist."""
        db = MagicMock()
        query = MagicMock()
        query.filter.return_value = query
        query.with_for_update.return_value = query
        query.first.return_value = None  # No tenant
        db.query.return_value = query

        with pytest.raises(ValueError, match="Tenant tenant-missing not found"):
            await ensure_tenant_workspace(
                tenant_id="tenant-missing",
                tenant_name="Ghost",
                db=db,
            )

    @pytest.mark.asyncio
    async def test_workspace_id_persisted_on_tenant_record(self, monkeypatch):
        """After provisioning, tenant.airbyte_workspace_id must be set."""
        monkeypatch.setenv("DATABASE_URL", "")
        tenant = _make_mock_tenant(workspace_id=None)
        db = _make_mock_db(tenant)
        client = _make_mock_client(workspace_id="ws-persist-test")

        await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Test Store",
            db=db,
            airbyte_client=client,
        )

        assert tenant.airbyte_workspace_id == "ws-persist-test"

    @pytest.mark.asyncio
    async def test_uses_select_for_update(self):
        """Query should use with_for_update() to prevent concurrent provisioning races."""
        tenant = _make_mock_tenant(workspace_id="ws-already")
        db = MagicMock()
        query = MagicMock()
        filter_result = MagicMock()
        for_update_result = MagicMock()
        for_update_result.first.return_value = tenant

        db.query.return_value = query
        query.filter.return_value = filter_result
        filter_result.with_for_update.return_value = for_update_result

        await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Acme Store",
            db=db,
        )

        # Verify the chain: query → filter → with_for_update → first
        db.query.assert_called_once()
        query.filter.assert_called_once()
        filter_result.with_for_update.assert_called_once()
        for_update_result.first.assert_called_once()

    @pytest.mark.asyncio
    async def test_workspace_name_includes_tenant_id_prefix(self, monkeypatch):
        """Workspace name should include tenant name and truncated ID."""
        monkeypatch.setenv("DATABASE_URL", "")
        tenant = _make_mock_tenant(
            tenant_id="abcdef12-3456-7890-abcd-ef1234567890",
            name="Cool Store",
            workspace_id=None,
        )
        db = _make_mock_db(tenant)
        client = _make_mock_client()

        await ensure_tenant_workspace(
            tenant_id="abcdef12-3456-7890-abcd-ef1234567890",
            tenant_name="Cool Store",
            db=db,
            airbyte_client=client,
        )

        call_args = client.create_workspace.call_args
        name_arg = call_args.kwargs.get("name") or call_args[0][0]
        assert "Cool Store" in name_arg
        assert "abcdef12" in name_arg

    @pytest.mark.asyncio
    async def test_destination_config_uses_postgres_type(self, monkeypatch):
        """Destination should be destination-postgres type."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
        tenant = _make_mock_tenant(workspace_id=None)
        db = _make_mock_db(tenant)
        client = _make_mock_client()

        await ensure_tenant_workspace(
            tenant_id="tenant-001",
            tenant_name="Test",
            db=db,
            airbyte_client=client,
        )

        call_args = client.create_destination.call_args
        request = call_args[0][0] if call_args[0] else call_args.kwargs.get("request")
        assert request.destination_type == "destination-postgres"
