from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.platform.health import get_health_checker

router = APIRouter()


@router.get("/health")
def health():
    """
    Health check endpoint for Render monitoring.
    
    Returns:
        - 200 OK: Service is healthy
        - 503 Service Unavailable: Service is degraded (DB/Env issues)
    
    This endpoint is used by Render to determine service health.
    """
    health_checker = get_health_checker()
    health_status = health_checker.get_health_status()
    
    # Return 200 if healthy, 503 if degraded
    http_status = status.HTTP_200_OK if health_status["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=http_status,
        content=health_status
    )