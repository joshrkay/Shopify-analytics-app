"""
Tests for RequestTimeoutMiddleware.

Verifies that:
- Requests exceeding REQUEST_TIMEOUT_SECONDS return HTTP 504.
- Requests completing under the timeout are unaffected.
- Allowlisted paths (``/health``) are never timed out.
- The timeout is read per-request from the environment (so tests can
  override without re-instantiating the middleware).
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.request_timeout import RequestTimeoutMiddleware


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "1")

    fastapi_app = FastAPI()
    fastapi_app.add_middleware(RequestTimeoutMiddleware)

    @fastapi_app.get("/slow")
    async def slow():
        await asyncio.sleep(3)
        return {"ok": True}

    @fastapi_app.get("/fast")
    async def fast():
        return {"ok": True}

    @fastapi_app.get("/health")
    async def health_endpoint():
        await asyncio.sleep(2)  # longer than the 1s limit
        return {"status": "ok"}

    return fastapi_app


def test_slow_request_times_out_with_504(app):
    client = TestClient(app)
    start = time.monotonic()
    resp = client.get("/slow")
    elapsed = time.monotonic() - start

    assert resp.status_code == 504
    body = resp.json()
    assert body["error"] == "request_timeout"
    assert body["timeout_seconds"] == 1
    # Should time out close to 1s, well before the handler's 3s sleep.
    assert elapsed < 2.5, f"timeout middleware did not abort in time (elapsed={elapsed})"


def test_fast_request_is_not_affected(app):
    client = TestClient(app)
    resp = client.get("/fast")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_health_endpoint_is_allowlisted(app):
    """
    /health is in the allowlist so even a handler that sleeps longer
    than the timeout must still return 200. This keeps Render's liveness
    probe immune to the middleware.
    """
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_invalid_timeout_env_falls_back_to_default(monkeypatch):
    from src.middleware.request_timeout import _get_timeout_seconds, DEFAULT_TIMEOUT_SECONDS

    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "not-a-number")
    assert _get_timeout_seconds() == float(DEFAULT_TIMEOUT_SECONDS)

    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "-5")
    assert _get_timeout_seconds() == float(DEFAULT_TIMEOUT_SECONDS)

    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "10")
    assert _get_timeout_seconds() == 10.0
