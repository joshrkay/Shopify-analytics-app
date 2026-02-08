"""
Rate limiting middleware using Redis sliding window.

Protects API endpoints from abuse by enforcing per-user, per-tenant,
per-endpoint request limits using a Redis-backed sliding window algorithm.

Features:
- Per-user + per-tenant rate limiting
- Configurable limits via env vars
- Returns 429 with Retry-After header when exceeded
- Emits rate_limit.triggered audit event via structured logging
- Graceful degradation if Redis is unavailable (allow request, log warning)

Configuration (environment variables):
- RATE_LIMIT_EMBED_TOKEN:    Max requests per window (default: "30")
- RATE_LIMIT_WINDOW_SECONDS: Window duration in seconds (default: "60")
- RATE_LIMIT_ENABLED:        Kill switch (default: "true")
- REDIS_URL:                 Redis connection URL (default: "redis://redis:6379/0")

Usage (FastAPI dependency injection):
    from src.middleware.rate_limit import rate_limit_dependency

    @router.post("/api/v1/embed/token")
    async def generate_token(
        request: Request,
        _rate_limit=Depends(rate_limit_dependency("embed_token")),
    ):
        ...

SECURITY: user_id and tenant_id are always extracted from JWT via
TenantContext, never from request body or query parameters.
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

import redis
from fastapi import Depends, HTTPException, Request, status

from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _is_rate_limit_enabled() -> bool:
    """Check if rate limiting is enabled via environment variable."""
    return os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")


def _get_default_limit() -> int:
    """Get the default rate limit from environment."""
    return int(os.getenv("RATE_LIMIT_EMBED_TOKEN", "30"))


def _get_default_window() -> int:
    """Get the default window duration from environment."""
    return int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


# ---------------------------------------------------------------------------
# Rate limit result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RateLimitResult:
    """
    Result of a rate limit check.

    Attributes:
        allowed:     Whether the request is allowed.
        remaining:   Number of requests remaining in the current window.
        limit:       Maximum number of requests allowed per window.
        reset_at:    Unix timestamp when the current window resets.
        retry_after: Seconds until the client should retry (0 if allowed).
    """

    allowed: bool
    remaining: int
    limit: int
    reset_at: float
    retry_after: int


# ---------------------------------------------------------------------------
# RateLimiter class
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Redis-backed sliding window rate limiter.

    Uses sorted sets where each member is a unique request ID scored by
    its timestamp. On each check the window is trimmed to the last
    ``window_seconds`` seconds and the remaining member count is compared
    against the configured limit.

    If Redis is unavailable the limiter degrades gracefully: requests are
    allowed and a warning is logged.
    """

    def __init__(
        self,
        redis_url: str,
        default_limit: int = 30,
        window_seconds: int = 60,
    ):
        self.redis_url = redis_url
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self._redis: Optional[redis.Redis] = None

    # -- Redis connection (lazy) -----------------------------------------

    def _get_redis(self) -> redis.Redis:
        """
        Get or create a Redis connection.

        The connection is created lazily on first use so that the module
        can be imported even when Redis is not yet available.
        """
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        return self._redis

    # -- Core sliding window check ---------------------------------------

    def check_rate_limit(
        self,
        user_id: str,
        tenant_id: str,
        endpoint: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Check whether a request is allowed under the sliding window.

        Algorithm:
        1. Build key ``ratelimit:{endpoint}:{tenant_id}:{user_id}``
        2. Remove sorted-set members with score < (now - window)
        3. Count remaining members
        4. If count >= limit  -> denied
        5. Otherwise          -> add current timestamp, set TTL, allow

        Args:
            user_id:   Authenticated user ID (from JWT).
            tenant_id: Tenant ID (from JWT).
            endpoint:  Logical endpoint name (e.g. ``"embed_token"``).
            limit:     Override for the per-window request limit.
            window:    Override for the window duration in seconds.

        Returns:
            :class:`RateLimitResult` describing the outcome.
        """
        effective_limit = limit if limit is not None else self.default_limit
        effective_window = window if window is not None else self.window_seconds

        now = time.time()
        window_start = now - effective_window
        reset_at = now + effective_window

        key = f"ratelimit:{endpoint}:{tenant_id}:{user_id}"

        try:
            r = self._get_redis()

            # Atomic pipeline: trim + count + (conditionally) add
            pipe = r.pipeline(transaction=True)
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = pipe.execute()

            current_count: int = results[1]

            if current_count >= effective_limit:
                # Exceeded - compute retry_after from oldest entry that
                # will drop out of the window.
                retry_after = max(1, int(effective_window - (now - window_start)))
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    limit=effective_limit,
                    reset_at=reset_at,
                    retry_after=retry_after,
                )

            # Allowed - record this request.  Use ``now`` as both score
            # and a unique-enough member (add a small counter to handle
            # sub-millisecond bursts).
            member = f"{now}:{user_id}:{current_count}"
            pipe2 = r.pipeline(transaction=True)
            pipe2.zadd(key, {member: now})
            pipe2.expire(key, effective_window + 10)  # TTL slightly beyond window
            pipe2.execute()

            remaining = max(0, effective_limit - current_count - 1)

            return RateLimitResult(
                allowed=True,
                remaining=remaining,
                limit=effective_limit,
                reset_at=reset_at,
                retry_after=0,
            )

        except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as exc:
            # Graceful degradation: allow the request and log a warning.
            logger.warning(
                "Redis unavailable for rate limiting - allowing request (fail-open)",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "endpoint": endpoint,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                },
            )
            return RateLimitResult(
                allowed=True,
                remaining=effective_limit,
                limit=effective_limit,
                reset_at=reset_at,
                retry_after=0,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_rate_limiter_instance: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """
    Return the module-level :class:`RateLimiter` singleton.

    Creates the instance on first call using ``REDIS_URL``, the default
    limit from ``RATE_LIMIT_EMBED_TOKEN``, and the window from
    ``RATE_LIMIT_WINDOW_SECONDS``.
    """
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _rate_limiter_instance = RateLimiter(
            redis_url=redis_url,
            default_limit=_get_default_limit(),
            window_seconds=_get_default_window(),
        )
    return _rate_limiter_instance


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def rate_limit_dependency(
    endpoint_name: str,
    limit: Optional[int] = None,
    window: Optional[int] = None,
) -> Callable:
    """
    Create a FastAPI dependency that enforces rate limiting.

    Returns an async function suitable for use with ``Depends()``.

    Args:
        endpoint_name: Logical name for the endpoint (used in the Redis
                       key, e.g. ``"embed_token"``).
        limit:         Override for the per-window request limit.  When
                       ``None`` the value from ``RATE_LIMIT_EMBED_TOKEN``
                       (or the RateLimiter default) is used.
        window:        Override for the window duration in seconds.  When
                       ``None`` the value from ``RATE_LIMIT_WINDOW_SECONDS``
                       (or the RateLimiter default) is used.

    Returns:
        An async dependency function.

    Usage::

        @router.post("/api/v1/embed/token")
        async def generate_token(
            request: Request,
            _rate_limit=Depends(rate_limit_dependency("embed_token")),
        ):
            ...

        # With custom limits:
        @router.post("/api/v1/embed/token/refresh")
        async def refresh_token(
            request: Request,
            _rate_limit=Depends(rate_limit_dependency("embed_token_refresh", limit=60, window=60)),
        ):
            ...
    """

    async def _dependency(request: Request) -> RateLimitResult:
        # Kill switch: skip rate limiting entirely when disabled.
        if not _is_rate_limit_enabled():
            return RateLimitResult(
                allowed=True,
                remaining=_get_default_limit(),
                limit=_get_default_limit(),
                reset_at=time.time() + _get_default_window(),
                retry_after=0,
            )

        # Extract tenant context (user_id + tenant_id from JWT).
        tenant_ctx = get_tenant_context(request)

        limiter = get_rate_limiter()
        result = limiter.check_rate_limit(
            user_id=tenant_ctx.user_id,
            tenant_id=tenant_ctx.tenant_id,
            endpoint=endpoint_name,
            limit=limit,
            window=window,
        )

        if not result.allowed:
            # Emit structured audit log (no DB session required).
            logger.warning(
                "Rate limit triggered",
                extra={
                    "action": "rate_limit.triggered",
                    "user_id": tenant_ctx.user_id,
                    "tenant_id": tenant_ctx.tenant_id,
                    "endpoint": endpoint_name,
                    "limit": result.limit,
                    "window_seconds": window if window is not None else limiter.window_seconds,
                    "retry_after": result.retry_after,
                    "reset_at": result.reset_at,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": (
                        "Too many requests. Please wait before retrying."
                    ),
                    "retry_after": result.retry_after,
                    "limit": result.limit,
                },
                headers={"Retry-After": str(result.retry_after)},
            )

        return result

    return _dependency
