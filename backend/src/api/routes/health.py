"""
Health check endpoint for the Signals AI Analytics API.

Provides a simple health check endpoint for load balancers,
Kubernetes probes, and monitoring systems.
"""

from typing import Dict

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Dict with status "ok" if the service is running.
    """
    return {"status": "ok"}
