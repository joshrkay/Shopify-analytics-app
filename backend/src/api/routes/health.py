"""
Liveness and readiness endpoints.

- ``GET /health`` is a shallow liveness probe used by Render's load balancer.
  It must stay fast and never 503 for transient downstream issues.
- ``GET /api/health/readiness`` is a deep readiness probe that verifies the
  required identity tables exist and that Redis is reachable. Used by
  operators and pre-deploy smoke tests.
"""

import logging
import os
import time
from typing import Any

import redis
from fastapi import APIRouter, Depends, Response, status

from src.database.session import get_db_session
from src.middleware.rate_limit import get_rate_limiter
from src.platform.db_readiness import (
    REQUIRED_IDENTITY_TABLES,
    check_required_tables,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health():
    """Shallow liveness probe — must never fail for downstream issues."""
    return {"status": "ok"}


def _check_redis_component() -> dict[str, Any]:
    """
    Ping Redis via the rate limiter's connection. Non-fatal for readiness:
    if Redis is unreachable the service still answers requests (rate
    limiting degrades gracefully) but operators should see the failure in
    the readiness payload so they can act.
    """
    if not os.getenv("REDIS_URL"):
        return {"ready": False, "reason": "not_configured"}

    try:
        limiter = get_rate_limiter()
        client = limiter._get_redis()
        start = time.perf_counter()
        client.ping()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {"ready": True, "latency_ms": latency_ms}
    except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as exc:
        logger.warning(
            "Redis readiness check failed",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        return {"ready": False, "reason": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("Unexpected error during Redis readiness check")
        return {"ready": False, "reason": f"{type(exc).__name__}: {exc}"}


@router.get("/api/health/readiness")
async def readiness(response: Response, db=Depends(get_db_session)):
    """
    Deep readiness probe.

    Components:
    - ``database``: required identity tables exist (blocking — 503 if missing)
    - ``redis``: reachable via PING (non-blocking — logged but not fatal)
    """
    db_result = check_required_tables(db, REQUIRED_IDENTITY_TABLES)
    database_component = {
        "ready": db_result.ready,
        "checked_tables": db_result.checked_tables,
        "missing_tables": db_result.missing_tables,
    }

    redis_component = _check_redis_component()

    # Overall readiness is gated on the database only. Redis degradation
    # is surfaced in the payload so Render + operators can see it, but it
    # does not take the service out of rotation.
    overall_ready = db_result.ready
    if not overall_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": overall_ready,
        "status": "ready" if overall_ready else "not_ready",
        "components": {
            "database": database_component,
            "redis": redis_component,
        },
        # Legacy shape kept for backwards compatibility with existing
        # monitors / dashboards that look at the ``checks`` key.
        "checks": {
            "database": "ok" if db_result.ready else "missing_tables",
            "identity_tables": {
                "required": db_result.checked_tables,
                "missing": db_result.missing_tables,
            },
        },
    }
