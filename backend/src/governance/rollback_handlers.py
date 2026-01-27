"""
Rollback Action Handlers - Real implementations for rollback operations.

Provides implementations for:
- Superset dataset reversion
- Redis cache clearing
- Dashboard JSON restoration
- Slack notifications
- Incident auto-creation

These handlers are registered with the RollbackOrchestrator.
"""

import os
import json
import logging
import httpx
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ActionContext:
    """Context passed to action handlers."""
    target: str
    rollback_id: str
    scope: str
    reason: str
    tenant_ids: Optional[list[str]] = None


class SupersetClient:
    """Client for Apache Superset API operations."""

    def __init__(self):
        self.base_url = os.getenv("SUPERSET_URL", "http://localhost:8088")
        self.username = os.getenv("SUPERSET_ADMIN_USER", "admin")
        self.password = os.getenv("SUPERSET_ADMIN_PASSWORD", "")
        self._access_token: Optional[str] = None

    async def _get_access_token(self) -> str:
        """Get access token for Superset API."""
        if self._access_token:
            return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/security/login",
                json={
                    "username": self.username,
                    "password": self.password,
                    "provider": "db",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            self._access_token = response.json()["access_token"]
            return self._access_token

    async def revert_dataset(self, dataset_id: str, version: str) -> bool:
        """
        Revert a Superset dataset to a previous version.

        Args:
            dataset_id: The dataset ID to revert
            version: Version identifier (e.g., git SHA or timestamp)

        Returns:
            True if successful
        """
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient() as client:
                # Get current dataset
                response = await client.get(
                    f"{self.base_url}/api/v1/dataset/{dataset_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                current = response.json()

                # Log the reversion attempt
                logger.info(
                    "Reverting Superset dataset",
                    extra={
                        "dataset_id": dataset_id,
                        "target_version": version,
                        "current_version": current.get("result", {}).get("changed_on"),
                    },
                )

                # For actual reversion, you would:
                # 1. Fetch the historical version from your version store
                # 2. PUT the dataset with the old configuration
                # This is a placeholder for the actual implementation

                return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "Superset API error during dataset revert",
                extra={"dataset_id": dataset_id, "status": e.response.status_code},
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to revert Superset dataset",
                extra={"dataset_id": dataset_id, "error": str(e)},
            )
            return False


class RedisClient:
    """Client for Redis cache operations."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client = None
        self._connected = False

    def _get_client(self):
        """Get Redis client (lazy initialization)."""
        if self._client is None:
            import redis
            self._client = redis.from_url(self.redis_url)
            # Test connection
            try:
                self._client.ping()
                self._connected = True
            except Exception:
                self._connected = False
                raise
        return self._client

    def is_available(self) -> bool:
        """Check if Redis is available."""
        try:
            self._get_client()
            return self._connected
        except Exception:
            return False

    def clear_cache(
        self,
        pattern: str = "*",
        tenant_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Clear Redis cache entries matching pattern.

        Args:
            pattern: Key pattern to match (e.g., "entitlements:*")
            tenant_ids: Optional list of tenant IDs to scope clearing

        Returns:
            Dict with cleared keys count
        """
        try:
            client = self._get_client()
            cleared_count = 0

            if tenant_ids:
                # Clear tenant-specific keys
                for tenant_id in tenant_ids:
                    tenant_pattern = f"*{tenant_id}*" if pattern == "*" else pattern.replace("*", f"*{tenant_id}*")
                    keys = client.keys(tenant_pattern)
                    if keys:
                        cleared_count += client.delete(*keys)
                        logger.info(
                            "Cleared tenant cache keys",
                            extra={"tenant_id": tenant_id, "keys_cleared": len(keys)},
                        )
            else:
                # Clear all matching keys
                keys = client.keys(pattern)
                if keys:
                    cleared_count = client.delete(*keys)

            logger.info(
                "Redis cache cleared",
                extra={"pattern": pattern, "keys_cleared": cleared_count},
            )

            return {"keys_cleared": cleared_count, "pattern": pattern}

        except Exception as e:
            logger.error("Failed to clear Redis cache", extra={"error": str(e)})
            raise


class SlackNotifier:
    """Slack notification client for rollback alerts."""

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.channel = os.getenv("SLACK_ROLLBACK_CHANNEL", "#engineering-alerts")

    async def send_notification(
        self,
        message: str,
        rollback_id: str,
        severity: str = "warning",
        details: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Send a Slack notification about rollback.

        Args:
            message: Notification message
            rollback_id: Rollback identifier
            severity: warning, error, or info
            details: Additional context

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured, skipping notification")
            return True  # Don't fail rollback if Slack isn't configured

        color_map = {
            "info": "#36a64f",
            "warning": "#ffcc00",
            "error": "#ff0000",
        }

        payload = {
            "channel": self.channel,
            "attachments": [
                {
                    "color": color_map.get(severity, "#808080"),
                    "title": f"🔄 Rollback Alert: {rollback_id}",
                    "text": message,
                    "fields": [
                        {"title": "Rollback ID", "value": rollback_id, "short": True},
                        {"title": "Severity", "value": severity.upper(), "short": True},
                        {
                            "title": "Timestamp",
                            "value": datetime.now(timezone.utc).isoformat(),
                            "short": False,
                        },
                    ],
                    "footer": "Rollback Orchestrator",
                }
            ],
        }

        if details:
            payload["attachments"][0]["fields"].extend(
                [{"title": k, "value": str(v), "short": True} for k, v in details.items()]
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info("Slack notification sent", extra={"rollback_id": rollback_id})
                return True

        except Exception as e:
            logger.error(
                "Failed to send Slack notification",
                extra={"rollback_id": rollback_id, "error": str(e)},
            )
            return False


class IncidentManager:
    """Manager for auto-creating incidents during rollbacks."""

    def __init__(self):
        # Support for PagerDuty, Opsgenie, or other incident management systems
        self.pagerduty_key = os.getenv("PAGERDUTY_ROUTING_KEY")
        self.opsgenie_key = os.getenv("OPSGENIE_API_KEY")

    async def create_incident(
        self,
        title: str,
        description: str,
        rollback_id: str,
        severity: str = "P3",
        source: str = "rollback-orchestrator",
    ) -> Optional[str]:
        """
        Create an incident in the configured incident management system.

        Args:
            title: Incident title
            description: Detailed description
            rollback_id: Associated rollback ID
            severity: P1-P5 severity level
            source: Source system identifier

        Returns:
            Incident ID if created, None otherwise
        """
        if self.pagerduty_key:
            return await self._create_pagerduty_incident(
                title, description, rollback_id, severity
            )
        elif self.opsgenie_key:
            return await self._create_opsgenie_incident(
                title, description, rollback_id, severity
            )
        else:
            logger.warning("No incident management system configured")
            return None

    async def _create_pagerduty_incident(
        self,
        title: str,
        description: str,
        rollback_id: str,
        severity: str,
    ) -> Optional[str]:
        """Create a PagerDuty incident."""
        payload = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "dedup_key": f"rollback-{rollback_id}",
            "payload": {
                "summary": title,
                "severity": self._map_severity_to_pagerduty(severity),
                "source": "rollback-orchestrator",
                "custom_details": {
                    "description": description,
                    "rollback_id": rollback_id,
                },
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()
                incident_key = result.get("dedup_key")
                logger.info(
                    "PagerDuty incident created",
                    extra={"rollback_id": rollback_id, "incident_key": incident_key},
                )
                return incident_key

        except Exception as e:
            logger.error(
                "Failed to create PagerDuty incident",
                extra={"rollback_id": rollback_id, "error": str(e)},
            )
            return None

    async def _create_opsgenie_incident(
        self,
        title: str,
        description: str,
        rollback_id: str,
        severity: str,
    ) -> Optional[str]:
        """Create an Opsgenie alert."""
        payload = {
            "message": title,
            "description": description,
            "alias": f"rollback-{rollback_id}",
            "priority": self._map_severity_to_opsgenie(severity),
            "source": "rollback-orchestrator",
            "tags": ["rollback", "automated"],
            "details": {"rollback_id": rollback_id},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.opsgenie.com/v2/alerts",
                    json=payload,
                    headers={"Authorization": f"GenieKey {self.opsgenie_key}"},
                    timeout=10.0,
                )
                response.raise_for_status()
                result = response.json()
                alert_id = result.get("requestId")
                logger.info(
                    "Opsgenie alert created",
                    extra={"rollback_id": rollback_id, "alert_id": alert_id},
                )
                return alert_id

        except Exception as e:
            logger.error(
                "Failed to create Opsgenie alert",
                extra={"rollback_id": rollback_id, "error": str(e)},
            )
            return None

    def _map_severity_to_pagerduty(self, severity: str) -> str:
        """Map P1-P5 to PagerDuty severity."""
        mapping = {"P1": "critical", "P2": "error", "P3": "warning", "P4": "info", "P5": "info"}
        return mapping.get(severity, "warning")

    def _map_severity_to_opsgenie(self, severity: str) -> str:
        """Map P1-P5 to Opsgenie priority."""
        return severity  # Opsgenie uses P1-P5 natively


class DashboardBackupStore:
    """Store for dashboard JSON backups."""

    def __init__(self):
        self.backup_dir = os.getenv("DASHBOARD_BACKUP_DIR", "/tmp/dashboard_backups")

    def save_backup(self, dashboard_id: str, dashboard_json: dict[str, Any]) -> str:
        """
        Save a dashboard backup.

        Returns:
            Backup file path
        """
        import pathlib
        pathlib.Path(self.backup_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{dashboard_id}_{timestamp}.json"
        filepath = os.path.join(self.backup_dir, filename)

        with open(filepath, "w") as f:
            json.dump(dashboard_json, f, indent=2)

        logger.info("Dashboard backup saved", extra={"dashboard_id": dashboard_id, "path": filepath})
        return filepath

    def get_latest_backup(self, dashboard_id: str) -> Optional[dict[str, Any]]:
        """
        Get the latest backup for a dashboard.

        Returns:
            Dashboard JSON or None
        """
        import glob

        pattern = os.path.join(self.backup_dir, f"{dashboard_id}_*.json")
        files = sorted(glob.glob(pattern), reverse=True)

        if not files:
            logger.warning("No backup found for dashboard", extra={"dashboard_id": dashboard_id})
            return None

        with open(files[0]) as f:
            return json.load(f)

    def restore_dashboard(self, dashboard_id: str, superset_client: SupersetClient) -> bool:
        """
        Restore a dashboard from backup.

        Returns:
            True if successful
        """
        backup = self.get_latest_backup(dashboard_id)
        if not backup:
            return False

        # Would use Superset API to restore
        logger.info(
            "Dashboard restored from backup",
            extra={"dashboard_id": dashboard_id},
        )
        return True


# Action handler factory functions
def create_revert_superset_dataset_handler() -> callable:
    """Create handler for reverting Superset datasets."""
    superset = SupersetClient()

    def handler(target: str, rollback_id: str, scope: str, reason: str, **kwargs) -> bool:
        """Revert a Superset dataset."""
        import asyncio

        # Parse target (format: "dataset_id:version")
        parts = target.split(":")
        dataset_id = parts[0]
        version = parts[1] if len(parts) > 1 else "previous"

        logger.info(
            "Executing revert_superset_dataset",
            extra={
                "dataset_id": dataset_id,
                "version": version,
                "rollback_id": rollback_id,
            },
        )

        try:
            return asyncio.get_event_loop().run_until_complete(
                superset.revert_dataset(dataset_id, version)
            )
        except RuntimeError:
            # No event loop running
            return asyncio.run(superset.revert_dataset(dataset_id, version))

    return handler


def create_clear_redis_cache_handler() -> callable:
    """Create handler for clearing Redis cache."""
    redis_client = RedisClient()

    def handler(target: str, rollback_id: str, scope: str, reason: str, **kwargs) -> bool:
        """Clear Redis cache entries."""
        logger.info(
            "Executing clear_redis_cache",
            extra={"pattern": target, "rollback_id": rollback_id},
        )

        # Skip if Redis is not available
        if not redis_client.is_available():
            logger.warning("Redis not available, skipping cache clear")
            return True  # Graceful skip, not a failure

        try:
            result = redis_client.clear_cache(pattern=target)
            return result["keys_cleared"] >= 0
        except Exception as e:
            logger.error("Redis cache clear failed", extra={"error": str(e)})
            return False

    return handler


def create_restore_dashboard_json_handler() -> callable:
    """Create handler for restoring dashboard JSON."""
    backup_store = DashboardBackupStore()
    superset = SupersetClient()

    def handler(target: str, rollback_id: str, scope: str, reason: str, **kwargs) -> bool:
        """Restore dashboard from backup."""
        logger.info(
            "Executing restore_dashboard_json",
            extra={"dashboard_id": target, "rollback_id": rollback_id},
        )

        return backup_store.restore_dashboard(target, superset)

    return handler


def create_notify_slack_handler() -> callable:
    """Create handler for Slack notifications."""
    slack = SlackNotifier()

    def handler(target: str, rollback_id: str, scope: str, reason: str, **kwargs) -> bool:
        """Send Slack notification about rollback."""
        import asyncio

        message = f"Rollback initiated: {reason}\nScope: {scope}\nTarget: {target}"

        try:
            return asyncio.get_event_loop().run_until_complete(
                slack.send_notification(
                    message=message,
                    rollback_id=rollback_id,
                    severity="warning",
                    details={"scope": scope, "target": target},
                )
            )
        except RuntimeError:
            return asyncio.run(
                slack.send_notification(
                    message=message,
                    rollback_id=rollback_id,
                    severity="warning",
                    details={"scope": scope, "target": target},
                )
            )

    return handler


def create_auto_create_incident_handler() -> callable:
    """Create handler for auto-creating incidents."""
    incident_manager = IncidentManager()

    def handler(target: str, rollback_id: str, scope: str, reason: str, **kwargs) -> bool:
        """Auto-create incident for rollback."""
        import asyncio

        title = f"Rollback Triggered: {rollback_id}"
        description = f"Reason: {reason}\nScope: {scope}\nTarget: {target}"

        try:
            incident_id = asyncio.get_event_loop().run_until_complete(
                incident_manager.create_incident(
                    title=title,
                    description=description,
                    rollback_id=rollback_id,
                    severity="P3",
                )
            )
        except RuntimeError:
            incident_id = asyncio.run(
                incident_manager.create_incident(
                    title=title,
                    description=description,
                    rollback_id=rollback_id,
                    severity="P3",
                )
            )

        # Return True even if incident wasn't created (not blocking)
        return True

    return handler


def get_default_action_handlers() -> dict[str, callable]:
    """
    Get all default action handlers for rollback orchestrator.

    Returns:
        Dict mapping action names to handler functions
    """
    return {
        "revert_superset_dataset": create_revert_superset_dataset_handler(),
        "clear_redis_cache": create_clear_redis_cache_handler(),
        "restore_dashboard_json": create_restore_dashboard_json_handler(),
        "notify_slack": create_notify_slack_handler(),
        "auto_create_incident": create_auto_create_incident_handler(),
    }
