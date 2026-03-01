"""
Airbyte integration for data ingestion.

Supports both Airbyte OSS (self-hosted, Basic auth) and Airbyte Cloud (Bearer token).
Provides a client for managing workspaces, sources, destinations, connections,
and sync jobs.
"""

from src.integrations.airbyte.client import AirbyteClient, get_airbyte_client
from src.integrations.airbyte.exceptions import (
    AirbyteError,
    AirbyteAuthenticationError,
    AirbyteRateLimitError,
    AirbyteConnectionError,
    AirbyteSyncError,
)
from src.integrations.airbyte.models import (
    AirbyteHealth,
    AirbyteConnection,
    AirbyteJob,
    AirbyteJobStatus,
    AirbyteSyncResult,
    AirbyteWorkspace,
    DestinationCreationRequest,
)

__all__ = [
    # Client
    "AirbyteClient",
    "get_airbyte_client",
    # Exceptions
    "AirbyteError",
    "AirbyteAuthenticationError",
    "AirbyteRateLimitError",
    "AirbyteConnectionError",
    "AirbyteSyncError",
    # Models
    "AirbyteHealth",
    "AirbyteConnection",
    "AirbyteJob",
    "AirbyteJobStatus",
    "AirbyteSyncResult",
    "AirbyteWorkspace",
    "DestinationCreationRequest",
]
