"""
Airbyte API client for data synchronization management.

Supports both Airbyte OSS (self-hosted) and Airbyte Cloud:
- OSS: Basic auth via AIRBYTE_USERNAME / AIRBYTE_PASSWORD
- Cloud: Bearer token via AIRBYTE_API_TOKEN

This client handles:
- Health checks for Airbyte availability
- Workspace management (create, per-tenant provisioning)
- Connection management (list, get)
- Source and destination management
- Sync job orchestration (trigger, status, wait)

Note: OAuth flows are handled by oauth_registry.py (app-managed per-provider) — not
delegated to the Airbyte API, which only supports OAuth delegation on Airbyte Cloud.

Documentation: https://reference.airbyte.com/
"""

import asyncio
import base64
import logging
import os
import time
from typing import Optional, List, Dict, Any

import httpx

from src.integrations.airbyte.exceptions import (
    AirbyteError,
    AirbyteAuthenticationError,
    AirbyteRateLimitError,
    AirbyteConnectionError,
    AirbyteSyncError,
    AirbyteNotFoundError,
)
from src.integrations.airbyte.models import (
    AirbyteHealth,
    AirbyteConnection,
    AirbyteJob,
    AirbyteSyncResult,
    AirbyteSource,
    AirbyteDestination,
    AirbyteWorkspace,
    SourceCreationRequest,
    ConnectionCreationRequest,
    DestinationCreationRequest,
)

logger = logging.getLogger(__name__)

# Default configuration.
# OSS deployments typically expose the public API at one of:
#   http://<host>:8006/v1        (airbyte-api-server container, Airbyte >= 0.50)
#   http://<host>:8000/api/public/v1  (nginx proxy path)
# Cloud: https://api.airbyte.com/v1
# Set AIRBYTE_BASE_URL to match your deployment.
DEFAULT_BASE_URL = "https://api.airbyte.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_SYNC_TIMEOUT_SECONDS = 3600
DEFAULT_POLL_INTERVAL_SECONDS = 30


