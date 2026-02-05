"""
dbt artifact parser.

Stateless parser for dbt run_results.json and sources.json (freshness) artifacts.
Extracts per-model transformation timestamps and per-source freshness check results.

This module does NOT persist data — it provides parsed structures that other
services (e.g., FreshnessCalculator) can use for freshness correlation.

Usage:
    from src.ingestion.dbt_artifact_parser import DbtArtifactParser

    parser = DbtArtifactParser()
    run_results = parser.parse_run_results(artifact_json)
    freshness_results = parser.parse_freshness_results(freshness_json)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)


class DbtNodeStatus(str, Enum):
    """dbt node execution status."""
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    WARN = "warn"
    PASS = "pass"
    FAIL = "fail"


class FreshnessStatus(str, Enum):
    """dbt source freshness status."""
    PASS = "pass"
    WARN = "warn"
    ERROR = "error"
    RUNTIME_ERROR = "runtime error"


@dataclass
class DbtModelResult:
    """
    Result of a single dbt model execution.

    Attributes:
        unique_id: dbt unique identifier (e.g., model.project.model_name)
        name: Short model name
        schema: Database schema
        database: Database name
        status: Execution status
        execution_time: Time taken to execute (seconds)
        started_at: Execution start timestamp
        completed_at: Execution completion timestamp
        rows_affected: Number of rows affected (if available)
        message: Status message or error
        adapter_response: Raw adapter response metadata
    """
    unique_id: str
    name: str
    schema: Optional[str]
    database: Optional[str]
    status: DbtNodeStatus
    execution_time: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    rows_affected: Optional[int] = None
    message: Optional[str] = None
    adapter_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DbtSourceFreshnessResult:
    """
    Result of a dbt source freshness check.

    Attributes:
        unique_id: dbt unique identifier (e.g., source.project.source.table)
        source_name: Source name (e.g., shopify)
        table_name: Table name (e.g., orders)
        status: Freshness check status
        max_loaded_at: Most recent timestamp found in the source
        snapshotted_at: When the freshness check was executed
        freshness_age_seconds: Age of the data in seconds
        warn_after_seconds: Threshold for warning
        error_after_seconds: Threshold for error
        filter_expression: Optional filter used in check
    """
    unique_id: str
    source_name: str
    table_name: str
    status: FreshnessStatus
    max_loaded_at: Optional[datetime]
    snapshotted_at: Optional[datetime]
    freshness_age_seconds: Optional[float] = None
    warn_after_seconds: Optional[int] = None
    error_after_seconds: Optional[int] = None
    filter_expression: Optional[str] = None


@dataclass
class DbtRunResults:
    """
    Parsed dbt run_results.json artifact.

    Attributes:
        dbt_version: dbt version used
        generated_at: When the artifact was generated
        invocation_id: Unique invocation identifier
        elapsed_time: Total elapsed time (seconds)
        models: List of model execution results
        success_count: Number of successful models
        error_count: Number of failed models
        skip_count: Number of skipped models
        warn_count: Number of models with warnings
    """
    dbt_version: str
    generated_at: datetime
    invocation_id: str
    elapsed_time: float
    models: List[DbtModelResult]
    success_count: int = 0
    error_count: int = 0
    skip_count: int = 0
    warn_count: int = 0


@dataclass
class DbtFreshnessResults:
    """
    Parsed dbt sources.json (freshness) artifact.

    Attributes:
        dbt_version: dbt version used
        generated_at: When the artifact was generated
        elapsed_time: Total elapsed time (seconds)
        sources: List of source freshness results
        pass_count: Number of sources passing freshness
        warn_count: Number of sources with freshness warnings
        error_count: Number of sources failing freshness
    """
    dbt_version: str
    generated_at: datetime
    elapsed_time: float
    sources: List[DbtSourceFreshnessResult]
    pass_count: int = 0
    warn_count: int = 0
    error_count: int = 0


class DbtArtifactParserError(Exception):
    """Base exception for dbt artifact parsing errors."""
    pass


class DbtArtifactParser:
    """
    Stateless parser for dbt artifacts.

    Parses run_results.json and sources.json (freshness) artifacts
    without side effects or database access.
    """

    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        """
        Parse ISO 8601 timestamp from dbt artifacts.

        dbt uses ISO 8601 format: 2024-01-15T10:30:00.123456Z
        """
        if ts is None:
            return None

        try:
            # Handle 'Z' suffix and fractional seconds
            ts_clean = ts.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(ts_clean)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, AttributeError) as e:
            logger.warning(
                "Failed to parse dbt timestamp",
                extra={"timestamp": ts, "error": str(e)},
            )
            return None

    def _parse_status(self, status: str) -> DbtNodeStatus:
        """Parse dbt node status string."""
        status_lower = status.lower()
        try:
            return DbtNodeStatus(status_lower)
        except ValueError:
            logger.warning(
                "Unknown dbt status, defaulting to error",
                extra={"status": status},
            )
            return DbtNodeStatus.ERROR

    def _parse_freshness_status(self, status: str) -> FreshnessStatus:
        """Parse dbt freshness status string."""
        status_lower = status.lower()
        try:
            return FreshnessStatus(status_lower)
        except ValueError:
            logger.warning(
                "Unknown freshness status, defaulting to error",
                extra={"status": status},
            )
            return FreshnessStatus.ERROR

    def _extract_rows_affected(
        self,
        adapter_response: Dict[str, Any],
    ) -> Optional[int]:
        """Extract rows affected from adapter response."""
        # Different adapters use different keys
        for key in ("rows_affected", "rowcount", "rows"):
            value = adapter_response.get(key)
            if value is not None:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        return None

    def parse_run_results(
        self,
        artifact: dict | str,
    ) -> DbtRunResults:
        """
        Parse dbt run_results.json artifact.

        Args:
            artifact: Parsed JSON dict or JSON string

        Returns:
            DbtRunResults with model execution details

        Raises:
            DbtArtifactParserError: If artifact is malformed
        """
        if isinstance(artifact, str):
            try:
                artifact = json.loads(artifact)
            except json.JSONDecodeError as e:
                raise DbtArtifactParserError(f"Invalid JSON: {e}")

        if not isinstance(artifact, dict):
            raise DbtArtifactParserError("Artifact must be a JSON object")

        # Extract metadata
        metadata = artifact.get("metadata", {})
        dbt_version = metadata.get("dbt_version", "unknown")
        generated_at_str = metadata.get("generated_at")
        invocation_id = metadata.get("invocation_id", "")

        generated_at = self._parse_timestamp(generated_at_str)
        if generated_at is None:
            generated_at = datetime.now(timezone.utc)

        elapsed_time = artifact.get("elapsed_time", 0.0)

        # Parse results
        results = artifact.get("results", [])
        models: List[DbtModelResult] = []
        success_count = 0
        error_count = 0
        skip_count = 0
        warn_count = 0

        for result in results:
            unique_id = result.get("unique_id", "")

            # Skip non-model nodes (tests, snapshots, etc.) for now
            # but include them if needed for broader coverage
            node_type = unique_id.split(".")[0] if unique_id else ""
            if node_type not in ("model", "snapshot", "seed"):
                continue

            status = self._parse_status(result.get("status", "error"))
            timing = result.get("timing", [])

            # Extract timing info
            started_at = None
            completed_at = None
            for t in timing:
                if t.get("name") == "execute":
                    started_at = self._parse_timestamp(t.get("started_at"))
                    completed_at = self._parse_timestamp(t.get("completed_at"))

            adapter_response = result.get("adapter_response", {})
            rows_affected = self._extract_rows_affected(adapter_response)

            model = DbtModelResult(
                unique_id=unique_id,
                name=unique_id.split(".")[-1] if unique_id else "",
                schema=result.get("relation_name", "").split(".")[1]
                    if result.get("relation_name") and "." in result.get("relation_name", "")
                    else None,
                database=result.get("relation_name", "").split(".")[0]
                    if result.get("relation_name") and "." in result.get("relation_name", "")
                    else None,
                status=status,
                execution_time=result.get("execution_time", 0.0),
                started_at=started_at,
                completed_at=completed_at,
                rows_affected=rows_affected,
                message=result.get("message"),
                adapter_response=adapter_response,
            )
            models.append(model)

            # Count statuses
            if status == DbtNodeStatus.SUCCESS:
                success_count += 1
            elif status == DbtNodeStatus.ERROR:
                error_count += 1
            elif status == DbtNodeStatus.SKIPPED:
                skip_count += 1
            elif status == DbtNodeStatus.WARN:
                warn_count += 1

        logger.info(
            "Parsed dbt run_results",
            extra={
                "dbt_version": dbt_version,
                "invocation_id": invocation_id,
                "model_count": len(models),
                "success": success_count,
                "error": error_count,
            },
        )

        return DbtRunResults(
            dbt_version=dbt_version,
            generated_at=generated_at,
            invocation_id=invocation_id,
            elapsed_time=elapsed_time,
            models=models,
            success_count=success_count,
            error_count=error_count,
            skip_count=skip_count,
            warn_count=warn_count,
        )

    def parse_freshness_results(
        self,
        artifact: dict | str,
    ) -> DbtFreshnessResults:
        """
        Parse dbt sources.json (freshness) artifact.

        Args:
            artifact: Parsed JSON dict or JSON string

        Returns:
            DbtFreshnessResults with source freshness details

        Raises:
            DbtArtifactParserError: If artifact is malformed
        """
        if isinstance(artifact, str):
            try:
                artifact = json.loads(artifact)
            except json.JSONDecodeError as e:
                raise DbtArtifactParserError(f"Invalid JSON: {e}")

        if not isinstance(artifact, dict):
            raise DbtArtifactParserError("Artifact must be a JSON object")

        # Extract metadata
        metadata = artifact.get("metadata", {})
        dbt_version = metadata.get("dbt_version", "unknown")
        generated_at_str = metadata.get("generated_at")

        generated_at = self._parse_timestamp(generated_at_str)
        if generated_at is None:
            generated_at = datetime.now(timezone.utc)

        elapsed_time = artifact.get("elapsed_time", 0.0)

        # Parse results
        results = artifact.get("results", [])
        sources: List[DbtSourceFreshnessResult] = []
        pass_count = 0
        warn_count = 0
        error_count = 0

        for result in results:
            unique_id = result.get("unique_id", "")
            status = self._parse_freshness_status(result.get("status", "error"))

            # Extract source and table names from unique_id
            # Format: source.project.source_name.table_name
            parts = unique_id.split(".")
            source_name = parts[2] if len(parts) > 2 else ""
            table_name = parts[3] if len(parts) > 3 else ""

            # Freshness criteria
            criteria = result.get("criteria", {})
            warn_after = criteria.get("warn_after", {})
            error_after = criteria.get("error_after", {})

            # Convert period to seconds
            def period_to_seconds(period: dict) -> Optional[int]:
                if not period:
                    return None
                count = period.get("count", 0)
                unit = period.get("period", "hour")
                multipliers = {
                    "minute": 60,
                    "hour": 3600,
                    "day": 86400,
                }
                return count * multipliers.get(unit, 3600)

            # Extract freshness data
            max_loaded_at = self._parse_timestamp(result.get("max_loaded_at"))
            snapshotted_at = self._parse_timestamp(result.get("snapshotted_at"))

            # Calculate age if both timestamps available
            freshness_age_seconds = None
            if max_loaded_at and snapshotted_at:
                freshness_age_seconds = (
                    snapshotted_at - max_loaded_at
                ).total_seconds()

            source = DbtSourceFreshnessResult(
                unique_id=unique_id,
                source_name=source_name,
                table_name=table_name,
                status=status,
                max_loaded_at=max_loaded_at,
                snapshotted_at=snapshotted_at,
                freshness_age_seconds=freshness_age_seconds,
                warn_after_seconds=period_to_seconds(warn_after),
                error_after_seconds=period_to_seconds(error_after),
                filter_expression=result.get("filter"),
            )
            sources.append(source)

            # Count statuses
            if status == FreshnessStatus.PASS:
                pass_count += 1
            elif status == FreshnessStatus.WARN:
                warn_count += 1
            elif status in (FreshnessStatus.ERROR, FreshnessStatus.RUNTIME_ERROR):
                error_count += 1

        logger.info(
            "Parsed dbt freshness results",
            extra={
                "dbt_version": dbt_version,
                "source_count": len(sources),
                "pass": pass_count,
                "warn": warn_count,
                "error": error_count,
            },
        )

        return DbtFreshnessResults(
            dbt_version=dbt_version,
            generated_at=generated_at,
            elapsed_time=elapsed_time,
            sources=sources,
            pass_count=pass_count,
            warn_count=warn_count,
            error_count=error_count,
        )

    def parse_from_file(
        self,
        file_path: str | Path,
        artifact_type: str = "run_results",
    ) -> DbtRunResults | DbtFreshnessResults:
        """
        Parse dbt artifact from a file.

        Args:
            file_path: Path to artifact JSON file
            artifact_type: "run_results" or "freshness"

        Returns:
            Parsed artifact (DbtRunResults or DbtFreshnessResults)

        Raises:
            DbtArtifactParserError: If file cannot be read or parsed
        """
        path = Path(file_path)

        if not path.exists():
            raise DbtArtifactParserError(f"File not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                artifact = json.load(f)
        except json.JSONDecodeError as e:
            raise DbtArtifactParserError(f"Invalid JSON in {path}: {e}")
        except IOError as e:
            raise DbtArtifactParserError(f"Cannot read {path}: {e}")

        if artifact_type == "run_results":
            return self.parse_run_results(artifact)
        elif artifact_type == "freshness":
            return self.parse_freshness_results(artifact)
        else:
            raise DbtArtifactParserError(
                f"Unknown artifact_type: {artifact_type}"
            )

    def get_latest_model_timestamps(
        self,
        run_results: DbtRunResults,
    ) -> Dict[str, datetime]:
        """
        Extract latest completion timestamps per model.

        Useful for correlating dbt transformation times with
        source ingestion times.

        Args:
            run_results: Parsed run results

        Returns:
            Dict mapping model name to completion timestamp
        """
        timestamps: Dict[str, datetime] = {}

        for model in run_results.models:
            if model.status == DbtNodeStatus.SUCCESS and model.completed_at:
                timestamps[model.name] = model.completed_at

        return timestamps

    def get_source_freshness_by_name(
        self,
        freshness_results: DbtFreshnessResults,
        source_name: str,
    ) -> List[DbtSourceFreshnessResult]:
        """
        Filter freshness results by source name.

        Args:
            freshness_results: Parsed freshness results
            source_name: Source name to filter by (e.g., "shopify")

        Returns:
            List of freshness results for the source
        """
        return [
            s for s in freshness_results.sources
            if s.source_name.lower() == source_name.lower()
        ]
