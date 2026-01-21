"""
Render deployment health checks and validation.

Provides health check functionality for Render services:
- Database connectivity
- Environment variable validation
- Service status reporting
"""

import os
import logging
from typing import Dict, Optional
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class HealthChecker:
    """Health check service for Render deployment validation."""
    
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.redis_url = os.getenv("REDIS_URL")
        self._db_engine = None
        self._db_connected = False
    
    def check_database(self) -> Dict[str, any]:
        """
        Check database connectivity.
        
        Returns:
            Dict with 'status' (ok/error) and 'message'
        """
        if not self.db_url:
            return {
                "status": "error",
                "message": "DATABASE_URL not configured"
            }
        
        try:
            # Create engine if not exists
            if not self._db_engine:
                self._db_engine = create_engine(self.db_url, pool_pre_ping=True)
            
            # Test connection with a simple query
            with self._db_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            self._db_connected = True
            return {
                "status": "ok",
                "message": "Database connection successful"
            }
        except SQLAlchemyError as e:
            self._db_connected = False
            logger.error("Database connection failed", extra={"error": str(e)})
            return {
                "status": "error",
                "message": f"Database connection failed: {str(e)}"
            }
        except Exception as e:
            self._db_connected = False
            logger.error("Unexpected database error", extra={"error": str(e)})
            return {
                "status": "error",
                "message": f"Database check failed: {str(e)}"
            }
    
    def check_environment_variables(self) -> Dict[str, any]:
        """
        Check required environment variables are present.
        
        Returns:
            Dict with 'status', 'present', and 'missing' lists
        """
        required_vars = [
            "FRONTEGG_CLIENT_ID",
            "FRONTEGG_CLIENT_SECRET",
            "DATABASE_URL",
        ]
        
        # Optional but recommended
        optional_vars = [
            "REDIS_URL",
            "SHOPIFY_API_KEY",
            "OPENROUTER_API_KEY",
            "LAUNCHDARKLY_SDK_KEY",
        ]
        
        present = []
        missing = []
        
        for var in required_vars:
            if os.getenv(var):
                present.append(var)
            else:
                missing.append(var)
        
        for var in optional_vars:
            if os.getenv(var):
                present.append(var)
        
        status = "ok" if len(missing) == 0 else "error"
        
        return {
            "status": status,
            "present": present,
            "missing": missing,
            "message": f"{len(present)} vars present, {len(missing)} missing"
        }
    
    def get_health_status(self) -> Dict[str, any]:
        """
        Get comprehensive health status.
        
        Returns:
            Dict with overall status and component checks
        """
        db_check = self.check_database()
        env_check = self.check_environment_variables()
        
        # Overall status is ok only if all critical checks pass
        overall_status = "ok"
        if db_check["status"] != "ok" or env_check["status"] != "ok":
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "ai-growth-api",
            "checks": {
                "database": db_check,
                "environment": env_check,
            }
        }
    
    def log_config_status(self):
        """
        Log configuration status on startup (NO secrets).
        
        Logs which environment variables are present without
        exposing their values.
        """
        env_check = self.check_environment_variables()
        
        logger.info("Configuration status", extra={
            "required_vars_present": len([v for v in env_check["present"] if v in ["FRONTEGG_CLIENT_ID", "FRONTEGG_CLIENT_SECRET", "DATABASE_URL"]]),
            "required_vars_missing": env_check["missing"],
            "optional_vars_present": len([v for v in env_check["present"] if v not in ["FRONTEGG_CLIENT_ID", "FRONTEGG_CLIENT_SECRET", "DATABASE_URL"]]),
            "database_configured": bool(self.db_url),
            "redis_configured": bool(self.redis_url),
            # CRITICAL: No secret values logged
        })
        
        if env_check["missing"]:
            logger.warning("Missing required environment variables", extra={
                "missing_vars": env_check["missing"]
            })


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker