"""Helpers for getting database sessions from request state."""

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from src.database.session import get_db_session_sync


def get_request_db_session(request: Request, *, require_state: bool = False) -> Session:
    """Return a database session from request state or create a new one."""
    db = getattr(request.state, "db", None)
    if db:
        return db

    if require_state:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session not available",
        )

    return next(get_db_session_sync())
