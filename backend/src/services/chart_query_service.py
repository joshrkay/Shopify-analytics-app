"""
Chart Query Service.

Accepts a chart config, translates it to a Superset dataset query,
executes with a 100-row limit and 10-second timeout, and returns
formatted data ready for frontend rendering.

Security: All metric/column names are parameterized via Superset's
dataset API column references - never interpolated into raw SQL.

Phase 2B - Chart Preview Backend
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

PREVIEW_ROW_LIMIT = 100
PREVIEW_TIMEOUT_SECONDS = 10
PREVIEW_CACHE_TTL_SECONDS = 60
MAX_GROUPBY_CARDINALITY = 100

# Abstract chart types mapped to current Superset viz_type plugins
VIZ_TYPE_MAP: dict[str, str] = {
    "line": "echarts_timeseries_line",
    "bar": "echarts_timeseries_bar",
    "pie": "pie",
    "big_number": "big_number",
    "table": "table",
    "area": "echarts_area",
    "scatter": "echarts_timeseries_scatter",
}


@dataclass
class ChartConfig:
    """Chart configuration submitted for preview."""

    dataset_name: str
    metrics: list[dict[str, Any]]
    dimensions: list[str] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    time_range: str = "Last 30 days"
    time_column: Optional[str] = None
    time_grain: str = "P1D"
    viz_type: str = "line"
    order_by: Optional[list[dict[str, Any]]] = None
    row_limit: int = PREVIEW_ROW_LIMIT

    def config_hash(self) -> str:
        """Deterministic hash for cache keying."""
        payload = json.dumps(
            {
                "dataset_name": self.dataset_name,
                "metrics": self.metrics,
                "dimensions": self.dimensions,
                "filters": self.filters,
                "time_range": self.time_range,
                "time_column": self.time_column,
                "time_grain": self.time_grain,
                "viz_type": self.viz_type,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class ChartPreviewResult:
    """Result of a chart preview query."""

    data: list[dict[str, Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    message: Optional[str] = None
    query_duration_ms: Optional[float] = None
    viz_type: str = ""


def _resolve_viz_type(abstract_type: str) -> str:
    """Map abstract chart type to current Superset viz_type plugin."""
    return VIZ_TYPE_MAP.get(abstract_type, abstract_type)


def _build_query_payload(
    config: ChartConfig,
    dataset_id: int,
) -> dict[str, Any]:
    """
    Build a Superset chart data query payload.

    Uses Superset's /api/v1/chart/data endpoint with column references
    (not raw SQL) to prevent injection.
    """
    resolved_viz = _resolve_viz_type(config.viz_type)

    # Build metrics as Superset-format aggregation expressions
    query_metrics = []
    for m in config.metrics:
        if isinstance(m, str):
            query_metrics.append({"label": m, "expressionType": "SIMPLE", "column": {"column_name": m}, "aggregate": "SUM"})
        elif isinstance(m, dict):
            query_metrics.append(m)

    # Build filters as Superset adhoc_filters
    adhoc_filters = []
    for f in config.filters:
        col = f.get("column", "")
        op = f.get("operator", "==")
        val = f.get("value")
        adhoc_filters.append({
            "expressionType": "SIMPLE",
            "clause": "WHERE",
            "subject": col,
            "operator": op,
            "comparator": val,
            "isExtra": False,
        })

    payload = {
        "datasource": {"id": dataset_id, "type": "table"},
        "queries": [
            {
                "metrics": query_metrics,
                "groupby": config.dimensions,
                "time_range": config.time_range,
                "granularity_sqla": config.time_column,
                "time_grain_sqla": config.time_grain,
                "filters": adhoc_filters,
                "row_limit": min(config.row_limit, PREVIEW_ROW_LIMIT),
                "order_desc": True,
            }
        ],
        "result_format": "json",
        "result_type": "results",
    }

    return payload


class ChartQueryService:
    """Executes chart preview queries against Superset."""

    def __init__(
        self,
        superset_url: Optional[str] = None,
        superset_username: Optional[str] = None,
        superset_password: Optional[str] = None,
    ):
        self._superset_url = (superset_url or os.getenv("SUPERSET_EMBED_URL", "")).rstrip("/")
        self._username = superset_username or os.getenv("SUPERSET_USERNAME", "admin")
        self._password = superset_password or os.getenv("SUPERSET_PASSWORD", "admin")
        self._token: Optional[str] = None
        self._csrf: Optional[str] = None

        # Preview cache: {(dataset_name, config_hash, tenant_id): (timestamp, result)}
        self._cache: dict[tuple[str, str, str], tuple[float, ChartPreviewResult]] = {}

    def _ensure_auth(self, client: httpx.Client) -> None:
        if self._token:
            return
        resp = client.post(
            f"{self._superset_url}/api/v1/security/login",
            json={
                "username": self._username,
                "password": self._password,
                "provider": "db",
            },
            timeout=PREVIEW_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

        csrf_resp = client.get(
            f"{self._superset_url}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=PREVIEW_TIMEOUT_SECONDS,
        )
        csrf_resp.raise_for_status()
        self._csrf = csrf_resp.json().get("result", "")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-CSRFToken": self._csrf or "",
            "Content-Type": "application/json",
        }

    def _get_cached_preview(
        self, dataset_name: str, config_hash: str, tenant_id: str
    ) -> Optional[ChartPreviewResult]:
        """Return cached preview if fresh, else None."""
        key = (dataset_name, config_hash, tenant_id)
        entry = self._cache.get(key)
        if entry is None:
            return None
        cached_at, result = entry
        if (time.time() - cached_at) > PREVIEW_CACHE_TTL_SECONDS:
            return None
        return result

    def _set_cached_preview(
        self, dataset_name: str, config_hash: str, tenant_id: str, result: ChartPreviewResult
    ) -> None:
        key = (dataset_name, config_hash, tenant_id)
        self._cache[key] = (time.time(), result)

    def _resolve_dataset_id(self, dataset_name: str, client: httpx.Client) -> Optional[int]:
        """Look up Superset dataset ID by table name."""
        resp = client.get(
            f"{self._superset_url}/api/v1/dataset/",
            headers=self._auth_headers(),
            params={
                "q": json.dumps({
                    "filters": [{"col": "table_name", "opr": "eq", "value": dataset_name}],
                })
            },
        )
        resp.raise_for_status()
        results = resp.json().get("result", [])
        if results:
            return results[0]["id"]
        return None

    def execute_preview(
        self,
        config: ChartConfig,
        tenant_id: str,
    ) -> ChartPreviewResult:
        """
        Execute a chart preview query.

        - 100-row limit enforced
        - 10-second timeout
        - Cached for 60s keyed by (dataset_name, config_hash, tenant_id)
        - High-cardinality GROUP BY truncated to MAX_GROUPBY_CARDINALITY
        """
        c_hash = config.config_hash()

        # Check cache (shared across concurrent users in same tenant)
        cached = self._get_cached_preview(config.dataset_name, c_hash, tenant_id)
        if cached is not None:
            logger.info(
                "chart_preview.cache_hit",
                extra={
                    "tenant_id": tenant_id,
                    "dataset_name": config.dataset_name,
                    "config_hash": c_hash,
                },
            )
            return cached

        start_ms = time.time() * 1000

        try:
            with httpx.Client(timeout=PREVIEW_TIMEOUT_SECONDS) as client:
                self._ensure_auth(client)

                dataset_id = self._resolve_dataset_id(config.dataset_name, client)
                if dataset_id is None:
                    return ChartPreviewResult(
                        message=f"Dataset '{config.dataset_name}' not found in Superset",
                        viz_type=_resolve_viz_type(config.viz_type),
                    )

                payload = _build_query_payload(config, dataset_id)
                resp = client.post(
                    f"{self._superset_url}/api/v1/chart/data",
                    headers=self._auth_headers(),
                    json=payload,
                )
                resp.raise_for_status()

                query_result = resp.json()
                query_data = query_result.get("result", [{}])
                if not query_data:
                    return ChartPreviewResult(
                        message="No data available for the selected time range",
                        viz_type=_resolve_viz_type(config.viz_type),
                        query_duration_ms=time.time() * 1000 - start_ms,
                    )

                first_result = query_data[0] if isinstance(query_data, list) else query_data
                rows = first_result.get("data", [])
                columns = list(first_result.get("colnames", []))

                # Empty dataset handling
                if not rows:
                    result = ChartPreviewResult(
                        data=[],
                        columns=columns,
                        row_count=0,
                        message="No data available for the selected time range",
                        viz_type=_resolve_viz_type(config.viz_type),
                        query_duration_ms=time.time() * 1000 - start_ms,
                    )
                    self._set_cached_preview(config.dataset_name, c_hash, tenant_id, result)
                    return result

                # Truncate high-cardinality GROUP BY results
                truncated = False
                if config.dimensions and len(rows) > MAX_GROUPBY_CARDINALITY:
                    rows = rows[:MAX_GROUPBY_CARDINALITY]
                    truncated = True

                result = ChartPreviewResult(
                    data=rows,
                    columns=columns,
                    row_count=len(rows),
                    truncated=truncated,
                    viz_type=_resolve_viz_type(config.viz_type),
                    query_duration_ms=time.time() * 1000 - start_ms,
                )
                self._set_cached_preview(config.dataset_name, c_hash, tenant_id, result)
                return result

        except httpx.TimeoutException:
            logger.warning(
                "chart_preview.timeout",
                extra={
                    "tenant_id": tenant_id,
                    "dataset_name": config.dataset_name,
                    "timeout_seconds": PREVIEW_TIMEOUT_SECONDS,
                },
            )
            return ChartPreviewResult(
                message=f"Preview query timed out after {PREVIEW_TIMEOUT_SECONDS}s",
                viz_type=_resolve_viz_type(config.viz_type),
                query_duration_ms=time.time() * 1000 - start_ms,
            )
        except Exception as exc:
            logger.error(
                "chart_preview.query_failed",
                extra={
                    "tenant_id": tenant_id,
                    "dataset_name": config.dataset_name,
                    "error": str(exc),
                },
            )
            return ChartPreviewResult(
                message=f"Preview query failed: {exc}",
                viz_type=_resolve_viz_type(config.viz_type),
                query_duration_ms=time.time() * 1000 - start_ms,
            )
