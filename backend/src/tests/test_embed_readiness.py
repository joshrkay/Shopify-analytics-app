"""Tests for embed readiness endpoint."""

import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.embed import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _restore_env(old_secret, old_url, old_dashboards):
    if old_secret is None:
        os.environ.pop('SUPERSET_JWT_SECRET', None)
    else:
        os.environ['SUPERSET_JWT_SECRET'] = old_secret

    if old_url is None:
        os.environ.pop('SUPERSET_EMBED_URL', None)
    else:
        os.environ['SUPERSET_EMBED_URL'] = old_url

    if old_dashboards is None:
        os.environ.pop('ALLOWED_EMBED_DASHBOARDS', None)
    else:
        os.environ['ALLOWED_EMBED_DASHBOARDS'] = old_dashboards


def test_embed_readiness_ready_when_all_env_present():
    old_secret = os.environ.get('SUPERSET_JWT_SECRET')
    old_url = os.environ.get('SUPERSET_EMBED_URL')
    old_dashboards = os.environ.get('ALLOWED_EMBED_DASHBOARDS')

    os.environ['SUPERSET_JWT_SECRET'] = 'secret'
    os.environ['SUPERSET_EMBED_URL'] = 'https://analytics.example.com'
    os.environ['ALLOWED_EMBED_DASHBOARDS'] = 'overview,sales'

    try:
        response = client.get('/api/v1/embed/health/readiness')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'ready'
        assert body['embed_configured'] is True
        assert body['superset_url_configured'] is True
        assert body['allowed_dashboards_configured'] is True
    finally:
        _restore_env(old_secret, old_url, old_dashboards)


def test_embed_readiness_not_ready_when_dashboards_env_missing():
    """Missing ALLOWED_EMBED_DASHBOARDS returns not_ready."""
    old_secret = os.environ.get('SUPERSET_JWT_SECRET')
    old_url = os.environ.get('SUPERSET_EMBED_URL')
    old_dashboards = os.environ.get('ALLOWED_EMBED_DASHBOARDS')

    os.environ['SUPERSET_JWT_SECRET'] = 'secret'
    os.environ['SUPERSET_EMBED_URL'] = 'https://analytics.example.com'
    os.environ['ALLOWED_EMBED_DASHBOARDS'] = ''

    try:
        response = client.get('/api/v1/embed/health/readiness')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'not_ready'
        assert body['allowed_dashboards_configured'] is False
        assert body['message'] == 'ALLOWED_EMBED_DASHBOARDS not configured'
    finally:
        _restore_env(old_secret, old_url, old_dashboards)


def test_embed_readiness_not_ready_when_jwt_secret_missing():
    """Missing SUPERSET_JWT_SECRET returns not_ready with embed_configured=False."""
    old_secret = os.environ.get('SUPERSET_JWT_SECRET')
    old_url = os.environ.get('SUPERSET_EMBED_URL')
    old_dashboards = os.environ.get('ALLOWED_EMBED_DASHBOARDS')

    os.environ.pop('SUPERSET_JWT_SECRET', None)
    os.environ['SUPERSET_EMBED_URL'] = 'https://analytics.example.com'
    os.environ['ALLOWED_EMBED_DASHBOARDS'] = 'overview'

    try:
        response = client.get('/api/v1/embed/health/readiness')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'not_ready'
        assert body['embed_configured'] is False
        assert body['message'] == 'SUPERSET_JWT_SECRET not configured'
    finally:
        _restore_env(old_secret, old_url, old_dashboards)


def test_embed_readiness_not_ready_when_superset_url_missing():
    """Missing SUPERSET_EMBED_URL returns not_ready."""
    old_secret = os.environ.get('SUPERSET_JWT_SECRET')
    old_url = os.environ.get('SUPERSET_EMBED_URL')
    old_dashboards = os.environ.get('ALLOWED_EMBED_DASHBOARDS')

    os.environ['SUPERSET_JWT_SECRET'] = 'secret'
    os.environ.pop('SUPERSET_EMBED_URL', None)
    os.environ['ALLOWED_EMBED_DASHBOARDS'] = 'overview'

    try:
        response = client.get('/api/v1/embed/health/readiness')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'not_ready'
        assert body['superset_url_configured'] is False
        assert body['message'] == 'SUPERSET_EMBED_URL not configured'
    finally:
        _restore_env(old_secret, old_url, old_dashboards)


def test_embed_readiness_message_is_none_when_ready():
    """When fully configured, message should be None."""
    old_secret = os.environ.get('SUPERSET_JWT_SECRET')
    old_url = os.environ.get('SUPERSET_EMBED_URL')
    old_dashboards = os.environ.get('ALLOWED_EMBED_DASHBOARDS')

    os.environ['SUPERSET_JWT_SECRET'] = 'secret'
    os.environ['SUPERSET_EMBED_URL'] = 'https://analytics.example.com'
    os.environ['ALLOWED_EMBED_DASHBOARDS'] = 'overview,sales'

    try:
        response = client.get('/api/v1/embed/health/readiness')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'ready'
        assert body['message'] is None
    finally:
        _restore_env(old_secret, old_url, old_dashboards)
