from fastapi import APIRouter, Depends

from src.database.session import get_db_session
from src.platform.db_readiness import (
    REQUIRED_IDENTITY_TABLES,
    check_required_tables,
)

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/health/readiness")
async def readiness(db=Depends(get_db_session)):
    """Readiness probe that validates required identity tables exist."""
    result = check_required_tables(db, REQUIRED_IDENTITY_TABLES)
    return {
        "status": "ready" if result.ready else "not_ready",
        "checks": {
            "database": "ok",
            "identity_tables": {
                "required": result.checked_tables,
                "missing": result.missing_tables,
            },
        },
    }
