"""
Request-level timeout middleware.

Enforces a ceiling on the total duration of any single HTTP request so that
a wedged downstream call or a slow SQL query cannot tie up a worker
indefinitely and exhaust the connection pool.

Why this is needed:
- Individual HTTP clients (e.g. ``billing_client.py``) set their own
  timeouts, but there is no app-wide enforcement. A handler that forgets
  to pass ``timeout=`` to a dependency can still hang forever.
- Uvicorn's ``--timeout-keep-alive`` bounds idle connection time, not
  active request handlers.
- Database pool exhaustion due to a few stuck requests produces cascading
  503s — far harder to debug than an explicit 504.

Implementation note:
- This is a pure ASGI middleware (not ``BaseHTTPMiddleware``) because
  ``BaseHTTPMiddleware`` waits for the underlying handler task to finish
  before returning a response, which defeats the point of a timeout.
  Wrapping the downstream ASGI call in ``asyncio.wait_for`` lets us
  cancel the handler task and return a 504 immediately.

Configuration:
- ``REQUEST_TIMEOUT_SECONDS`` (default: 30) — ceiling in seconds.

Behavior on timeout:
- Returns HTTP 504 with JSON body ``{"error": "request_timeout", ...}``
- Logs the route, tenant_id, and correlation_id at ERROR level so
  operators can find the stuck endpoint.

Allowlist:
- ``/health`` and ``/api/health/readiness`` are skipped so that Render's
  load balancer health checks never time out due to this middleware
  (they already do their own bounded work).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30

# Paths exempt from the timeout middleware. Keep this tight — only the
# liveness/readiness probes should ever skip request-level bounds.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/health",
        "/api/health/readiness",
    }
)


def _get_timeout_seconds() -> float:
    raw = os.getenv("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid REQUEST_TIMEOUT_SECONDS value; falling back to default",
            extra={"raw_value": raw, "default": DEFAULT_TIMEOUT_SECONDS},
        )
        return float(DEFAULT_TIMEOUT_SECONDS)
    if value <= 0:
        return float(DEFAULT_TIMEOUT_SECONDS)
    return value


def _build_504_body(timeout_seconds: float) -> bytes:
    return json.dumps(
        {
            "error": "request_timeout",
            "detail": "Request exceeded maximum duration",
            "timeout_seconds": timeout_seconds,
        }
    ).encode("utf-8")


class RequestTimeoutMiddleware:
    """
    Pure-ASGI middleware that aborts any request exceeding the configured
    timeout with HTTP 504.

    The timeout is resolved per-request so tests can set
    ``REQUEST_TIMEOUT_SECONDS`` via ``monkeypatch.setenv`` without needing
    to re-instantiate the middleware.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowlist: Iterable[str] | None = None,
    ) -> None:
        self.app = app
        self._allowlist: frozenset[str] = (
            frozenset(allowlist) if allowlist is not None else _ALLOWLIST
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._allowlist:
            await self.app(scope, receive, send)
            return

        timeout = _get_timeout_seconds()

        # Track whether the handler has begun sending its own response.
        # Once the first "http.response.start" has gone out, the status
        # line is committed — we can no longer return a 504, we can only
        # let the handler finish (or close the connection).
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        task = asyncio.create_task(self.app(scope, receive, send_wrapper))

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            # Cancel the in-flight handler task. It may still take a
            # moment to unwind, but the client gets its 504 immediately.
            task.cancel()

            tenant_id = "unknown"
            correlation_id = "unknown"
            state = scope.get("state") or {}
            tenant_ctx = state.get("tenant_context") if isinstance(state, dict) else None
            if tenant_ctx is not None:
                tenant_id = getattr(tenant_ctx, "tenant_id", tenant_id) or tenant_id
            if isinstance(state, dict):
                correlation_id = state.get("correlation_id", correlation_id) or correlation_id

            logger.error(
                "Request exceeded timeout",
                extra={
                    "path": path,
                    "method": scope.get("method"),
                    "timeout_seconds": timeout,
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                },
            )

            if response_started:
                # The handler already started writing a response — we
                # can't prepend a 504 on the wire. Best we can do is let
                # the task finish / be cancelled and log the violation.
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                return

            body = _build_504_body(timeout)
            await send(
                {
                    "type": "http.response.start",
                    "status": 504,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("latin-1")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
