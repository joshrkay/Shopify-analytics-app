"""
Data availability guard middleware for API endpoint enforcement.

Blocks or degrades downstream features based on data availability state:
- UNAVAILABLE -> API analytics endpoints return 503 with human-readable reason
- STALE       -> Allow through but attach warning to request.state
- FRESH       -> All features enabled

Provides:
- require_data_available:  Decorator that blocks requests with HTTP 503 when
                           ANY source is UNAVAILABLE
- require_data_fresh:      Strict decorator that requires ALL sources to be FRESH
- DataAvailabilityGuard:   Dependency-injection guard for use with Depends()
- check_data_availability: Standalone function that evaluates availability and
                           attaches result to request.state

Error responses are human-readable and never expose internal system details
(thresholds, internal state names, SLA details, technical error codes).

SECURITY: tenant_id is always extracted from JWT via TenantContext, never from
request body or query parameters.

Usage (decorator):
    @router.get("/api/analytics/orders")
    @require_data_available(source_types=["shopify_orders"])
    async def get_orders(request: Request):
        ...

Usage (dependency injection):
    @router.get("/api/analytics/overview")
    async def get_overview(
        request: Request,
        guard: DataAvailabilityGuard = Depends(DataAvailabilityGuard),
    ):
        guard.require_available(request)
        ...
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.models.data_availability import AvailabilityState
from src.services.data_availability_service import (
    DataAvailabilityResult,
    DataAvailabilityService,
    resolve_sla_key,
)
from src.database.session import get_db_session
from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Friendly source name mapping
# ---------------------------------------------------------------------------

SOURCE_FRIENDLY_NAMES: Dict[str, str] = {
    "shopify_orders": "Shopify Orders",
    "facebook_ads": "Facebook Ads",
    "google_ads": "Google Ads",
    "tiktok_ads": "TikTok Ads",
    "snapchat_ads": "Snapchat Ads",
    "email": "Email Marketing",
    "sms": "SMS Marketing",
}

# Default retry hint returned in 503 responses (seconds).
_DEFAULT_RETRY_AFTER_SECONDS = 300


def _friendly_name(source_type: str) -> str:
    """Return a user-facing name for a source type, falling back to title-case."""
    return SOURCE_FRIENDLY_NAMES.get(
        source_type,
        source_type.replace("_", " ").title(),
    )


# ---------------------------------------------------------------------------
# Human-readable messages (never expose internal details)
# ---------------------------------------------------------------------------

_MSG_UNAVAILABLE = (
    "Your data is temporarily unavailable while we process updates. "
    "Please try again shortly."
)

_MSG_STALE_WARNING = (
    "Some of your data sources are being updated. "
    "Results may not reflect the latest changes."
)

_MSG_FRESH_REQUIRED_STALE = (
    "We are waiting for your latest data to finish syncing. "
    "Please try again in a few minutes."
)


# ---------------------------------------------------------------------------
# Guard result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DataAvailabilityCheckResult:
    """
    Result of a data-availability evaluation across one or more sources.

    Attached to ``request.state.data_availability`` by
    :func:`check_data_availability` so downstream handlers can inspect it.
    """

    is_available: bool
    has_warnings: bool = False
    warning_message: Optional[str] = None
    unavailable_sources: List[str] = field(default_factory=list)
    stale_sources: List[str] = field(default_factory=list)
    fresh_sources: List[str] = field(default_factory=list)
    evaluated_at: Optional[datetime] = None
    results: List[DataAvailabilityResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_available": self.is_available,
            "has_warnings": self.has_warnings,
            "warning_message": self.warning_message,
            "unavailable_sources": self.unavailable_sources,
            "stale_sources": self.stale_sources,
            "fresh_sources": self.fresh_sources,
        }


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def check_data_availability(
    request: Request,
    source_types: Optional[List[str]] = None,
) -> DataAvailabilityCheckResult:
    """
    Evaluate data availability for the current tenant and attach the result
    to ``request.state.data_availability``.

    When *source_types* is ``None``, all enabled sources for the tenant are
    evaluated.

    Args:
        request:      The incoming FastAPI request (must have tenant context
                      and a database session on ``request.state``).
        source_types: Optional list of SLA source keys to evaluate.  When
                      ``None``, :meth:`DataAvailabilityService.evaluate_all`
                      is used instead.

    Returns:
        :class:`DataAvailabilityCheckResult` summarising the evaluation.
    """
    tenant_ctx = get_tenant_context(request)
    db_session: Session = getattr(request.state, "db", None)

    if db_session is None:
        # Graceful degradation: if no DB session is available, allow the
        # request through and log a warning.
        logger.warning(
            "No database session on request.state; skipping availability check",
            extra={"tenant_id": tenant_ctx.tenant_id, "path": request.url.path},
        )
        result = DataAvailabilityCheckResult(
            is_available=True,
            evaluated_at=datetime.now(timezone.utc),
        )
        request.state.data_availability = result
        return result

    service = DataAvailabilityService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        billing_tier=tenant_ctx.billing_tier,
    )

    if source_types:
        results = [service.get_data_availability(st) for st in source_types]
    else:
        results = service.evaluate_all()

    unavailable: List[str] = []
    stale: List[str] = []
    fresh: List[str] = []

    for r in results:
        friendly = _friendly_name(r.source_type)
        if r.state == AvailabilityState.UNAVAILABLE.value:
            unavailable.append(friendly)
        elif r.state == AvailabilityState.STALE.value:
            stale.append(friendly)
        else:
            fresh.append(friendly)

    is_available = len(unavailable) == 0
    has_warnings = len(stale) > 0
    warning_message = _MSG_STALE_WARNING if has_warnings else None

    check_result = DataAvailabilityCheckResult(
        is_available=is_available,
        has_warnings=has_warnings,
        warning_message=warning_message,
        unavailable_sources=unavailable,
        stale_sources=stale,
        fresh_sources=fresh,
        evaluated_at=datetime.now(timezone.utc),
        results=results,
    )

    request.state.data_availability = check_result

    logger.info(
        "Data availability evaluated",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "path": request.url.path,
            "is_available": is_available,
            "unavailable_count": len(unavailable),
            "stale_count": len(stale),
            "fresh_count": len(fresh),
        },
    )

    return check_result


# ---------------------------------------------------------------------------
# 503 response builder
# ---------------------------------------------------------------------------

def _build_unavailable_response(
    affected_sources: List[str],
    message: Optional[str] = None,
) -> JSONResponse:
    """
    Build a standard 503 JSON response for data unavailability.

    The response body follows the project-wide error envelope pattern and
    includes only human-readable details.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "data_unavailable",
            "error_code": "DATA_UNAVAILABLE",
            "message": message or _MSG_UNAVAILABLE,
            "status": "unavailable",
            "affected_sources": affected_sources,
            "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
        },
        headers={
            "Retry-After": str(_DEFAULT_RETRY_AFTER_SECONDS),
        },
    )


