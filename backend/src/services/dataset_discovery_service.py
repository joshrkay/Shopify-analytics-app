"""
Dataset Discovery Service.

Queries Superset API for available datasets and their column metadata.
Caches results with 5-minute TTL. Returns column-level metadata including
is_metric, is_dimension, and data_type for frontend chart builder filtering.

Handles Superset unavailability by returning stale cached data with a
stale flag. Validates existing report configs against current schema
and returns warnings for missing columns.

Phase 2A - Dataset Discovery API
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Column types that can serve as metrics (numeric aggregation)
METRIC_DATA_TYPES = frozenset({
    "INTEGER", "INT", "BIGINT", "SMALLINT",
    "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC",
    "REAL", "DOUBLE PRECISION", "MONEY",
})

# Column types that can serve as time axes
DATETIME_DATA_TYPES = frozenset({
    "DATE", "DATETIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMPTZ",
})

CACHE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class ColumnMetadata:
    """Metadata for a single dataset column."""

    column_name: str
    data_type: str
    description: str = ""
    is_metric: bool = False
    is_dimension: bool = False
    is_temporal: bool = False


@dataclass
class DatasetInfo:
    """Metadata for a Superset dataset."""

    dataset_name: str
    dataset_id: int
    schema: str
    description: str
    columns: list[ColumnMetadata] = field(default_factory=list)


@dataclass
class DatasetDiscoveryResult:
    """Result of dataset discovery, with cache staleness info."""

    datasets: list[DatasetInfo] = field(default_factory=list)
    stale: bool = False
    cached_at: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ConfigWarning:
    """Warning for a report config referencing a missing column."""

    column_name: str
    dataset_name: str
    message: str


def classify_column(column_name: str, data_type: str) -> ColumnMetadata:
    """Classify a column as metric, dimension, or temporal based on its data type."""
    upper_type = (data_type or "VARCHAR").upper().strip()

    is_temporal = upper_type in DATETIME_DATA_TYPES
    is_metric = upper_type in METRIC_DATA_TYPES and not is_temporal
    # Dimensions: anything that isn't purely a metric (strings, booleans, etc.)
    # Temporal columns are also valid dimensions (GROUP BY date).
    is_dimension = not is_metric or is_temporal

    return ColumnMetadata(
        column_name=column_name,
        data_type=data_type or "VARCHAR",
        is_metric=is_metric,
        is_dimension=is_dimension,
        is_temporal=is_temporal,
    )


class DatasetDiscoveryService:
    """Discovers datasets and columns from Superset with caching."""

    def __init__(
        self,
        superset_url: Optional[str] = None,
        superset_username: Optional[str] = None,
        superset_password: Optional[str] = None,
        timeout_seconds: int = 10,
    ):
        self._superset_url = (superset_url or os.getenv("SUPERSET_EMBED_URL", "")).rstrip("/")
        self._username = superset_username or os.getenv("SUPERSET_USERNAME", "admin")
        self._password = superset_password or os.getenv("SUPERSET_PASSWORD", "admin")
        self._timeout = timeout_seconds
        self._token: Optional[str] = None
        self._csrf: Optional[str] = None

        # In-memory cache: {cache_key: (timestamp, data)}
        self._cache: dict[str, tuple[float, Any]] = {}

    def _ensure_auth(self, client: httpx.Client) -> None:
        """Authenticate with Superset if not already authenticated."""
        if self._token:
            return
        resp = client.post(
            f"{self._superset_url}/api/v1/security/login",
            json={
                "username": self._username,
                "password": self._password,
                "provider": "db",
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

        csrf_resp = client.get(
            f"{self._superset_url}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        csrf_resp.raise_for_status()
        self._csrf = csrf_resp.json().get("result", "")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-CSRFToken": self._csrf or "",
            "Content-Type": "application/json",
        }

    def _get_cached(self, key: str) -> Optional[tuple[bool, float, Any]]:
        """Return (is_stale, cached_at_timestamp, data) or None if no cache."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        cached_at, data = entry
        is_stale = (time.time() - cached_at) > CACHE_TTL_SECONDS
        return is_stale, cached_at, data

    def _set_cache(self, key: str, data: Any) -> None:
        self._cache[key] = (time.time(), data)

    def discover_datasets(self) -> DatasetDiscoveryResult:
        """
        Fetch all available datasets and their columns from Superset.

        Returns cached data with stale=True if Superset is unavailable.
        """
        cache_key = "all_datasets"
        cached = self._get_cached(cache_key)

        try:
            datasets = self._fetch_datasets_from_superset()
            result = DatasetDiscoveryResult(datasets=datasets)
            self._set_cache(cache_key, datasets)
            return result
        except Exception as exc:
            logger.warning(
                "dataset_discovery.superset_unavailable",
                extra={"error": str(exc)},
            )
            if cached is not None:
                _, cached_at, data = cached
                from datetime import datetime, timezone
                return DatasetDiscoveryResult(
                    datasets=data,
                    stale=True,
                    cached_at=datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat(),
                    error=f"Superset unavailable: {exc}",
                )
            return DatasetDiscoveryResult(
                error=f"Superset unavailable and no cached data: {exc}",
            )

    def get_dataset_columns(self, dataset_id: int) -> list[ColumnMetadata]:
        """Fetch columns for a specific dataset by Superset dataset ID."""
        cache_key = f"dataset_columns_{dataset_id}"
        cached = self._get_cached(cache_key)

        try:
            columns = self._fetch_columns_from_superset(dataset_id)
            self._set_cache(cache_key, columns)
            return columns
        except Exception as exc:
            logger.warning(
                "dataset_discovery.columns_fetch_failed",
                extra={"dataset_id": dataset_id, "error": str(exc)},
            )
            if cached is not None:
                _, _, data = cached
                return data
            return []

    def validate_config_columns(
        self,
        dataset_name: str,
        referenced_columns: list[str],
        available_columns: list[ColumnMetadata],
    ) -> list[ConfigWarning]:
        """
        Validate that columns referenced in a report config still exist.

        Returns warnings for any missing columns rather than raising errors.
        """
        available_names = {col.column_name for col in available_columns}
        warnings: list[ConfigWarning] = []
        for col_name in referenced_columns:
            if col_name not in available_names:
                warnings.append(ConfigWarning(
                    column_name=col_name,
                    dataset_name=dataset_name,
                    message=f"Column '{col_name}' no longer exists in dataset '{dataset_name}'",
                ))
        return warnings

    def _fetch_datasets_from_superset(self) -> list[DatasetInfo]:
        """Query Superset API for all available datasets with columns."""
        datasets: list[DatasetInfo] = []
        with httpx.Client(timeout=self._timeout) as client:
            self._ensure_auth(client)
            page = 0
            page_size = 100
            while True:
                resp = client.get(
                    f"{self._superset_url}/api/v1/dataset/",
                    headers=self._auth_headers(),
                    params={
                        "q": json.dumps({
                            "page": page,
                            "page_size": page_size,
                            "columns": [
                                "id", "table_name", "schema",
                                "description",
                            ],
                        })
                    },
                )
                resp.raise_for_status()
                result = resp.json().get("result", [])
                if not result:
                    break

                for ds in result:
                    ds_id = ds.get("id")
                    columns = self._fetch_columns_from_superset(
                        ds_id, client=client,
                    )
                    datasets.append(DatasetInfo(
                        dataset_name=ds.get("table_name", ""),
                        dataset_id=ds_id,
                        schema=ds.get("schema", ""),
                        description=ds.get("description", "") or "",
                        columns=columns,
                    ))

                if len(result) < page_size:
                    break
                page += 1

        return datasets

    def _fetch_columns_from_superset(
        self,
        dataset_id: int,
        client: Optional[httpx.Client] = None,
    ) -> list[ColumnMetadata]:
        """Fetch and classify columns for a single dataset."""
        def _do_fetch(c: httpx.Client) -> list[ColumnMetadata]:
            resp = c.get(
                f"{self._superset_url}/api/v1/dataset/{dataset_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            ds_data = resp.json().get("result", {})
            raw_columns = ds_data.get("columns", [])
            columns: list[ColumnMetadata] = []
            for col in raw_columns:
                col_name = col.get("column_name", "")
                data_type = col.get("type", "VARCHAR") or "VARCHAR"
                description = col.get("description", "") or col.get("verbose_name", "") or ""
                meta = classify_column(col_name, data_type)
                meta.description = description
                columns.append(meta)
            return columns

        if client is not None:
            return _do_fetch(client)

        with httpx.Client(timeout=self._timeout) as new_client:
            self._ensure_auth(new_client)
            return _do_fetch(new_client)
