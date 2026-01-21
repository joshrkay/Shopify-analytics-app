"""
Tests for health endpoint and Render deployment validation.

CRITICAL: Health endpoint must return 200 for Render to mark service as healthy.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes import health
from src.platform.health import HealthChecker, get_health_checker


@pytest.fixture
def app():
    """Create FastAPI app with health route."""
    app = FastAPI()
    app.include_router(health.router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_health_checker():
    """Mock health checker with successful checks."""
    checker = MagicMock(spec=HealthChecker)
    checker.get_health_status.return_value = {
        "status": "ok",
        "timestamp": "2024-01-01T00:00:00",
        "service": "ai-growth-api",
        "checks": {
            "database": {"status": "ok", "message": "Database connection successful"},
            "environment": {
                "status": "ok",
                "present": ["FRONTEGG_CLIENT_ID", "DATABASE_URL"],
                "missing": [],
                "message": "2 vars present, 0 missing"
            }
        }
    }
    return checker


class TestHealthEndpoint:
    """Test health endpoint functionality."""
    
    def test_health_endpoint_returns_200_when_healthy(
        self,
        client,
        mock_health_checker,
        monkeypatch
    ):
        """
        QUALITY GATE: Health endpoint returns 200 when service is healthy.
        
        Render uses this to mark service as healthy.
        """
        # Mock health checker
        monkeypatch.setattr("src.api.routes.health.get_health_checker", lambda: mock_health_checker)
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ai-growth-api"
        assert "checks" in data
        assert data["checks"]["database"]["status"] == "ok"
    
    def test_health_endpoint_returns_503_when_degraded(
        self,
        client,
        monkeypatch
    ):
        """
        QUALITY GATE: Health endpoint returns 503 when service is degraded.
        
        Render will mark service as unhealthy if /health returns non-200.
        """
        # Mock degraded health status
        degraded_checker = MagicMock(spec=HealthChecker)
        degraded_checker.get_health_status.return_value = {
            "status": "degraded",
            "timestamp": "2024-01-01T00:00:00",
            "service": "ai-growth-api",
            "checks": {
                "database": {"status": "error", "message": "Database connection failed"},
                "environment": {
                    "status": "ok",
                    "present": ["FRONTEGG_CLIENT_ID"],
                    "missing": [],
                    "message": "1 vars present, 0 missing"
                }
            }
        }
        
        monkeypatch.setattr("src.api.routes.health.get_health_checker", lambda: degraded_checker)
        
        response = client.get("/health")
        
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"]["status"] == "error"
    
    def test_health_endpoint_includes_timestamp(self, client, mock_health_checker, monkeypatch):
        """Test that health endpoint includes timestamp."""
        monkeypatch.setattr("src.api.routes.health.get_health_checker", lambda: mock_health_checker)
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert data["timestamp"] is not None


class TestHealthChecker:
    """Test HealthChecker functionality."""
    
    def test_check_database_success(self, monkeypatch):
        """Test successful database check."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        
        # Mock SQLAlchemy engine
        with patch('src.platform.health.create_engine') as mock_create:
            mock_engine = MagicMock()
            mock_create.return_value = mock_engine
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            
            checker = HealthChecker()
            result = checker.check_database()
            
            assert result["status"] == "ok"
            assert "successful" in result["message"].lower()
    
    def test_check_database_missing_url(self, monkeypatch):
        """Test database check with missing DATABASE_URL."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        
        checker = HealthChecker()
        result = checker.check_database()
        
        assert result["status"] == "error"
        assert "not configured" in result["message"].lower()
    
    def test_check_environment_variables_all_present(self, monkeypatch):
        """Test environment check with all required vars present."""
        monkeypatch.setenv("FRONTEGG_CLIENT_ID", "test-id")
        monkeypatch.setenv("FRONTEGG_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        
        checker = HealthChecker()
        result = checker.check_environment_variables()
        
        assert result["status"] == "ok"
        assert "FRONTEGG_CLIENT_ID" in result["present"]
        assert "DATABASE_URL" in result["present"]
        assert len(result["missing"]) == 0
    
    def test_check_environment_variables_missing(self, monkeypatch):
        """Test environment check with missing required vars."""
        monkeypatch.delenv("FRONTEGG_CLIENT_ID", raising=False)
        monkeypatch.delenv("FRONTEGG_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        
        checker = HealthChecker()
        result = checker.check_environment_variables()
        
        assert result["status"] == "error"
        assert "FRONTEGG_CLIENT_ID" in result["missing"]
        assert len(result["missing"]) > 0
    
    def test_log_config_status_no_secrets(self, monkeypatch, caplog):
        """Test that log_config_status doesn't expose secrets."""
        import logging
        
        monkeypatch.setenv("FRONTEGG_CLIENT_ID", "secret-client-id")
        monkeypatch.setenv("FRONTEGG_CLIENT_SECRET", "secret-secret-value")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/db")
        
        with caplog.at_level(logging.INFO):
            checker = HealthChecker()
            checker.log_config_status()
        
        # CRITICAL: Verify no secret values in logs
        log_output = caplog.text
        assert "secret-client-id" not in log_output
        assert "secret-secret-value" not in log_output
        assert "password" not in log_output
        
        # But should log that vars are present
        assert "FRONTEGG_CLIENT_ID" in log_output or "Configuration status" in log_output
    
    def test_get_health_status_comprehensive(self, monkeypatch):
        """Test comprehensive health status."""
        monkeypatch.setenv("FRONTEGG_CLIENT_ID", "test-id")
        monkeypatch.setenv("FRONTEGG_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        
        with patch('src.platform.health.create_engine') as mock_create:
            mock_engine = MagicMock()
            mock_create.return_value = mock_engine
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            
            checker = HealthChecker()
            status = checker.get_health_status()
            
            assert "status" in status
            assert "timestamp" in status
            assert "service" in status
            assert "checks" in status
            assert "database" in status["checks"]
            assert "environment" in status["checks"]


class TestRenderDeploymentValidation:
    """Test Render-specific deployment validation."""
    
    def test_health_endpoint_reachable(self, client):
        """
        CRITICAL: Health endpoint must be reachable for Render.
        
        Render monitors /health to determine service health.
        """
        response = client.get("/health")
        
        # Should return some status (200 or 503)
        assert response.status_code in [200, 503]
        assert response.headers["content-type"] == "application/json"
    
    def test_health_endpoint_no_auth_required(self, client):
        """
        CRITICAL: Health endpoint must not require authentication.
        
        Render needs to access /health without JWT token.
        """
        # Make request without Authorization header
        response = client.get("/health")
        
        # Should not return 403 (Forbidden)
        assert response.status_code != 403
        assert response.status_code in [200, 503]
    
    def test_startup_database_check(self, monkeypatch):
        """Test that startup checks database connectivity."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
        
        with patch('src.platform.health.create_engine') as mock_create:
            mock_engine = MagicMock()
            mock_create.return_value = mock_engine
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            
            checker = HealthChecker()
            result = checker.check_database()
            
            # Should attempt connection
            assert mock_create.called
            assert result["status"] in ["ok", "error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])