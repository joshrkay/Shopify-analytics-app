"""Database schema readiness checks for critical runtime tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Tables required for auth/tenant middleware and request authorization.
REQUIRED_IDENTITY_TABLES = (
    "users",
    "tenants",
    "user_tenant_roles",
)


@dataclass(frozen=True)
class DBReadinessResult:
    """Result payload for DB schema readiness checks."""

    ready: bool
    missing_tables: list[str]
    checked_tables: list[str]


def check_required_tables(session: Session, required_tables: Iterable[str]) -> DBReadinessResult:
    """Check whether required tables exist in the current database schema."""
    checked = list(required_tables)
    missing: list[str] = []

    for table_name in checked:
        try:
            row = session.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": f"public.{table_name}"},
            ).scalar()
        except SQLAlchemyError:
            logger.exception("Failed checking table existence", extra={"table": table_name})
            raise

        if row is None:
            missing.append(table_name)

    return DBReadinessResult(
        ready=len(missing) == 0,
        missing_tables=missing,
        checked_tables=checked,
    )
