"""
Tests for the extended /api/health/readiness endpoint.

Verifies that:
- The ``components`` payload includes both ``database`` and ``redis``.
- Database readiness gates overall readiness (503 if missing tables).
- Redis degradation is reported but does NOT take the service out of
  rotation (overall ready=true even when Redis ping fails).
- ``/health`` remains shallow and fast.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import health as health_routes
from src.database.session import get_db_session
from src.platform.db_readiness import DBReadinessResult


@pytest.fixture
def app():
    fastapi_app = FastAPI()
    fastapi_app.include_router(health_routes.router)

    # Stub the DB dependency so the readiness route does not require a
    # real database. Tests override ``check_required_tables`` below to
    # drive the DB component's status.
    def _fake_db():
        yield MagicMock()

    fastapi_app.dependency_overrides[get_db_session] = _fake_db
    return fastapi_app


def _patch_db(ready: bool, missing=None):
    return patch.object(
        health_routes,
        "check_required_tables",
        return_value=DBReadinessResult(
            ready=ready,
            missing_tables=list(missing or []),
            checked_tables=["users", "tenants", "user_tenant_roles"],
        ),
    )


def test_liveness_is_shallow(app):
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_all_components_ok(app, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_limiter = MagicMock()
    fake_limiter._get_redis.return_value = fake_client

    with _patch_db(ready=True), patch.object(
        health_routes, "get_rate_limiter", return_value=fake_limiter
    ):
        client = TestClient(app)
        resp = client.get("/api/health/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["components"]["database"]["ready"] is True
    assert body["components"]["redis"]["ready"] is True
    assert "latency_ms" in body["components"]["redis"]


def test_readiness_503_when_database_missing_tables(app, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_limiter = MagicMock()
    fake_limiter._get_redis.return_value = fake_client

    with _patch_db(ready=False, missing=["users"]), patch.object(
        health_routes, "get_rate_limiter", return_value=fake_limiter
    ):
        client = TestClient(app)
        resp = client.get("/api/health/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["components"]["database"]["ready"] is False
    assert "users" in body["components"]["database"]["missing_tables"]


def test_readiness_stays_up_when_redis_unreachable(app, monkeypatch):
    """
    Redis is a non-blocking dependency for readiness — if it's down, we
    still want the DB-backed API to serve requests. The readiness
    payload surfaces the degradation so operators can see it.
    """
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    fake_client = MagicMock()
    fake_client.ping.side_effect = redis.ConnectionError("refused")
    fake_limiter = MagicMock()
    fake_limiter._get_redis.return_value = fake_client

    with _patch_db(ready=True), patch.object(
        health_routes, "get_rate_limiter", return_value=fake_limiter
    ):
        client = TestClient(app)
        resp = client.get("/api/health/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["components"]["database"]["ready"] is True
    assert body["components"]["redis"]["ready"] is False
    assert "reason" in body["components"]["redis"]


def test_readiness_reports_redis_not_configured(app, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    with _patch_db(ready=True):
        client = TestClient(app)
        resp = client.get("/api/health/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["components"]["redis"] == {"ready": False, "reason": "not_configured"}
