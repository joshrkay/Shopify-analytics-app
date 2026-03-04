"""
Integration tests for Search API.

Layer 2 — Tests HTTP request → response via FastAPI TestClient.
Uses dependency_overrides for DB session injection.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.search import router, _get_db


@pytest.fixture
def mock_tenant_ctx():
    ctx = Mock()
    ctx.tenant_id = "tenant-search-api"
    ctx.user_id = "user-1"
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def app(mock_db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_get_db] = lambda: mock_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestGlobalSearch:

    def test_returns_matching_pages(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search?q=home")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        page_results = [r for r in data["results"] if r["type"] == "page"]
        assert any(r["title"] == "Home" for r in page_results)

    def test_min_2_chars_accepted(self, client, mock_tenant_ctx, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search?q=ho")

        assert response.status_code == 200

    def test_1_char_query_rejected(self, client, mock_tenant_ctx):
        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search?q=a")

        assert response.status_code == 422

    def test_missing_query_rejected(self, client, mock_tenant_ctx):
        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search")

        assert response.status_code == 422

    def test_db_error_graceful_degradation(self, client, mock_tenant_ctx, mock_db):
        """Dashboard search failure should still return static page matches."""
        mock_db.execute.side_effect = Exception("analytics schema not found")

        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search?q=alert")

        assert response.status_code == 200
        data = response.json()
        # Static "Alerts" page should still match even though DB failed
        assert any(r["title"] == "Alerts" for r in data["results"])

    def test_dashboard_results_included(self, client, mock_tenant_ctx, mock_db):
        """Dashboard search results should be typed as 'dashboard'."""
        mock_row = Mock()
        mock_row.id = "dash-1"
        mock_row.title = "Revenue Dashboard"
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        with patch("src.api.routes.search.get_tenant_context", return_value=mock_tenant_ctx):
            response = client.get("/api/search?q=revenue")

        assert response.status_code == 200
        data = response.json()
        dashboard_results = [r for r in data["results"] if r["type"] == "dashboard"]
        assert len(dashboard_results) == 1
        assert dashboard_results[0]["title"] == "Revenue Dashboard"
        assert dashboard_results[0]["path"] == "/dashboards/dash-1"