class AirbyteClient:
    """
    Async client for the Airbyte API (OSS and Cloud).

    Authentication modes (checked in order):
    1. Basic auth — set AIRBYTE_USERNAME + AIRBYTE_PASSWORD (Airbyte OSS default)
    2. Bearer token — set AIRBYTE_API_TOKEN (Airbyte Cloud / OSS with token auth)

    workspace_id is optional in the constructor. When not set the instance
    has no default workspace; callers pass workspace_id per-call. This
    supports the per-tenant workspace model where workspace IDs are stored
    on Tenant records and resolved at call sites.

    SECURITY: Credentials must be stored securely and never logged.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        workspace_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ):
        """
        Initialize Airbyte client.

        Args:
            base_url: API base URL (default: from AIRBYTE_BASE_URL env or Cloud URL)
            api_token: Bearer token for authentication (default: from AIRBYTE_API_TOKEN env)
            workspace_id: Optional default workspace ID (default: from AIRBYTE_WORKSPACE_ID env).
                          Per-tenant workspace IDs are passed explicitly per call instead.
            username: Basic auth username (default: from AIRBYTE_USERNAME env)
            password: Basic auth password (default: from AIRBYTE_PASSWORD env)
            timeout: Request timeout in seconds
            connect_timeout: Connection timeout in seconds

        Raises:
            ValueError: If neither Basic auth credentials nor a Bearer token are configured
        """
        self.base_url = (
            base_url or os.getenv("AIRBYTE_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

        # workspace_id is optional — per-tenant model stores it on the Tenant record
        self.workspace_id = workspace_id or os.getenv("AIRBYTE_WORKSPACE_ID")

        # Resolve auth header — Basic auth takes precedence over Bearer token
        _username = username or os.getenv("AIRBYTE_USERNAME")
        _password = password or os.getenv("AIRBYTE_PASSWORD")

        if _username and _password:
            credentials = base64.b64encode(
                f"{_username}:{_password}".encode()
            ).decode()
            auth_header = f"Basic {credentials}"
        else:
            self.api_token = api_token or os.getenv("AIRBYTE_API_TOKEN")
            if not self.api_token:
                raise ValueError(
                    "Airbyte authentication is required. Set either "
                    "AIRBYTE_USERNAME + AIRBYTE_PASSWORD (Airbyte OSS Basic auth) "
                    "or AIRBYTE_API_TOKEN (Bearer token for Cloud / OSS token auth)."
                )
            auth_header = f"Bearer {self.api_token}"

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": auth_header,
            },
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "AirbyteClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the Airbyte API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json: Request body as JSON
            params: Query parameters

        Returns:
            Response data as dictionary

        Raises:
            AirbyteError: On API errors
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json,
                params=params,
            )

            if response.status_code == 401:
                logger.error(
                    "Airbyte API authentication failed",
                    extra={"status_code": 401, "endpoint": endpoint},
                )
                raise AirbyteAuthenticationError()

            if response.status_code == 403:
                logger.error(
                    "Airbyte API authorization failed",
                    extra={"status_code": 403, "endpoint": endpoint},
                )
                raise AirbyteAuthenticationError(
                    message="Authorization failed - token may lack required permissions",
                    status_code=403,
                )

            if response.status_code == 404:
                raise AirbyteNotFoundError(
                    message=f"Resource not found: {endpoint}",
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                logger.warning(
                    "Airbyte API rate limited",
                    extra={
                        "endpoint": endpoint,
                        "retry_after": retry_after,
                    },
                )
                raise AirbyteRateLimitError(
                    retry_after=int(retry_after) if retry_after else None
                )

            if response.status_code >= 400:
                error_body = {}
                try:
                    error_body = response.json()
                except Exception:
                    pass

                logger.error(
                    "Airbyte API error",
                    extra={
                        "status_code": response.status_code,
                        "endpoint": endpoint,
                        "response": str(error_body)[:500],
                    },
                )
                raise AirbyteError(
                    message=f"Airbyte API error: {response.status_code}",
                    status_code=response.status_code,
                    response=error_body,
                )

            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.TimeoutException as e:
            logger.error(
                "Airbyte API timeout",
                extra={"endpoint": endpoint, "error": str(e)},
            )
            raise AirbyteConnectionError(f"Request timeout: {e}")
        except httpx.RequestError as e:
            logger.error(
                "Airbyte API connection error",
                extra={"endpoint": endpoint, "error": str(e)},
            )
            raise AirbyteConnectionError(f"Connection error: {e}")

    async def check_health(self) -> AirbyteHealth:
        """
        Check Airbyte API health status.

        Returns:
            AirbyteHealth with availability status

        Raises:
            AirbyteError: On API errors
        """
        data = await self._request("GET", "/health")
        return AirbyteHealth.from_dict(data)

    async def list_connections(
        self,
        workspace_id: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[AirbyteConnection]:
        """
        List all connections in the workspace.

        Args:
            workspace_id: Override workspace ID (uses default if not provided)
            include_deleted: Include deleted connections

        Returns:
            List of AirbyteConnection objects

        Raises:
            AirbyteError: On API errors
        """
        ws_id = workspace_id or self.workspace_id

        params = {"workspaceIds": ws_id}
        if include_deleted:
            params["includeDeleted"] = "true"

        data = await self._request("GET", "/connections", params=params)

        connections = []
        for conn_data in data.get("data", []):
            connections.append(AirbyteConnection.from_dict(conn_data))

        logger.debug(
            "Listed Airbyte connections",
            extra={
                "workspace_id": ws_id,
                "connection_count": len(connections),
            },
        )

        return connections

    async def get_connection(self, connection_id: str) -> AirbyteConnection:
        """
        Get a specific connection by ID.

        Args:
            connection_id: Connection UUID

        Returns:
            AirbyteConnection object

        Raises:
            AirbyteNotFoundError: If connection not found
            AirbyteError: On other API errors
        """
        data = await self._request("GET", f"/connections/{connection_id}")
        return AirbyteConnection.from_dict(data)

    async def trigger_sync(self, connection_id: str) -> str:
        """
        Trigger a manual sync for a connection.

        Uses POST /jobs per the Airbyte Public API spec (not the deprecated
        POST /connections/{id}/sync from the old Config API).

        Args:
            connection_id: Connection UUID

        Returns:
            Job ID for the triggered sync

        Raises:
            AirbyteError: On API errors
        """
        data = await self._request(
            "POST",
            "/jobs",
            json={"connectionId": connection_id, "jobType": "sync"},
        )

        job_id = str(data.get("jobId", ""))

        logger.info(
            "Airbyte sync triggered",
            extra={
                "connection_id": connection_id,
                "job_id": job_id,
            },
        )

        return job_id

    async def get_job(self, job_id: str) -> AirbyteJob:
        """
        Get job status and details.

        Args:
            job_id: Job ID

        Returns:
            AirbyteJob object

        Raises:
            AirbyteError: On API errors
        """
        data = await self._request("GET", f"/jobs/{job_id}")
        return AirbyteJob.from_dict(data)

    async def cancel_job(self, job_id: str) -> AirbyteJob:
        """
        Cancel a running job.

        Args:
            job_id: Job ID to cancel

        Returns:
            Updated AirbyteJob object

        Raises:
            AirbyteError: On API errors
        """
        data = await self._request("DELETE", f"/jobs/{job_id}")

        logger.info(
            "Airbyte job cancelled",
            extra={"job_id": job_id},
        )

        return AirbyteJob.from_dict(data)

    async def wait_for_sync(
        self,
        job_id: str,
        timeout_seconds: float = DEFAULT_SYNC_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        connection_id: Optional[str] = None,
    ) -> AirbyteSyncResult:
        """
        Wait for a sync job to complete.

        Args:
            job_id: Job ID to monitor
            timeout_seconds: Maximum wait time
            poll_interval_seconds: Interval between status checks
            connection_id: Optional connection ID for logging

        Returns:
            AirbyteSyncResult with final status

        Raises:
            AirbyteSyncError: On timeout or job failure
            AirbyteError: On API errors
        """
        start_time = time.time()

        logger.info(
            "Waiting for Airbyte sync",
            extra={
                "job_id": job_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            },
        )

        while True:
            elapsed = time.time() - start_time

            if elapsed >= timeout_seconds:
                raise AirbyteSyncError(
                    message=f"Sync timed out after {timeout_seconds} seconds",
                    job_id=job_id,
                    connection_id=connection_id,
                )

            job = await self.get_job(job_id)

            if job.is_complete:
                duration = time.time() - start_time

                records_synced = 0
                bytes_synced = 0
                if job.attempts:
                    last_attempt = job.attempts[-1]
                    records_synced = last_attempt.records_synced
                    bytes_synced = last_attempt.bytes_synced

                result = AirbyteSyncResult(
                    job_id=job_id,
                    status=job.status,
                    connection_id=connection_id or job.config_id,
                    records_synced=records_synced,
                    bytes_synced=bytes_synced,
                    duration_seconds=duration,
                )

                if job.is_successful:
                    logger.info(
                        "Airbyte sync completed successfully",
                        extra={
                            "job_id": job_id,
                            "connection_id": connection_id,
                            "records_synced": records_synced,
                            "bytes_synced": bytes_synced,
                            "duration_seconds": duration,
                        },
                    )
                else:
                    logger.warning(
                        "Airbyte sync completed with status",
                        extra={
                            "job_id": job_id,
                            "connection_id": connection_id,
                            "status": job.status.value,
                            "duration_seconds": duration,
                        },
                    )

                return result

            logger.debug(
                "Airbyte sync still running",
                extra={
                    "job_id": job_id,
                    "status": job.status.value,
                    "elapsed_seconds": elapsed,
                },
            )

            await asyncio.sleep(poll_interval_seconds)

    async def sync_and_wait(
        self,
        connection_id: str,
        timeout_seconds: float = DEFAULT_SYNC_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> AirbyteSyncResult:
        """
        Trigger a sync and wait for completion.

        Convenience method that combines trigger_sync and wait_for_sync.

        Args:
            connection_id: Connection to sync
            timeout_seconds: Maximum wait time
            poll_interval_seconds: Interval between status checks

        Returns:
            AirbyteSyncResult with final status

        Raises:
            AirbyteSyncError: On timeout or job failure
            AirbyteError: On API errors
        """
        job_id = await self.trigger_sync(connection_id)
        return await self.wait_for_sync(
            job_id=job_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            connection_id=connection_id,
        )

    # =========================================================================
    # Source Management Methods
    # =========================================================================

    async def create_source(
        self,
        request: SourceCreationRequest,
        workspace_id: Optional[str] = None,
    ) -> AirbyteSource:
        """
        Create a new source in Airbyte.

        Args:
            request: Source creation request with configuration
            workspace_id: Override workspace ID (uses default if not provided)

        Returns:
            Created AirbyteSource object

        Raises:
            AirbyteError: On API errors
        """
        ws_id = workspace_id or self.workspace_id

        data = await self._request(
            "POST",
            "/sources",
            json=request.to_dict(ws_id),
        )

        source = AirbyteSource.from_dict(data)

        logger.info(
            "Airbyte source created",
            extra={
                "source_id": source.source_id,
                "source_type": source.source_type,
                "source_name": source.name,  # 'name' is reserved in LogRecord
            },
        )

        return source

    async def get_source(self, source_id: str) -> AirbyteSource:
        """
        Get a specific source by ID.

        Args:
            source_id: Source UUID

        Returns:
            AirbyteSource object

        Raises:
            AirbyteNotFoundError: If source not found
            AirbyteError: On other API errors
        """
        data = await self._request("GET", f"/sources/{source_id}")
        return AirbyteSource.from_dict(data)

    async def check_source_connection(self, source_id: str) -> Dict[str, Any]:
        """
        Test connectivity for an existing source.

        Calls Airbyte's check_connection endpoint which validates
        that credentials are valid and the external platform is reachable.

        Args:
            source_id: Source UUID to test

        Returns:
            Dict with 'status' ('succeeded'/'failed') and optional 'message'

        Raises:
            AirbyteNotFoundError: If source not found
            AirbyteError: On other API errors
        """
        data = await self._request(
            "POST",
            "/sources/check_connection",
            json={"sourceId": source_id},
        )
        return data

    async def list_sources(
        self,
        workspace_id: Optional[str] = None,
    ) -> List[AirbyteSource]:
        """
        List all sources in the workspace.

        Args:
            workspace_id: Override workspace ID (uses default if not provided)

        Returns:
            List of AirbyteSource objects

        Raises:
            AirbyteError: On API errors
        """
        ws_id = workspace_id or self.workspace_id

        data = await self._request(
            "GET",
            "/sources",
            params={"workspaceIds": ws_id},
        )

        sources = []
        for source_data in data.get("data", []):
            sources.append(AirbyteSource.from_dict(source_data))

        return sources

    async def delete_source(self, source_id: str) -> None:
        """
        Delete a source.

        Args:
            source_id: Source UUID to delete

        Raises:
            AirbyteError: On API errors
        """
        await self._request("DELETE", f"/sources/{source_id}")

        logger.info(
            "Airbyte source deleted",
            extra={"source_id": source_id},
        )

    # =========================================================================
    # Destination Management Methods
    # =========================================================================

    async def get_destination(self, destination_id: str) -> AirbyteDestination:
        """
        Get a specific destination by ID.

        Args:
            destination_id: Destination UUID

        Returns:
            AirbyteDestination object

        Raises:
            AirbyteNotFoundError: If destination not found
            AirbyteError: On other API errors
        """
        data = await self._request("GET", f"/destinations/{destination_id}")
        return AirbyteDestination.from_dict(data)

    async def list_destinations(
        self,
        workspace_id: Optional[str] = None,
    ) -> List[AirbyteDestination]:
        """
        List all destinations in the workspace.

        Args:
            workspace_id: Override workspace ID (uses default if not provided)

        Returns:
            List of AirbyteDestination objects

        Raises:
            AirbyteError: On API errors
        """
        ws_id = workspace_id or self.workspace_id

        data = await self._request(
            "GET",
            "/destinations",
            params={"workspaceIds": ws_id},
        )

        destinations = []
        for dest_data in data.get("data", []):
            destinations.append(AirbyteDestination.from_dict(dest_data))

        return destinations

    # =========================================================================
    # Connection Creation Methods
    # =========================================================================

    async def create_connection(
        self,
        request: ConnectionCreationRequest,
    ) -> AirbyteConnection:
        """
        Create a new connection between source and destination.

        Args:
            request: Connection creation request

        Returns:
            Created AirbyteConnection object

        Raises:
            AirbyteError: On API errors
        """
        data = await self._request(
            "POST",
            "/connections",
            json=request.to_dict(),
        )

        connection = AirbyteConnection.from_dict(data)

        logger.info(
            "Airbyte connection created",
            extra={
                "connection_id": connection.connection_id,
                "source_id": connection.source_id,
                "destination_id": connection.destination_id,
                "connection_name": connection.name,  # 'name' is reserved in LogRecord
            },
        )

        return connection

    async def delete_connection(self, connection_id: str) -> None:
        """
        Delete a connection.

        Args:
            connection_id: Connection UUID to delete

        Raises:
            AirbyteError: On API errors
        """
        await self._request("DELETE", f"/connections/{connection_id}")

        logger.info(
            "Airbyte connection deleted",
            extra={"connection_id": connection_id},
        )

    # =========================================================================
    # Workspace Management Methods
    # =========================================================================

    async def create_workspace(
        self,
        name: str,
        organization_id: Optional[str] = None,
    ) -> AirbyteWorkspace:
        """
        Create a new Airbyte workspace.

        Used for per-tenant workspace provisioning. Each tenant gets an
        isolated workspace so their sources and connections are fully
        separated from other tenants.

        Args:
            name: Human-readable workspace name (e.g. "Acme Store (abc12345)")
            organization_id: Optional Airbyte organization ID to associate with

        Returns:
            Created AirbyteWorkspace

        Raises:
            AirbyteError: On API errors
        """
        payload: Dict[str, Any] = {"name": name}
        if organization_id:
            payload["organizationId"] = organization_id

        data = await self._request("POST", "/workspaces", json=payload)
        workspace = AirbyteWorkspace.from_dict(data)

        logger.info(
            "Airbyte workspace created",
            extra={"workspace_id": workspace.workspace_id, "workspace_name": name},  # 'name' is reserved in LogRecord
        )

        return workspace

    async def create_destination(
        self,
        request: DestinationCreationRequest,
        workspace_id: Optional[str] = None,
    ) -> AirbyteDestination:
        """
        Create a new destination in an Airbyte workspace.

        Used during workspace provisioning to add the PostgreSQL destination
        that all sources in the workspace sync into.

        Args:
            request: Destination creation request (type + configuration)
            workspace_id: Target workspace ID (uses default if not provided)

        Returns:
            Created AirbyteDestination

        Raises:
            AirbyteError: On API errors
        """
        ws_id = workspace_id or self.workspace_id

        data = await self._request(
            "POST",
            "/destinations",
            json=request.to_dict(ws_id),
        )
        destination = AirbyteDestination.from_dict(data)

        logger.info(
            "Airbyte destination created",
            extra={
                "destination_id": destination.destination_id,
                "destination_type": destination.destination_type,
                "workspace_id": ws_id,
            },
        )

        return destination


def get_airbyte_client(
    base_url: Optional[str] = None,
    api_token: Optional[str] = None,
    workspace_id: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> AirbyteClient:
    """
    Factory function to create an AirbyteClient.

    Auth is resolved automatically from environment variables when not passed:
    - Basic auth: AIRBYTE_USERNAME + AIRBYTE_PASSWORD (Airbyte OSS)
    - Bearer token: AIRBYTE_API_TOKEN (Airbyte Cloud / OSS token auth)

    workspace_id is optional — the per-tenant model resolves workspace IDs
    from Tenant records and passes them explicitly to each call.

    Args:
        base_url: Override API base URL (default: AIRBYTE_BASE_URL env)
        api_token: Override Bearer token (default: AIRBYTE_API_TOKEN env)
        workspace_id: Optional default workspace ID (default: AIRBYTE_WORKSPACE_ID env)
        username: Override Basic auth username (default: AIRBYTE_USERNAME env)
        password: Override Basic auth password (default: AIRBYTE_PASSWORD env)

    Returns:
        Configured AirbyteClient instance
    """
    return AirbyteClient(
        base_url=base_url,
        api_token=api_token,
        workspace_id=workspace_id,
        username=username,
        password=password,
    )
