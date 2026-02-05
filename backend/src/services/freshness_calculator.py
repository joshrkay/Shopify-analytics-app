"""
Multi-signal freshness calculator.

Correlates ingestion (Airbyte) and transformation (dbt) signals per tenant+source.
Computes unified freshness status using worst-signal-wins semantics:
- Missing signals degrade safely to STALE, not FRESH
- When signals disagree, the worst state wins
- No single source of truth assumption

SECURITY: All operations are tenant-scoped via tenant_id from JWT.

Usage:
    from src.services.freshness_calculator import FreshnessCalculator

    calculator = FreshnessCalculator(
        db_session=session,
        tenant_id=tenant_id,
        sla_config=sla_config,  # Optional: override SLA thresholds
    )
    result = calculator.calculate_source_freshness(source_type="shopify")
    summary = calculator.calculate_tenant_freshness()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default path to SLA configuration
DEFAULT_SLA_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "data_freshness_sla.yml"


class FreshnessLevel(str, Enum):
    """Unified freshness level across all signals."""
    FRESH = "fresh"
    WARN = "warn"
    STALE = "stale"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class SignalFreshness:
    """
    Freshness status from a single signal source.

    Attributes:
        signal_type: Type of signal (ingestion, transformation, freshness_check)
        source_type: Data source type (e.g., shopify)
        level: Freshness level
        last_updated_at: When the signal was last updated
        age_minutes: Age of the signal in minutes
        threshold_warn_minutes: Warning threshold
        threshold_error_minutes: Error threshold
        message: Human-readable status message
        metadata: Additional signal-specific metadata
    """
    signal_type: str
    source_type: str
    level: FreshnessLevel
    last_updated_at: Optional[datetime]
    age_minutes: Optional[int]
    threshold_warn_minutes: Optional[int] = None
    threshold_error_minutes: Optional[int] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "source_type": self.source_type,
            "level": self.level.value,
            "last_updated_at": (
                self.last_updated_at.isoformat() if self.last_updated_at else None
            ),
            "age_minutes": self.age_minutes,
            "threshold_warn_minutes": self.threshold_warn_minutes,
            "threshold_error_minutes": self.threshold_error_minutes,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass
class SourceFreshnessResult:
    """
    Correlated freshness result for a single source.

    Attributes:
        source_type: Data source type
        connection_id: Internal connection ID
        connection_name: Human-readable connection name
        overall_level: Worst-case freshness level across signals
        signals: Individual signal freshness statuses
        is_fresh: Whether data is considered fresh for consumption
        is_actionable: Whether freshness issues are actionable
        recommendation: Recommended action if not fresh
    """
    source_type: str
    connection_id: str
    connection_name: str
    overall_level: FreshnessLevel
    signals: List[SignalFreshness]
    is_fresh: bool
    is_actionable: bool = True
    recommendation: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "connection_id": self.connection_id,
            "connection_name": self.connection_name,
            "overall_level": self.overall_level.value,
            "signals": [s.to_dict() for s in self.signals],
            "is_fresh": self.is_fresh,
            "is_actionable": self.is_actionable,
            "recommendation": self.recommendation,
        }


@dataclass
class TenantFreshnessSummary:
    """
    Aggregate freshness summary for a tenant.

    Attributes:
        tenant_id: Tenant identifier
        calculated_at: When the summary was calculated
        overall_level: Worst-case level across all sources
        freshness_score: 0-100 score (100 = all fresh)
        sources: Per-source freshness results
        fresh_count: Number of fresh sources
        warn_count: Number of sources with warnings
        stale_count: Number of stale sources
        error_count: Number of sources with errors
        unknown_count: Number of sources with unknown status
        has_issues: Whether any sources have freshness issues
    """
    tenant_id: str
    calculated_at: datetime
    overall_level: FreshnessLevel
    freshness_score: float
    sources: List[SourceFreshnessResult]
    fresh_count: int = 0
    warn_count: int = 0
    stale_count: int = 0
    error_count: int = 0
    unknown_count: int = 0
    has_issues: bool = False

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "calculated_at": self.calculated_at.isoformat(),
            "overall_level": self.overall_level.value,
            "freshness_score": self.freshness_score,
            "sources": [s.to_dict() for s in self.sources],
            "fresh_count": self.fresh_count,
            "warn_count": self.warn_count,
            "stale_count": self.stale_count,
            "error_count": self.error_count,
            "unknown_count": self.unknown_count,
            "has_issues": self.has_issues,
        }


@dataclass
class SlaThresholds:
    """SLA thresholds for a source."""
    warn_after_minutes: int
    error_after_minutes: int


class FreshnessCalculatorError(Exception):
    """Base exception for freshness calculator errors."""
    pass


class FreshnessCalculator:
    """
    Multi-signal freshness calculator.

    Correlates ingestion and transformation signals to compute
    unified freshness status per source.

    Design principles:
    1. Missing signals = STALE (fail-safe)
    2. When signals disagree, worst wins
    3. SLA thresholds are tier-aware

    SECURITY: tenant_id must come from JWT (org_id), never client input.
    """

    # Level severity ordering (higher = worse)
    _LEVEL_SEVERITY = {
        FreshnessLevel.FRESH: 0,
        FreshnessLevel.WARN: 1,
        FreshnessLevel.STALE: 2,
        FreshnessLevel.ERROR: 3,
        FreshnessLevel.UNKNOWN: 4,
    }

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        billing_tier: str = "free",
        sla_config: Optional[Dict] = None,
        sla_config_path: Optional[Path] = None,
    ):
        """
        Initialize freshness calculator.

        Args:
            db_session: Database session
            tenant_id: Tenant ID from JWT (org_id)
            billing_tier: Billing tier for SLA lookup (free/growth/enterprise)
            sla_config: Optional override for SLA configuration
            sla_config_path: Path to SLA YAML config (defaults to config/data_freshness_sla.yml)

        Raises:
            ValueError: If tenant_id is empty or None
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.billing_tier = billing_tier
        self._sla_config = sla_config or self._load_sla_config(
            sla_config_path or DEFAULT_SLA_CONFIG_PATH
        )

    def _load_sla_config(self, config_path: Path) -> Dict:
        """Load SLA configuration from YAML file."""
        if not config_path.exists():
            logger.warning(
                "SLA config not found, using defaults",
                extra={"path": str(config_path)},
            )
            return {"version": 1, "default_tier": "free", "sources": {}}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(
                "Failed to load SLA config",
                extra={"path": str(config_path), "error": str(e)},
            )
            return {"version": 1, "default_tier": "free", "sources": {}}

    def _get_sla_thresholds(self, source_type: str) -> SlaThresholds:
        """
        Get SLA thresholds for a source type and billing tier.

        Falls back to defaults if source/tier not configured.
        """
        sources = self._sla_config.get("sources", {})
        source_config = sources.get(source_type, {})
        tier_config = source_config.get(self.billing_tier)

        if not tier_config:
            # Fall back to default tier
            default_tier = self._sla_config.get("default_tier", "free")
            tier_config = source_config.get(default_tier, {})

        # Default thresholds if not configured
        warn_after = tier_config.get("warn_after_minutes", 360)  # 6 hours
        error_after = tier_config.get("error_after_minutes", 1440)  # 24 hours

        return SlaThresholds(
            warn_after_minutes=warn_after,
            error_after_minutes=error_after,
        )

    def _get_tenant_connections(self):
        """Get enabled connections for the tenant."""
        from src.models.airbyte_connection import TenantAirbyteConnection

        return (
            self.db.query(TenantAirbyteConnection)
            .filter(
                TenantAirbyteConnection.tenant_id == self.tenant_id,
                TenantAirbyteConnection.is_enabled.is_(True),
            )
            .all()
        )

    def _minutes_since(self, ts: Optional[datetime]) -> Optional[int]:
        """Calculate minutes since a timestamp."""
        if ts is None:
            return None

        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return int((now - ts).total_seconds() / 60)

    def _classify_age(
        self,
        age_minutes: Optional[int],
        thresholds: SlaThresholds,
    ) -> FreshnessLevel:
        """Classify age into freshness level based on SLA thresholds."""
        if age_minutes is None:
            return FreshnessLevel.UNKNOWN

        if age_minutes <= thresholds.warn_after_minutes:
            return FreshnessLevel.FRESH
        elif age_minutes <= thresholds.error_after_minutes:
            return FreshnessLevel.WARN
        else:
            return FreshnessLevel.STALE

    def _get_worst_level(self, levels: List[FreshnessLevel]) -> FreshnessLevel:
        """Get the worst (highest severity) level from a list."""
        if not levels:
            return FreshnessLevel.UNKNOWN

        return max(levels, key=lambda l: self._LEVEL_SEVERITY.get(l, 999))

    def _build_ingestion_signal(
        self,
        connection,
        thresholds: SlaThresholds,
    ) -> SignalFreshness:
        """Build ingestion signal from connection data."""
        age_minutes = self._minutes_since(connection.last_sync_at)
        level = self._classify_age(age_minutes, thresholds)

        message = None
        if connection.last_sync_at is None:
            level = FreshnessLevel.ERROR
            message = "Never synced"
        elif connection.last_sync_status == "failed":
            level = FreshnessLevel.WARN
            message = "Last sync failed"
        elif level == FreshnessLevel.STALE:
            hours = (age_minutes or 0) // 60
            message = f"Data {hours}h stale (threshold: {thresholds.error_after_minutes // 60}h)"
        elif level == FreshnessLevel.WARN:
            hours = (age_minutes or 0) // 60
            message = f"Data {hours}h old, approaching staleness"

        return SignalFreshness(
            signal_type="ingestion",
            source_type=connection.source_type or "unknown",
            level=level,
            last_updated_at=connection.last_sync_at,
            age_minutes=age_minutes,
            threshold_warn_minutes=thresholds.warn_after_minutes,
            threshold_error_minutes=thresholds.error_after_minutes,
            message=message,
            metadata={
                "connection_id": connection.id,
                "last_sync_status": connection.last_sync_status,
            },
        )

    def _generate_recommendation(
        self,
        level: FreshnessLevel,
        signals: List[SignalFreshness],
    ) -> Optional[str]:
        """Generate actionable recommendation based on freshness issues."""
        if level == FreshnessLevel.FRESH:
            return None

        # Find the worst signal
        worst_signal = max(
            signals,
            key=lambda s: self._LEVEL_SEVERITY.get(s.level, 0),
        )

        if worst_signal.level == FreshnessLevel.ERROR:
            if "Never synced" in (worst_signal.message or ""):
                return "Trigger initial sync for this source"
            return "Investigate sync failures in Airbyte"

        if worst_signal.level == FreshnessLevel.STALE:
            if worst_signal.signal_type == "ingestion":
                return "Check Airbyte connection status and trigger manual sync"
            elif worst_signal.signal_type == "transformation":
                return "Check dbt job status and trigger manual run"

        if worst_signal.level == FreshnessLevel.WARN:
            return "Monitor - data approaching staleness threshold"

        return None

    def calculate_source_freshness(
        self,
        source_type: str,
        dbt_model_timestamp: Optional[datetime] = None,
        dbt_freshness_result: Optional[dict] = None,
    ) -> List[SourceFreshnessResult]:
        """
        Calculate freshness for all connections of a source type.

        Correlates ingestion signal (from TenantAirbyteConnection) with
        optional dbt transformation and freshness signals.

        Args:
            source_type: Data source type (e.g., "shopify")
            dbt_model_timestamp: Optional latest dbt model completion time
            dbt_freshness_result: Optional dbt source freshness check result

        Returns:
            List of SourceFreshnessResult for each connection of this type
        """
        connections = self._get_tenant_connections()
        source_connections = [
            c for c in connections
            if c.source_type == source_type
        ]

        if not source_connections:
            logger.info(
                "No connections found for source type",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                },
            )
            return []

        thresholds = self._get_sla_thresholds(source_type)
        results = []

        for conn in source_connections:
            signals: List[SignalFreshness] = []

            # Ingestion signal (always present if connection exists)
            ingestion_signal = self._build_ingestion_signal(conn, thresholds)
            signals.append(ingestion_signal)

            # Transformation signal (optional, from dbt run_results)
            if dbt_model_timestamp:
                age = self._minutes_since(dbt_model_timestamp)
                level = self._classify_age(age, thresholds)
                signals.append(SignalFreshness(
                    signal_type="transformation",
                    source_type=source_type,
                    level=level,
                    last_updated_at=dbt_model_timestamp,
                    age_minutes=age,
                    threshold_warn_minutes=thresholds.warn_after_minutes,
                    threshold_error_minutes=thresholds.error_after_minutes,
                ))

            # Freshness check signal (optional, from dbt source freshness)
            if dbt_freshness_result:
                status = dbt_freshness_result.get("status", "error")
                level_map = {
                    "pass": FreshnessLevel.FRESH,
                    "warn": FreshnessLevel.WARN,
                    "error": FreshnessLevel.STALE,
                }
                level = level_map.get(status, FreshnessLevel.ERROR)

                signals.append(SignalFreshness(
                    signal_type="freshness_check",
                    source_type=source_type,
                    level=level,
                    last_updated_at=None,  # dbt freshness doesn't track this
                    age_minutes=None,
                    message=f"dbt freshness: {status}",
                    metadata=dbt_freshness_result,
                ))

            # Calculate overall level (worst wins)
            signal_levels = [s.level for s in signals]
            overall_level = self._get_worst_level(signal_levels)
            is_fresh = overall_level == FreshnessLevel.FRESH

            recommendation = self._generate_recommendation(overall_level, signals)

            results.append(SourceFreshnessResult(
                source_type=source_type,
                connection_id=conn.id,
                connection_name=conn.connection_name,
                overall_level=overall_level,
                signals=signals,
                is_fresh=is_fresh,
                recommendation=recommendation,
            ))

        logger.info(
            "Calculated source freshness",
            extra={
                "tenant_id": self.tenant_id,
                "source_type": source_type,
                "connection_count": len(results),
                "fresh_count": sum(1 for r in results if r.is_fresh),
            },
        )

        return results

    def calculate_tenant_freshness(
        self,
        dbt_timestamps: Optional[Dict[str, datetime]] = None,
        dbt_freshness_results: Optional[Dict[str, dict]] = None,
    ) -> TenantFreshnessSummary:
        """
        Calculate aggregate freshness for all tenant sources.

        Args:
            dbt_timestamps: Optional dict of source_type -> latest model timestamp
            dbt_freshness_results: Optional dict of source_type -> freshness result

        Returns:
            TenantFreshnessSummary with aggregate metrics and per-source detail
        """
        dbt_timestamps = dbt_timestamps or {}
        dbt_freshness_results = dbt_freshness_results or {}

        connections = self._get_tenant_connections()

        # Group connections by source type
        source_types = set(c.source_type for c in connections if c.source_type)

        all_sources: List[SourceFreshnessResult] = []

        for source_type in source_types:
            results = self.calculate_source_freshness(
                source_type=source_type,
                dbt_model_timestamp=dbt_timestamps.get(source_type),
                dbt_freshness_result=dbt_freshness_results.get(source_type),
            )
            all_sources.extend(results)

        # Calculate aggregate metrics
        fresh_count = sum(1 for s in all_sources if s.overall_level == FreshnessLevel.FRESH)
        warn_count = sum(1 for s in all_sources if s.overall_level == FreshnessLevel.WARN)
        stale_count = sum(1 for s in all_sources if s.overall_level == FreshnessLevel.STALE)
        error_count = sum(1 for s in all_sources if s.overall_level == FreshnessLevel.ERROR)
        unknown_count = sum(1 for s in all_sources if s.overall_level == FreshnessLevel.UNKNOWN)

        total = len(all_sources)

        # Calculate score (weighted by severity)
        if total == 0:
            freshness_score = 100.0
        else:
            score_map = {
                FreshnessLevel.FRESH: 100,
                FreshnessLevel.WARN: 70,
                FreshnessLevel.STALE: 30,
                FreshnessLevel.ERROR: 0,
                FreshnessLevel.UNKNOWN: 50,
            }
            total_score = sum(
                score_map.get(s.overall_level, 0) for s in all_sources
            )
            freshness_score = round(total_score / total, 1)

        # Overall level (worst wins)
        all_levels = [s.overall_level for s in all_sources]
        overall_level = self._get_worst_level(all_levels) if all_levels else FreshnessLevel.UNKNOWN

        has_issues = overall_level != FreshnessLevel.FRESH

        logger.info(
            "Calculated tenant freshness summary",
            extra={
                "tenant_id": self.tenant_id,
                "total_sources": total,
                "fresh": fresh_count,
                "warn": warn_count,
                "stale": stale_count,
                "error": error_count,
                "score": freshness_score,
            },
        )

        return TenantFreshnessSummary(
            tenant_id=self.tenant_id,
            calculated_at=datetime.now(timezone.utc),
            overall_level=overall_level,
            freshness_score=freshness_score,
            sources=all_sources,
            fresh_count=fresh_count,
            warn_count=warn_count,
            stale_count=stale_count,
            error_count=error_count,
            unknown_count=unknown_count,
            has_issues=has_issues,
        )

    def check_ai_readiness(
        self,
        required_sources: Optional[List[str]] = None,
    ) -> tuple[bool, Optional[str], float]:
        """
        Check if tenant data is fresh enough for AI processing.

        Uses stricter thresholds than dashboard freshness.
        Any ERROR or STALE source blocks AI processing.

        Args:
            required_sources: Optional list of required source types.
                              If None, checks all enabled sources.

        Returns:
            Tuple of (is_ready, block_reason, freshness_score)
        """
        summary = self.calculate_tenant_freshness()

        sources_to_check = summary.sources
        if required_sources:
            sources_to_check = [
                s for s in summary.sources
                if s.source_type in required_sources
            ]

            # Check if all required sources exist
            found_types = set(s.source_type for s in sources_to_check)
            missing = set(required_sources) - found_types
            if missing:
                return (
                    False,
                    f"Required sources not found: {', '.join(missing)}",
                    0.0,
                )

        if not sources_to_check:
            return (
                False,
                "No enabled data sources found",
                0.0,
            )

        # Check for blocking issues
        blocking_sources = [
            s for s in sources_to_check
            if s.overall_level in (FreshnessLevel.ERROR, FreshnessLevel.STALE)
        ]

        if blocking_sources:
            source_names = [
                f"{s.source_type} ({s.overall_level.value})"
                for s in blocking_sources
            ]
            return (
                False,
                f"Data too stale for AI: {', '.join(source_names)}",
                summary.freshness_score,
            )

        return (True, None, summary.freshness_score)
