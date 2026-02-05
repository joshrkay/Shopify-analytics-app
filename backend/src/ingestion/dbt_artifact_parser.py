"""
dbt artifact parser for transformation freshness signals.

Parses dbt run artifacts (run_results.json, sources.json) to extract
transformation timestamps and source freshness results for the freshness
signal pipeline.

Responsibilities:
- Parse run_results.json for per-model execution status and timestamps
- Parse sources.json (freshness output) for per-source freshness results
- Track transformation timestamps independently from ingestion timestamps
- Degrade safely to STALE when artifacts are missing or malformed

Design decisions:
- Ingestion (Airbyte) and transformation (dbt) are tracked independently.
  Neither is a single source of truth -- both contribute to the unified
  freshness verdict produced by FreshnessCalculator.
- Missing or unreadable artifacts produce empty summaries with generated_at=None,
  signalling STALE to downstream consumers.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses -- run results
# ---------------------------------------------------------------------------


@dataclass
class DbtModelResult:
    """
    Parsed result for a single dbt model execution.

    Attributes:
        model_name: Fully-qualified model name (e.g. 'stg_shopify__orders')
        schema_name: Target schema (e.g. 'analytics')
        status: Execution status (pass/fail/error/skipped)
        execution_time_seconds: Wall-clock execution time
        compiled_at: Timestamp when the model was compiled
        rows_affected: Number of rows affected (if available)
    """

    model_name: str
    schema_name: Optional[str]
    status: str  # pass, fail, error, skipped
    execution_time_seconds: float
    compiled_at: Optional[datetime] = None
    rows_affected: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "schema_name": self.schema_name,
            "status": self.status,
            "execution_time_seconds": self.execution_time_seconds,
            "compiled_at": (
                self.compiled_at.isoformat() if self.compiled_at else None
            ),
            "rows_affected": self.rows_affected,
        }


@dataclass
class DbtRunSummary:
    """
    Summary of a dbt run_results.json artifact.

    Attributes:
        generated_at: Timestamp when run_results.json was generated
        elapsed_time_seconds: Total dbt invocation wall-clock time
        results: Per-model results
        total_models: Count of models in the run
        passed: Count of models with status 'pass'
        failed: Count of models with status 'fail'
        errored: Count of models with status 'error'
        skipped: Count of models with status 'skipped'
    """

    generated_at: Optional[datetime]
    elapsed_time_seconds: float
    results: List[DbtModelResult] = field(default_factory=list)
    total_models: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "generated_at": (
                self.generated_at.isoformat() if self.generated_at else None
            ),
            "elapsed_time_seconds": self.elapsed_time_seconds,
            "total_models": self.total_models,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Dataclasses -- source freshness
# ---------------------------------------------------------------------------


@dataclass
class DbtSourceFreshnessResult:
    """
    Parsed freshness result for a single dbt source table.

    Attributes:
        source_name: dbt source name (e.g. 'shopify')
        table_name: Source table (e.g. 'orders')
        status: Freshness status (pass/warn/error/runtime_error)
        max_loaded_at: Most recent loaded_at timestamp in the source table
        snapshotted_at: When the freshness check was performed
        warn_after_minutes: Warn threshold from dbt source YAML (if available)
        error_after_minutes: Error threshold from dbt source YAML (if available)
        filter: Optional filter expression applied during freshness check
    """

    source_name: str
    table_name: str
    status: str  # pass, warn, error, runtime_error
    max_loaded_at: Optional[datetime] = None
    snapshotted_at: Optional[datetime] = None
    warn_after_minutes: Optional[int] = None
    error_after_minutes: Optional[int] = None
    filter: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "table_name": self.table_name,
            "status": self.status,
            "max_loaded_at": (
                self.max_loaded_at.isoformat() if self.max_loaded_at else None
            ),
            "snapshotted_at": (
                self.snapshotted_at.isoformat()
                if self.snapshotted_at
                else None
            ),
            "warn_after_minutes": self.warn_after_minutes,
            "error_after_minutes": self.error_after_minutes,
            "filter": self.filter,
        }


@dataclass
class DbtFreshnessSummary:
    """
    Summary of a dbt sources.json (freshness) artifact.

    Attributes:
        generated_at: Timestamp when sources.json was generated
        results: Per-source freshness results
        total_sources: Count of sources evaluated
        passed: Count with status 'pass'
        warned: Count with status 'warn'
        errored: Count with status 'error' or 'runtime_error'
    """

    generated_at: Optional[datetime]
    results: List[DbtSourceFreshnessResult] = field(default_factory=list)
    total_sources: int = 0
    passed: int = 0
    warned: int = 0
    errored: int = 0

    def to_dict(self) -> dict:
        return {
            "generated_at": (
                self.generated_at.isoformat() if self.generated_at else None
            ),
            "total_sources": self.total_sources,
            "passed": self.passed,
            "warned": self.warned,
            "errored": self.errored,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class DbtArtifactParser:
    """
    Parses dbt run artifacts for transformation freshness signals.

    Reads run_results.json and sources.json from the dbt target/ directory
    to extract transformation-layer timestamps and freshness evaluations.

    Safe degradation: when artifacts are missing, unreadable, or malformed,
    the parser returns summaries with generated_at=None.  Downstream
    consumers (FreshnessCalculator) treat a missing transformation signal
    as STALE, never as FRESH.

    Usage:
        parser = DbtArtifactParser(artifacts_dir="/app/analytics/target")
        run_summary = parser.parse_run_results()
        freshness_summary = parser.parse_freshness_results()
    """

    def __init__(self, artifacts_dir: Union[str, Path]):
        """
        Initialize the dbt artifact parser.

        Args:
            artifacts_dir: Path to the dbt target/ directory containing
                           run_results.json and sources.json
        """
        self.artifacts_dir = Path(artifacts_dir)

    # ── Public API ────────────────────────────────────────────────────────

    def parse_run_results(self) -> DbtRunSummary:
        """
        Parse dbt run_results.json to extract transformation timestamps.

        Returns a DbtRunSummary with per-model execution status. If the
        artifact is missing or malformed, returns an empty summary with
        generated_at=None (safe degradation to STALE).

        Returns:
            DbtRunSummary with parsed results or empty summary on failure
        """
        artifact_path = self.artifacts_dir / "run_results.json"
        data = self._safe_read_json(artifact_path)

        if data is None:
            logger.warning(
                "run_results.json missing or unreadable, degrading to STALE",
                extra={"artifacts_dir": str(self.artifacts_dir)},
            )
            return DbtRunSummary(generated_at=None, elapsed_time_seconds=0.0)

        try:
            generated_at = self._parse_timestamp(
                data.get("metadata", {}).get("generated_at")
            )
            elapsed_time = float(data.get("elapsed_time", 0.0))

            results: List[DbtModelResult] = []
            for node in data.get("results", []):
                result = self._parse_model_result(node)
                if result is not None:
                    results.append(result)

            passed = sum(1 for r in results if r.status == "pass")
            failed = sum(1 for r in results if r.status == "fail")
            errored = sum(1 for r in results if r.status == "error")
            skipped = sum(1 for r in results if r.status == "skipped")

            summary = DbtRunSummary(
                generated_at=generated_at,
                elapsed_time_seconds=elapsed_time,
                results=results,
                total_models=len(results),
                passed=passed,
                failed=failed,
                errored=errored,
                skipped=skipped,
            )

            logger.info(
                "Parsed dbt run_results.json",
                extra={
                    "generated_at": (
                        generated_at.isoformat() if generated_at else None
                    ),
                    "total_models": summary.total_models,
                    "passed": passed,
                    "failed": failed,
                    "errored": errored,
                    "skipped": skipped,
                },
            )

            return summary

        except Exception as e:
            logger.error(
                "Failed to parse run_results.json, degrading to STALE",
                extra={
                    "artifacts_dir": str(self.artifacts_dir),
                    "error": str(e),
                },
                exc_info=True,
            )
            return DbtRunSummary(generated_at=None, elapsed_time_seconds=0.0)

    def parse_freshness_results(self) -> DbtFreshnessSummary:
        """
        Parse dbt sources.json (freshness output) to extract per-source
        freshness results.

        Tries sources.json first; falls back to freshness.json for
        compatibility with older dbt versions.

        Returns a DbtFreshnessSummary with per-source freshness results.
        If the artifact is missing or malformed, returns an empty summary
        with generated_at=None (safe degradation to STALE).

        Returns:
            DbtFreshnessSummary with parsed results or empty summary on failure
        """
        # Try sources.json first, then freshness.json for compatibility
        artifact_path = self.artifacts_dir / "sources.json"
        data = self._safe_read_json(artifact_path)

        if data is None:
            artifact_path = self.artifacts_dir / "freshness.json"
            data = self._safe_read_json(artifact_path)

        if data is None:
            logger.warning(
                "Freshness artifact missing or unreadable, degrading to STALE",
                extra={"artifacts_dir": str(self.artifacts_dir)},
            )
            return DbtFreshnessSummary(generated_at=None)

        try:
            generated_at = self._parse_timestamp(
                data.get("metadata", {}).get("generated_at")
            )

            results: List[DbtSourceFreshnessResult] = []
            for node in data.get("results", []):
                result = self._parse_freshness_result(node)
                if result is not None:
                    results.append(result)

            passed = sum(1 for r in results if r.status == "pass")
            warned = sum(1 for r in results if r.status == "warn")
            errored = sum(
                1 for r in results if r.status in ("error", "runtime_error")
            )

            summary = DbtFreshnessSummary(
                generated_at=generated_at,
                results=results,
                total_sources=len(results),
                passed=passed,
                warned=warned,
                errored=errored,
            )

            logger.info(
                "Parsed dbt freshness artifact",
                extra={
                    "artifact_path": str(artifact_path),
                    "generated_at": (
                        generated_at.isoformat() if generated_at else None
                    ),
                    "total_sources": summary.total_sources,
                    "passed": passed,
                    "warned": warned,
                    "errored": errored,
                },
            )

            return summary

        except Exception as e:
            logger.error(
                "Failed to parse freshness artifact, degrading to STALE",
                extra={
                    "artifacts_dir": str(self.artifacts_dir),
                    "error": str(e),
                },
                exc_info=True,
            )
            return DbtFreshnessSummary(generated_at=None)

    # ── Static helpers ────────────────────────────────────────────────────

    @staticmethod
    def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
        """
        Safely read and parse a JSON file.

        Returns None if the file does not exist, is not readable, or
        contains invalid JSON.  Never raises.

        Args:
            path: Path to the JSON file

        Returns:
            Parsed dict or None on any failure
        """
        try:
            if not path.exists():
                return None

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning(
                    "JSON artifact is not a dict",
                    extra={"path": str(path)},
                )
                return None

            return data

        except json.JSONDecodeError as e:
            logger.warning(
                "Invalid JSON in artifact file",
                extra={"path": str(path), "error": str(e)},
            )
            return None

        except OSError as e:
            logger.warning(
                "Cannot read artifact file",
                extra={"path": str(path), "error": str(e)},
            )
            return None

        except Exception as e:
            logger.warning(
                "Unexpected error reading artifact file",
                extra={"path": str(path), "error": str(e)},
            )
            return None

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """
        Parse an ISO-format timestamp string to a timezone-aware datetime.

        Handles common dbt timestamp formats. Returns None if the value
        is missing or unparseable.  Never raises.

        Args:
            value: Raw timestamp value from JSON

        Returns:
            Parsed datetime or None
        """
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if not isinstance(value, str):
            return None

        try:
            # Handle Z suffix
            ts_str = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    # ── Internal parse helpers ────────────────────────────────────────────

    def _parse_model_result(self, node: Dict[str, Any]) -> Optional[DbtModelResult]:
        """
        Parse a single node from run_results.json into a DbtModelResult.

        Args:
            node: Raw result node dict

        Returns:
            DbtModelResult or None if unparseable
        """
        try:
            unique_id = node.get("unique_id", "")
            # Extract model name from unique_id (e.g. "model.project.stg_orders")
            parts = unique_id.split(".")
            model_name = parts[-1] if parts else unique_id

            status = node.get("status", "error")
            execution_time = float(node.get("execution_time", 0.0))

            # Extract schema from adapter_response or node config
            adapter_response = node.get("adapter_response", {})
            schema_name = None
            if isinstance(adapter_response, dict):
                schema_name = adapter_response.get("schema")

            # Try to get compiled_at from timing entries
            compiled_at = None
            timings = node.get("timing", [])
            if isinstance(timings, list):
                for timing in timings:
                    if isinstance(timing, dict) and timing.get("name") == "compile":
                        compiled_at = self._parse_timestamp(
                            timing.get("completed_at")
                        )
                        break

            # Extract rows_affected from adapter_response
            rows_affected = None
            if isinstance(adapter_response, dict):
                rows_val = adapter_response.get("rows_affected")
                if rows_val is not None:
                    try:
                        rows_affected = int(rows_val)
                    except (ValueError, TypeError):
                        pass

            return DbtModelResult(
                model_name=model_name,
                schema_name=schema_name,
                status=status,
                execution_time_seconds=execution_time,
                compiled_at=compiled_at,
                rows_affected=rows_affected,
            )

        except Exception as e:
            logger.warning(
                "Failed to parse model result node",
                extra={
                    "unique_id": node.get("unique_id", "unknown"),
                    "error": str(e),
                },
            )
            return None

    def _parse_freshness_result(
        self,
        node: Dict[str, Any],
    ) -> Optional[DbtSourceFreshnessResult]:
        """
        Parse a single node from sources.json into a DbtSourceFreshnessResult.

        Args:
            node: Raw freshness result node dict

        Returns:
            DbtSourceFreshnessResult or None if unparseable
        """
        try:
            unique_id = node.get("unique_id", "")
            # Extract source_name and table_name from unique_id
            # e.g. "source.project.shopify.orders"
            parts = unique_id.split(".")
            if len(parts) >= 4:
                source_name = parts[2]
                table_name = parts[3]
            elif len(parts) >= 2:
                source_name = parts[-2]
                table_name = parts[-1]
            else:
                source_name = unique_id
                table_name = ""

            status = node.get("status", "runtime_error")

            max_loaded_at = self._parse_timestamp(
                node.get("max_loaded_at")
            )
            snapshotted_at = self._parse_timestamp(
                node.get("snapshotted_at")
            )

            # Extract thresholds from criteria
            warn_after_minutes = None
            error_after_minutes = None
            criteria = node.get("criteria", {})
            if isinstance(criteria, dict):
                warn_after = criteria.get("warn_after", {})
                error_after = criteria.get("error_after", {})
                if isinstance(warn_after, dict):
                    warn_after_minutes = self._period_to_minutes(warn_after)
                if isinstance(error_after, dict):
                    error_after_minutes = self._period_to_minutes(error_after)

            filter_expr = node.get("filter")

            return DbtSourceFreshnessResult(
                source_name=source_name,
                table_name=table_name,
                status=status,
                max_loaded_at=max_loaded_at,
                snapshotted_at=snapshotted_at,
                warn_after_minutes=warn_after_minutes,
                error_after_minutes=error_after_minutes,
                filter=filter_expr,
            )

        except Exception as e:
            logger.warning(
                "Failed to parse freshness result node",
                extra={
                    "unique_id": node.get("unique_id", "unknown"),
                    "error": str(e),
                },
            )
            return None

    @staticmethod
    def _period_to_minutes(period: Dict[str, Any]) -> Optional[int]:
        """
        Convert a dbt freshness period dict to minutes.

        dbt represents periods as {"count": N, "period": "hour"|"minute"|"day"}.

        Args:
            period: Period dict from dbt criteria

        Returns:
            Total minutes or None if unparseable
        """
        try:
            count = int(period.get("count", 0))
            unit = str(period.get("period", "")).lower()

            multipliers = {
                "minute": 1,
                "minutes": 1,
                "hour": 60,
                "hours": 60,
                "day": 1440,
                "days": 1440,
            }

            multiplier = multipliers.get(unit)
            if multiplier is None:
                return None

            return count * multiplier

        except (ValueError, TypeError):
            return None
