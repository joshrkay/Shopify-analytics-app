"""
Freshness calculator for unified data freshness verdicts.

Correlates ingestion (Airbyte sync) and transformation (dbt run) signals
to produce a unified freshness state per tenant per source, then applies
SLA thresholds from config/data_freshness_sla.yml.

Design principles:
- No single source of truth: both ingestion and transformation signals
  contribute independently to the freshness verdict.
- Safe degradation: missing signals degrade to STALE, never to FRESH.
- effective_age = max(ingestion_age, transformation_age) when both are
  available, ensuring the verdict reflects the oldest pipeline stage.

Business rules:
    1. Both signals present  -> effective_age = max(ingestion, transformation)
    2. Only ingestion        -> effective_age = ingestion_age  (log warning)
    3. Only transformation   -> effective_age = transformation_age (log warning)
    4. Neither signal        -> state = STALE, reason = "no_signals"
    5. SLA evaluation:
         effective_age < warn   -> FRESH
         warn <= effective_age < error -> STALE
         effective_age >= error -> UNAVAILABLE

SECURITY: All operations are tenant-scoped via tenant_id from JWT.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.ingestion.sync_status_ingestor import SyncStatusResult
from src.ingestion.dbt_artifact_parser import (
    DbtFreshnessSummary,
    DbtSourceFreshnessResult,
)
from src.services.data_availability_service import (
    get_sla_thresholds,
    get_tenant_connections,
    minutes_since_sync,
    resolve_sla_key,
)

logger = logging.getLogger(__name__)


@dataclass
class FreshnessVerdict:
    """
    Unified freshness verdict for one tenant + source combination.

    Combines ingestion and transformation signals with SLA thresholds
    to produce a single state that downstream consumers
    (DataAvailabilityService, dashboards, alerts) can act on.

    Attributes:
        tenant_id: Tenant identifier from JWT
        source_type: SLA config source key (e.g. 'shopify_orders')
        state: Computed state (fresh/stale/unavailable)
        reason: Human-readable reason for the state
        ingestion_age_minutes: Minutes since last successful Airbyte sync
        transformation_age_minutes: Minutes since last successful dbt run
        effective_age_minutes: max(ingestion_age, transformation_age)
        sla_warn_minutes: Warn threshold from SLA config
        sla_error_minutes: Error threshold from SLA config
        evaluated_at: When this verdict was computed
        details: Additional context for debugging and audit
    """

    tenant_id: str
    source_type: str
    state: str  # fresh, stale, unavailable
    reason: str
    ingestion_age_minutes: Optional[int]
    transformation_age_minutes: Optional[int]
    effective_age_minutes: int
    sla_warn_minutes: int
    sla_error_minutes: int
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "source_type": self.source_type,
            "state": self.state,
            "reason": self.reason,
            "ingestion_age_minutes": self.ingestion_age_minutes,
            "transformation_age_minutes": self.transformation_age_minutes,
            "effective_age_minutes": self.effective_age_minutes,
            "sla_warn_minutes": self.sla_warn_minutes,
            "sla_error_minutes": self.sla_error_minutes,
            "evaluated_at": self.evaluated_at.isoformat(),
            "details": self.details,
        }


class FreshnessCalculator:
    """
    Calculates unified freshness verdicts from ingestion and transformation signals.

    Correlates Airbyte sync timestamps (from SyncStatusIngestor) with dbt run
    timestamps (from DbtArtifactParser) and applies SLA thresholds to produce
    a per-source freshness verdict.

    Safe degradation rules:
    - If any signal is missing, use the worst-case (oldest) known value.
    - If no signals are available at all, the state is STALE (never FRESH).
    - This ensures that broken pipelines are surfaced rather than hidden.

    SECURITY: tenant_id must come from JWT (org_id), never from client input.

    Usage:
        calculator = FreshnessCalculator(db_session=session, tenant_id=tid)
        verdict = calculator.calculate(
            source_type="shopify_orders",
            sync_status=sync_result,
            dbt_freshness=dbt_freshness_result,
        )
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        billing_tier: str = "free",
    ):
        """
        Initialize freshness calculator.

        Args:
            db_session: Database session
            tenant_id: Tenant identifier from JWT (org_id)
            billing_tier: Billing tier for SLA threshold lookup

        Raises:
            ValueError: If tenant_id is empty or None
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.billing_tier = billing_tier

    def calculate(
        self,
        source_type: str,
        sync_status: Optional[SyncStatusResult] = None,
        dbt_freshness: Optional[DbtSourceFreshnessResult] = None,
    ) -> FreshnessVerdict:
        """
        Compute a freshness verdict for a single source from both signals.

        Combines the ingestion timestamp (from sync_status) and the
        transformation timestamp (from dbt_freshness) to derive an
        effective age, then applies SLA thresholds.

        Args:
            source_type: SLA config source key (e.g. 'shopify_orders')
            sync_status: Optional ingestion signal from SyncStatusIngestor
            dbt_freshness: Optional transformation signal from DbtArtifactParser

        Returns:
            FreshnessVerdict with computed state and supporting metadata
        """
        now = datetime.now(timezone.utc)
        warn_minutes, error_minutes = get_sla_thresholds(
            source_type, self.billing_tier
        )

        # Extract ingestion age
        ingestion_age = self._extract_ingestion_age(sync_status, now)

        # Extract transformation age
        transformation_age = self._extract_transformation_age(
            dbt_freshness, now
        )

        # Compute effective age with safe degradation
        effective_age = self._safe_degrade(ingestion_age, transformation_age)

        # Build details dict for audit/debugging
        details: Dict = {
            "billing_tier": self.billing_tier,
            "has_ingestion_signal": sync_status is not None,
            "has_transformation_signal": dbt_freshness is not None,
        }

        if sync_status is not None:
            details["ingestion_sync_status"] = sync_status.last_sync_status
            details["ingestion_connection_id"] = sync_status.connection_id

        if dbt_freshness is not None:
            details["dbt_source_name"] = dbt_freshness.source_name
            details["dbt_freshness_status"] = dbt_freshness.status

        # If neither signal is available, degrade to STALE
        if effective_age is None:
            logger.warning(
                "No freshness signals available, degrading to STALE",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                },
            )
            return FreshnessVerdict(
                tenant_id=self.tenant_id,
                source_type=source_type,
                state="stale",
                reason="no_signals",
                ingestion_age_minutes=None,
                transformation_age_minutes=None,
                effective_age_minutes=0,
                sla_warn_minutes=warn_minutes,
                sla_error_minutes=error_minutes,
                evaluated_at=now,
                details=details,
            )

        # Apply SLA thresholds
        state, reason = self._apply_sla(
            source_type, effective_age, ingestion_age, transformation_age
        )

        # Log partial-signal warnings
        if sync_status is not None and dbt_freshness is None:
            logger.warning(
                "Freshness calculated with ingestion signal only "
                "(no transformation signal)",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "ingestion_age_minutes": ingestion_age,
                },
            )
            details["signal_mode"] = "ingestion_only"

        elif sync_status is None and dbt_freshness is not None:
            logger.warning(
                "Freshness calculated with transformation signal only "
                "(no ingestion signal)",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "transformation_age_minutes": transformation_age,
                },
            )
            details["signal_mode"] = "transformation_only"

        else:
            details["signal_mode"] = "both"

        verdict = FreshnessVerdict(
            tenant_id=self.tenant_id,
            source_type=source_type,
            state=state,
            reason=reason,
            ingestion_age_minutes=ingestion_age,
            transformation_age_minutes=transformation_age,
            effective_age_minutes=effective_age,
            sla_warn_minutes=warn_minutes,
            sla_error_minutes=error_minutes,
            evaluated_at=now,
            details=details,
        )

        logger.info(
            "Freshness verdict computed",
            extra={
                "tenant_id": self.tenant_id,
                "source_type": source_type,
                "state": state,
                "reason": reason,
                "effective_age_minutes": effective_age,
                "ingestion_age_minutes": ingestion_age,
                "transformation_age_minutes": transformation_age,
                "sla_warn_minutes": warn_minutes,
                "sla_error_minutes": error_minutes,
            },
        )

        return verdict

    def calculate_all(
        self,
        sync_results: Optional[List[SyncStatusResult]] = None,
        dbt_summary: Optional[DbtFreshnessSummary] = None,
    ) -> List[FreshnessVerdict]:
        """
        Evaluate freshness for all sources belonging to this tenant.

        Correlates ingestion results (by source_type) and transformation
        results (by source_name) to produce one FreshnessVerdict per
        source.

        Args:
            sync_results: Optional list of ingestion signals from
                          SyncStatusIngestor.ingest_all()
            dbt_summary: Optional transformation freshness summary from
                         DbtArtifactParser.parse_freshness_results()

        Returns:
            List of FreshnessVerdict, one per source
        """
        # Build lookup maps for efficient correlation
        sync_by_source: Dict[str, SyncStatusResult] = {}
        if sync_results:
            for result in sync_results:
                if result.source_type:
                    sla_key = resolve_sla_key(result.source_type)
                    if sla_key and sla_key not in sync_by_source:
                        sync_by_source[sla_key] = result

        dbt_by_source: Dict[str, DbtSourceFreshnessResult] = {}
        if dbt_summary and dbt_summary.results:
            for result in dbt_summary.results:
                # Map dbt source_name to SLA key
                sla_key = resolve_sla_key(result.source_name)
                if sla_key and sla_key not in dbt_by_source:
                    dbt_by_source[sla_key] = result

        # Collect all source types to evaluate
        source_types: set = set()

        # From tenant connections
        connections = get_tenant_connections(self.db, self.tenant_id)
        for conn in connections:
            sla_key = resolve_sla_key(conn.source_type)
            if sla_key:
                source_types.add(sla_key)

        # From provided signals (in case connections are stale)
        source_types.update(sync_by_source.keys())
        source_types.update(dbt_by_source.keys())

        # Evaluate each source
        verdicts: List[FreshnessVerdict] = []
        for source_type in sorted(source_types):
            verdict = self.calculate(
                source_type=source_type,
                sync_status=sync_by_source.get(source_type),
                dbt_freshness=dbt_by_source.get(source_type),
            )
            verdicts.append(verdict)

        logger.info(
            "Freshness calculation completed for tenant",
            extra={
                "tenant_id": self.tenant_id,
                "sources_evaluated": len(verdicts),
                "fresh": sum(1 for v in verdicts if v.state == "fresh"),
                "stale": sum(1 for v in verdicts if v.state == "stale"),
                "unavailable": sum(
                    1 for v in verdicts if v.state == "unavailable"
                ),
            },
        )

        return verdicts

    def _apply_sla(
        self,
        source_type: str,
        effective_age_minutes: int,
        ingestion_age_minutes: Optional[int],
        transformation_age_minutes: Optional[int],
    ) -> Tuple[str, str]:
        """
        Apply SLA thresholds to determine freshness state and reason.

        State transitions:
            effective_age < warn_threshold  -> FRESH  / within_sla
            warn <= effective_age < error   -> STALE  / sla_warn_exceeded
            effective_age >= error          -> UNAVAILABLE / sla_error_exceeded

        Args:
            source_type: SLA config source key
            effective_age_minutes: The computed effective age
            ingestion_age_minutes: Ingestion age (for reason context)
            transformation_age_minutes: Transformation age (for reason context)

        Returns:
            Tuple of (state, reason)
        """
        warn_minutes, error_minutes = get_sla_thresholds(
            source_type, self.billing_tier
        )

        if effective_age_minutes >= error_minutes:
            # Determine which signal is the bottleneck
            bottleneck = self._identify_bottleneck(
                ingestion_age_minutes, transformation_age_minutes, error_minutes
            )
            return (
                "unavailable",
                f"sla_error_exceeded ({bottleneck})",
            )

        if effective_age_minutes >= warn_minutes:
            bottleneck = self._identify_bottleneck(
                ingestion_age_minutes, transformation_age_minutes, warn_minutes
            )
            return (
                "stale",
                f"sla_warn_exceeded ({bottleneck})",
            )

        return ("fresh", "within_sla")

    def _safe_degrade(
        self,
        *signals: Optional[int],
    ) -> Optional[int]:
        """
        Return the worst-case (maximum) value from available signals.

        When any signal is missing, only the available signals contribute.
        When ALL signals are missing, returns None (indicating no data).
        This ensures we never return FRESH when we lack information.

        Args:
            *signals: Optional age-in-minutes values

        Returns:
            Maximum of available values, or None if all are None
        """
        available = [s for s in signals if s is not None]
        if not available:
            return None
        return max(available)

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_ingestion_age(
        sync_status: Optional[SyncStatusResult],
        now: datetime,
    ) -> Optional[int]:
        """
        Extract ingestion age in minutes from a SyncStatusResult.

        Returns None if the signal is unavailable or has no successful
        sync timestamp.

        Args:
            sync_status: Ingestion signal
            now: Current timestamp for age calculation

        Returns:
            Minutes since last successful sync, or None
        """
        if sync_status is None:
            return None
        return minutes_since_sync(sync_status.last_successful_sync_at, now)

    @staticmethod
    def _extract_transformation_age(
        dbt_freshness: Optional[DbtSourceFreshnessResult],
        now: datetime,
    ) -> Optional[int]:
        """
        Extract transformation age in minutes from a DbtSourceFreshnessResult.

        Uses max_loaded_at as the transformation timestamp (the most recent
        data actually loaded into the warehouse for this source).

        Returns None if the signal is unavailable or has no max_loaded_at.

        Args:
            dbt_freshness: Transformation freshness signal
            now: Current timestamp for age calculation

        Returns:
            Minutes since max_loaded_at, or None
        """
        if dbt_freshness is None:
            return None
        return minutes_since_sync(dbt_freshness.max_loaded_at, now)

    @staticmethod
    def _identify_bottleneck(
        ingestion_age: Optional[int],
        transformation_age: Optional[int],
        threshold: int,
    ) -> str:
        """
        Identify which pipeline stage is the bottleneck for a threshold breach.

        Produces a human-readable label for inclusion in the reason string.

        Args:
            ingestion_age: Ingestion age in minutes
            transformation_age: Transformation age in minutes
            threshold: The SLA threshold that was exceeded

        Returns:
            Descriptive string identifying the bottleneck
        """
        ingestion_exceeded = (
            ingestion_age is not None and ingestion_age >= threshold
        )
        transformation_exceeded = (
            transformation_age is not None and transformation_age >= threshold
        )

        if ingestion_exceeded and transformation_exceeded:
            return "ingestion and transformation"
        if ingestion_exceeded:
            return "ingestion"
        if transformation_exceeded:
            return "transformation"
        return "effective_age"
