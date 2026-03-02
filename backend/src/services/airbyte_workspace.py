"""
Airbyte workspace provisioning service.

Each tenant gets their own isolated Airbyte workspace, provisioned lazily on
the first data source connection request. This module provides the single entry
point for that provisioning:

    workspace_id = await ensure_tenant_workspace(tenant_id, tenant_name, db)

The function is idempotent: if the tenant already has a workspace it is returned
immediately without any Airbyte API calls.

RACE CONDITION SAFETY: Uses SELECT FOR UPDATE to prevent two concurrent OAuth
requests from provisioning duplicate workspaces for the same tenant.

DESTINATION AUTO-PROVISIONING: After creating the workspace a PostgreSQL
destination is provisioned automatically so the OAuth callback can create
connections without manual Airbyte setup. Destination creation failure is
non-fatal — the workspace_id is still persisted and the operator can add the
destination manually via the Airbyte UI.
"""

import logging
import os
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from src.integrations.airbyte.client import AirbyteClient
from src.integrations.airbyte.exceptions import AirbyteError
from src.integrations.airbyte.models import DestinationCreationRequest

logger = logging.getLogger(__name__)

# Schema that Airbyte writes raw data into. Must match the dbt raw layer source.
_DESTINATION_SCHEMA = os.getenv("AIRBYTE_DESTINATION_SCHEMA", "airbyte_raw")


def parse_db_connection_config() -> dict:
    """
    Build the Airbyte PostgreSQL destination configuration dict.

    Precedence (highest to lowest):
    1. Explicit env vars: AIRBYTE_DESTINATION_HOST, AIRBYTE_DESTINATION_PORT,
       AIRBYTE_DESTINATION_DATABASE, AIRBYTE_DESTINATION_USERNAME,
       AIRBYTE_DESTINATION_PASSWORD
    2. Values parsed from DATABASE_URL
    3. Hardcoded fallbacks (localhost / postgres defaults)
    """
    database_url = os.getenv("DATABASE_URL", "")
    parsed = urlparse(database_url)

    host = os.getenv("AIRBYTE_DESTINATION_HOST") or parsed.hostname or "localhost"
    port = int(os.getenv("AIRBYTE_DESTINATION_PORT") or parsed.port or 5432)
    database = (
        os.getenv("AIRBYTE_DESTINATION_DATABASE")
        or (parsed.path.lstrip("/") if parsed.path else None)
        or "postgres"
    )
    username = (
        os.getenv("AIRBYTE_DESTINATION_USERNAME") or parsed.username or "postgres"
    )
    password = os.getenv("AIRBYTE_DESTINATION_PASSWORD") or parsed.password or ""

    return {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
        "schema": _DESTINATION_SCHEMA,
        "ssl_mode": {"mode": "prefer"},
        "tunnel_method": {"tunnel_method": "NO_TUNNEL"},
    }


async def ensure_tenant_workspace(
    tenant_id: str,
    tenant_name: str,
    db: Session,
    airbyte_client: Optional[AirbyteClient] = None,
) -> str:
    """
    Ensure the tenant has an Airbyte workspace provisioned.

    Idempotent: returns the existing workspace_id immediately if the tenant
    already has one (fast path, no Airbyte API calls).

    On first call for a tenant:
    1. Acquires a row-level lock (SELECT FOR UPDATE) to prevent concurrent
       provisioning races.
    2. Creates an Airbyte workspace named "<tenant_name> (<tenant_id[:8]>)".
    3. Provisions a PostgreSQL destination in the workspace pointing at the
       application database (airbyte_raw schema).
    4. Persists workspace_id on the Tenant record and commits.

    Args:
        tenant_id: Internal Tenant.id (UUID string).
        tenant_name: Display name used to label the Airbyte workspace.
        db: SQLAlchemy session (must be in an active transaction).
        airbyte_client: Optional pre-constructed client (primarily for testing).

    Returns:
        Airbyte workspace ID string.

    Raises:
        ValueError: If the tenant record is not found.
        AirbyteError: If workspace creation fails.
    """
    from src.models.tenant import Tenant

    # Acquire a row-level lock to prevent concurrent provisioning for the same tenant
    tenant = (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id)
        .with_for_update()
        .first()
    )

    if not tenant:
        raise ValueError(f"Tenant {tenant_id} not found")

    # Fast path: workspace already provisioned
    if tenant.airbyte_workspace_id:
        return tenant.airbyte_workspace_id

    client = airbyte_client or AirbyteClient()

    logger.info(
        "Provisioning Airbyte workspace for tenant",
        extra={"tenant_id": tenant_id, "tenant_name": tenant_name},
    )

    workspace = await client.create_workspace(
        name=f"{tenant_name} ({tenant_id[:8]})"
    )
    workspace_id = workspace.workspace_id

    # Provision the PostgreSQL destination — non-fatal if it fails
    try:
        db_config = parse_db_connection_config()
        dest_request = DestinationCreationRequest(
            name=f"PostgreSQL - {tenant_id[:8]}",
            destination_type="destination-postgres",
            configuration=db_config,
        )
        await client.create_destination(dest_request, workspace_id=workspace_id)
        logger.info(
            "Airbyte destination provisioned",
            extra={"tenant_id": tenant_id, "workspace_id": workspace_id},
        )
    except AirbyteError as exc:
        logger.error(
            "Failed to provision Airbyte destination — workspace created but has no destination. "
            "Add a destination manually via the Airbyte UI.",
            extra={
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "error": str(exc),
            },
        )
        # Continue — we still want to persist the workspace_id

    tenant.airbyte_workspace_id = workspace_id
    db.commit()

    logger.info(
        "Airbyte workspace provisioned and persisted",
        extra={"tenant_id": tenant_id, "workspace_id": workspace_id},
    )

    return workspace_id
