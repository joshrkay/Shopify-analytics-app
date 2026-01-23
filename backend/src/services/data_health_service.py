"""
Data freshness and health monitoring service.

Provides health indicators for data sources, tracking:
- Last successful sync timestamp
- Freshness status (fresh/stale/never_synced)
- Per-source health indicators
- Stale data warnings

SECURITY: All operations are tenant-scoped via tenant_id from JWT.

Story 3.6 - Data Freshness & Health Monitoring
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional

from sqlalchemy.orm import Session

from src.services.airbyte_service import AirbyteService
from src.models.airbyte_connection import ConnectionStatus

logger = logging.getLogger(__name__)


# Default freshness thresholds (in minutes)
DEFAULT_FRESHNESS_THRESHOLD_MINUTES = 120  # 2 hours - data considered stale
DEFAULT_CRITICAL_THRESHOLD_MINUTES = 1440  # 24 hours - data critically stale
DEFAULT_SYNC_FREQUENCY_MINUTES = 60  # Default if not specified on connection


class FreshnessStatus(str, Enum):
    """Data freshness status enumeration."""
    FRESH = "fresh"
    STALE = "stale"
    CRITICAL = "critical"
    NEVER_SYNCED = "never_synced"
    UNKNOWN = "unknown"


@dataclass
class SourceHealthInfo:
    """Health information for a single data source."""
    connection_id: str
    connection_name: str
    source_type: Optional[str]
    status: str
    is_enabled: bool
    freshness_status: FreshnessStatus
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    sync_frequency_minutes: int
    minutes_since_sync: Optional[int]
    expected_next_sync_at: Optional[datetime]
    is_stale: bool
    is_healthy: bool
    warning_message: Optional[str]


@dataclass
class DataHealthSummary:
    """Overall data health summary for a tenant."""
    total_sources: int
    healthy_sources: int
    stale_sources: int
    critical_sources: int
    never_synced_sources: int
    disabled_sources: int
    failed_sources: int
    overall_health_score: float
    has_warnings: bool
    sources: List[SourceHealthInfo]


class DataHealthServiceError(Exception):
    """Base exception for data health service errors."""
    pass


class DataHealthService:
    """
    Service for monitoring data freshness and health.

    Provides comprehensive health indicators for all data sources,
    with configurable freshness thresholds.

    SECURITY: All methods require tenant_id from JWT context.
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        freshness_threshold_minutes: int = DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
        critical_threshold_minutes: int = DEFAULT_CRITICAL_THRESHOLD_MINUTES,
    ):
        """
        Initialize data health service.

        Args:
            db_session: Database session
            tenant_id: Tenant ID from JWT (org_id)
            freshness_threshold_minutes: Minutes after which data is stale
            critical_threshold_minutes: Minutes after which data is critically stale

        Raises:
            ValueError: If tenant_id is empty or None
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self._airbyte_service = AirbyteService(db_session, tenant_id)
        self.freshness_threshold_minutes = freshness_threshold_minutes
        self.critical_threshold_minutes = critical_threshold_minutes

    def _parse_sync_frequency(self, sync_frequency: Optional[str]) -> int:
        """Parse sync frequency string to minutes."""
        if not sync_frequency:
            return DEFAULT_SYNC_FREQUENCY_MINUTES
        try:
            return int(sync_frequency)
        except (ValueError, TypeError):
            return DEFAULT_SYNC_FREQUENCY_MINUTES

    def _calculate_freshness_status(
        self,
        last_sync_at: Optional[datetime],
        sync_frequency_minutes: int,
        is_enabled: bool,
        connection_status: str,
    ) -> FreshnessStatus:
        """
        Calculate freshness status for a connection.

        Logic:
        - NEVER_SYNCED: No sync has ever occurred
        - FRESH: Within expected sync window
        - STALE: Exceeded freshness threshold
        - CRITICAL: Exceeded critical threshold
        - UNKNOWN: Cannot determine (disabled or deleted)
        """
        if connection_status == "deleted":
            return FreshnessStatus.UNKNOWN

        if not last_sync_at:
            return FreshnessStatus.NEVER_SYNCED

        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes
        if last_sync_at.tzinfo is None:
            last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)

        minutes_since_sync = (now - last_sync_at).total_seconds() / 60

        # Use the larger of sync_frequency or freshness_threshold
        effective_threshold = max(sync_frequency_minutes, self.freshness_threshold_minutes)

        if minutes_since_sync <= effective_threshold:
            return FreshnessStatus.FRESH
        elif minutes_since_sync <= self.critical_threshold_minutes:
            return FreshnessStatus.STALE
        else:
            return FreshnessStatus.CRITICAL

    def _calculate_minutes_since_sync(
        self,
        last_sync_at: Optional[datetime]
    ) -> Optional[int]:
        """Calculate minutes since last sync."""
        if not last_sync_at:
            return None

        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes
        if last_sync_at.tzinfo is None:
            last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)

        return int((now - last_sync_at).total_seconds() / 60)

    def _calculate_expected_next_sync(
        self,
        last_sync_at: Optional[datetime],
        sync_frequency_minutes: int
    ) -> Optional[datetime]:
        """Calculate expected next sync time."""
        if not last_sync_at:
            return None

        # Handle timezone-naive datetimes
        if last_sync_at.tzinfo is None:
            last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)

        return last_sync_at + timedelta(minutes=sync_frequency_minutes)

    def _generate_warning_message(
        self,
        freshness_status: FreshnessStatus,
        minutes_since_sync: Optional[int],
        last_sync_status: Optional[str],
        connection_status: str,
    ) -> Optional[str]:
        """Generate warning message for unhealthy sources."""
        if freshness_status == FreshnessStatus.NEVER_SYNCED:
            return "Data source has never been synced"

        if freshness_status == FreshnessStatus.CRITICAL:
            hours = minutes_since_sync // 60 if minutes_since_sync else 0
            return f"Data is critically stale: last synced {hours} hours ago"

        if freshness_status == FreshnessStatus.STALE:
            hours = minutes_since_sync // 60 if minutes_since_sync else 0
            return f"Data is stale: last synced {hours} hours ago"

        if connection_status == "failed":
            return "Connection is in failed state"

        if last_sync_status == "failed":
            return "Last sync attempt failed"

        return None

    def get_source_health(self, connection_id: str) -> Optional[SourceHealthInfo]:
        """
        Get health information for a specific data source.

        SECURITY: Only returns health for connections belonging to current tenant.

        Args:
            connection_id: Internal connection ID

        Returns:
            SourceHealthInfo if found, None otherwise
        """
        connection = self._airbyte_service.get_connection(connection_id)
        if not connection:
            return None

        sync_frequency = self._parse_sync_frequency(
            getattr(connection, 'sync_frequency_minutes', None) or
            str(DEFAULT_SYNC_FREQUENCY_MINUTES)
        )

        freshness_status = self._calculate_freshness_status(
            connection.last_sync_at,
            sync_frequency,
            connection.is_enabled,
            connection.status,
        )

        minutes_since_sync = self._calculate_minutes_since_sync(connection.last_sync_at)
        expected_next_sync = self._calculate_expected_next_sync(
            connection.last_sync_at, sync_frequency
        )

        is_stale = freshness_status in (
            FreshnessStatus.STALE,
            FreshnessStatus.CRITICAL,
            FreshnessStatus.NEVER_SYNCED,
        )

        is_healthy = (
            freshness_status == FreshnessStatus.FRESH
            and connection.is_enabled
            and connection.status == "active"
            and connection.last_sync_status != "failed"
        )

        warning_message = self._generate_warning_message(
            freshness_status,
            minutes_since_sync,
            connection.last_sync_status,
            connection.status,
        )

        logger.info(
            "Source health retrieved",
            extra={
                "tenant_id": self.tenant_id,
                "connection_id": connection_id,
                "freshness_status": freshness_status.value,
                "is_healthy": is_healthy,
            },
        )

        return SourceHealthInfo(
            connection_id=connection.id,
            connection_name=connection.connection_name,
            source_type=connection.source_type,
            status=connection.status,
            is_enabled=connection.is_enabled,
            freshness_status=freshness_status,
            last_sync_at=connection.last_sync_at,
            last_sync_status=connection.last_sync_status,
            sync_frequency_minutes=sync_frequency,
            minutes_since_sync=minutes_since_sync,
            expected_next_sync_at=expected_next_sync,
            is_stale=is_stale,
            is_healthy=is_healthy,
            warning_message=warning_message,
        )

    def get_all_sources_health(self) -> List[SourceHealthInfo]:
        """
        Get health information for all data sources.

        CRITICAL: Only returns sources belonging to the tenant.

        Returns:
            List of SourceHealthInfo for all connections
        """
        result = self._airbyte_service.list_connections(limit=1000)
        health_list = []

        for connection in result.connections:
            sync_frequency = self._parse_sync_frequency(
                getattr(connection, 'sync_frequency_minutes', None) or
                str(DEFAULT_SYNC_FREQUENCY_MINUTES)
            )

            freshness_status = self._calculate_freshness_status(
                connection.last_sync_at,
                sync_frequency,
                connection.is_enabled,
                connection.status,
            )

            minutes_since_sync = self._calculate_minutes_since_sync(
                connection.last_sync_at
            )
            expected_next_sync = self._calculate_expected_next_sync(
                connection.last_sync_at, sync_frequency
            )

            is_stale = freshness_status in (
                FreshnessStatus.STALE,
                FreshnessStatus.CRITICAL,
                FreshnessStatus.NEVER_SYNCED,
            )

            is_healthy = (
                freshness_status == FreshnessStatus.FRESH
                and connection.is_enabled
                and connection.status == "active"
                and connection.last_sync_status != "failed"
            )

            warning_message = self._generate_warning_message(
                freshness_status,
                minutes_since_sync,
                connection.last_sync_status,
                connection.status,
            )

            health_list.append(SourceHealthInfo(
                connection_id=connection.id,
                connection_name=connection.connection_name,
                source_type=connection.source_type,
                status=connection.status,
                is_enabled=connection.is_enabled,
                freshness_status=freshness_status,
                last_sync_at=connection.last_sync_at,
                last_sync_status=connection.last_sync_status,
                sync_frequency_minutes=sync_frequency,
                minutes_since_sync=minutes_since_sync,
                expected_next_sync_at=expected_next_sync,
                is_stale=is_stale,
                is_healthy=is_healthy,
                warning_message=warning_message,
            ))

        return health_list

    def get_data_health_summary(self) -> DataHealthSummary:
        """
        Get overall data health summary for the tenant.

        Provides aggregate health metrics and identifies issues.

        Returns:
            DataHealthSummary with overall health status
        """
        sources = self.get_all_sources_health()

        total = len(sources)
        healthy = sum(1 for s in sources if s.is_healthy)
        stale = sum(
            1 for s in sources
            if s.freshness_status == FreshnessStatus.STALE
        )
        critical = sum(
            1 for s in sources
            if s.freshness_status == FreshnessStatus.CRITICAL
        )
        never_synced = sum(
            1 for s in sources
            if s.freshness_status == FreshnessStatus.NEVER_SYNCED
        )
        disabled = sum(1 for s in sources if not s.is_enabled)
        failed = sum(1 for s in sources if s.status == "failed")

        # Calculate health score (0-100)
        if total == 0:
            health_score = 100.0
        else:
            # Healthy sources contribute 100%, stale 50%, critical/failed 0%
            enabled_sources = [s for s in sources if s.is_enabled]
            if len(enabled_sources) == 0:
                health_score = 100.0
            else:
                score_sum = sum(
                    100 if s.is_healthy else
                    50 if s.freshness_status == FreshnessStatus.STALE else
                    25 if s.freshness_status == FreshnessStatus.NEVER_SYNCED else
                    0
                    for s in enabled_sources
                )
                health_score = round(score_sum / len(enabled_sources), 1)

        has_warnings = stale > 0 or critical > 0 or never_synced > 0 or failed > 0

        logger.info(
            "Data health summary generated",
            extra={
                "tenant_id": self.tenant_id,
                "total_sources": total,
                "healthy_sources": healthy,
                "stale_sources": stale,
                "critical_sources": critical,
                "health_score": health_score,
            },
        )

        return DataHealthSummary(
            total_sources=total,
            healthy_sources=healthy,
            stale_sources=stale,
            critical_sources=critical,
            never_synced_sources=never_synced,
            disabled_sources=disabled,
            failed_sources=failed,
            overall_health_score=health_score,
            has_warnings=has_warnings,
            sources=sources,
        )

    def get_stale_sources(self) -> List[SourceHealthInfo]:
        """
        Get all sources with stale data.

        Useful for alerting and monitoring dashboards.

        Returns:
            List of SourceHealthInfo for stale sources
        """
        all_sources = self.get_all_sources_health()
        stale_sources = [
            s for s in all_sources
            if s.freshness_status in (
                FreshnessStatus.STALE,
                FreshnessStatus.CRITICAL,
                FreshnessStatus.NEVER_SYNCED,
            )
            and s.is_enabled
        ]

        logger.info(
            "Stale sources retrieved",
            extra={
                "tenant_id": self.tenant_id,
                "stale_count": len(stale_sources),
            },
        )

        return stale_sources