# ---------------------------------------------------------------------------
# Decorator: require_data_available
# ---------------------------------------------------------------------------

def require_data_available(
    source_types: Optional[List[str]] = None,
):
    """
    Decorator that blocks requests with HTTP 503 when **any** evaluated
    source is UNAVAILABLE.  STALE sources are allowed through with a
    warning attached to ``request.state``.

    Args:
        source_types: SLA source keys to check (e.g.
            ``["shopify_orders", "facebook_ads"]``).  When ``None``, all
            enabled sources for the tenant are evaluated.

    Usage::

        @router.get("/api/analytics/orders")
        @require_data_available(source_types=["shopify_orders"])
        async def get_orders(request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Locate the Request object in positional or keyword args.
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                raise ValueError(
                    "Request object not found in function arguments"
                )

            check_result = check_data_availability(request, source_types)

            if not check_result.is_available:
                tenant_ctx = get_tenant_context(request)
                logger.warning(
                    "Request blocked: data unavailable",
                    extra={
                        "tenant_id": tenant_ctx.tenant_id,
                        "path": request.url.path,
                        "affected_sources": check_result.unavailable_sources,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "data_unavailable",
                        "error_code": "DATA_UNAVAILABLE",
                        "message": _MSG_UNAVAILABLE,
                        "status": "unavailable",
                        "affected_sources": check_result.unavailable_sources,
                        "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                    },
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Decorator: require_data_fresh
# ---------------------------------------------------------------------------

def require_data_fresh(
    source_types: Optional[List[str]] = None,
):
    """
    Strict decorator that requires **all** evaluated sources to be FRESH.

    Both STALE and UNAVAILABLE sources will result in an HTTP 503 response.
    Use this for endpoints where even slightly outdated data is unacceptable
    (e.g. real-time alerting, AI insight generation).

    Args:
        source_types: SLA source keys to check.  When ``None``, all enabled
            sources for the tenant are evaluated.

    Usage::

        @router.post("/api/ai/generate")
        @require_data_fresh(source_types=["shopify_orders"])
        async def generate_insights(request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                raise ValueError(
                    "Request object not found in function arguments"
                )

            check_result = check_data_availability(request, source_types)

            # Block if ANY source is not FRESH.
            if not check_result.is_available:
                tenant_ctx = get_tenant_context(request)
                logger.warning(
                    "Request blocked (fresh required): data unavailable",
                    extra={
                        "tenant_id": tenant_ctx.tenant_id,
                        "path": request.url.path,
                        "affected_sources": check_result.unavailable_sources,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "data_unavailable",
                        "error_code": "DATA_UNAVAILABLE",
                        "message": _MSG_UNAVAILABLE,
                        "status": "unavailable",
                        "affected_sources": check_result.unavailable_sources,
                        "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                    },
                )

            if check_result.has_warnings:
                # STALE is not acceptable when freshness is required.
                tenant_ctx = get_tenant_context(request)
                logger.warning(
                    "Request blocked (fresh required): data stale",
                    extra={
                        "tenant_id": tenant_ctx.tenant_id,
                        "path": request.url.path,
                        "stale_sources": check_result.stale_sources,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "data_unavailable",
                        "error_code": "DATA_UNAVAILABLE",
                        "message": _MSG_FRESH_REQUIRED_STALE,
                        "status": "unavailable",
                        "affected_sources": check_result.stale_sources,
                        "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                    },
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Dependency-injection guard
# ---------------------------------------------------------------------------

class DataAvailabilityGuard:
    """
    FastAPI dependency-injection guard for data availability.

    Designed for use with ``Depends()`` in route signatures, following the
    same DI pattern used by :mod:`src.api.dependencies.entitlements`.

    Usage::

        @router.get("/api/analytics/overview")
        async def get_overview(
            request: Request,
            db: Session = Depends(get_db_session),
            guard: DataAvailabilityGuard = Depends(DataAvailabilityGuard),
        ):
            guard.require_available(request, source_types=["shopify_orders"])
            ...
    """

    def require_available(
        self,
        request: Request,
        source_types: Optional[List[str]] = None,
    ) -> DataAvailabilityCheckResult:
        """
        Check availability and raise HTTP 503 if any source is UNAVAILABLE.

        STALE sources are allowed through; a warning is attached to
        ``request.state.data_availability``.

        Returns:
            The :class:`DataAvailabilityCheckResult` for further inspection
            by the caller if needed.

        Raises:
            HTTPException: 503 when any source is UNAVAILABLE.
        """
        check_result = check_data_availability(request, source_types)

        if not check_result.is_available:
            tenant_ctx = get_tenant_context(request)
            logger.warning(
                "Guard blocked request: data unavailable",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "path": request.url.path,
                    "affected_sources": check_result.unavailable_sources,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "data_unavailable",
                    "error_code": "DATA_UNAVAILABLE",
                    "message": _MSG_UNAVAILABLE,
                    "status": "unavailable",
                    "affected_sources": check_result.unavailable_sources,
                    "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                },
            )

        return check_result

    def require_fresh(
        self,
        request: Request,
        source_types: Optional[List[str]] = None,
    ) -> DataAvailabilityCheckResult:
        """
        Strict check: raise HTTP 503 unless **all** sources are FRESH.

        Returns:
            The :class:`DataAvailabilityCheckResult`.

        Raises:
            HTTPException: 503 when any source is not FRESH.
        """
        check_result = check_data_availability(request, source_types)

        if not check_result.is_available:
            tenant_ctx = get_tenant_context(request)
            logger.warning(
                "Guard blocked request (fresh required): data unavailable",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "path": request.url.path,
                    "affected_sources": check_result.unavailable_sources,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "data_unavailable",
                    "error_code": "DATA_UNAVAILABLE",
                    "message": _MSG_UNAVAILABLE,
                    "status": "unavailable",
                    "affected_sources": check_result.unavailable_sources,
                    "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                },
            )

        if check_result.has_warnings:
            tenant_ctx = get_tenant_context(request)
            logger.warning(
                "Guard blocked request (fresh required): data stale",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "path": request.url.path,
                    "stale_sources": check_result.stale_sources,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "data_unavailable",
                    "error_code": "DATA_UNAVAILABLE",
                    "message": _MSG_FRESH_REQUIRED_STALE,
                    "status": "unavailable",
                    "affected_sources": check_result.stale_sources,
                    "retry_after_seconds": _DEFAULT_RETRY_AFTER_SECONDS,
                },
            )

        return check_result

    def check(
        self,
        request: Request,
        source_types: Optional[List[str]] = None,
    ) -> DataAvailabilityCheckResult:
        """
        Non-blocking check: evaluate availability and attach the result to
        ``request.state`` without raising.  Callers can inspect the returned
        :class:`DataAvailabilityCheckResult` to adapt their behaviour.
        """
        return check_data_availability(request, source_types)
