"""Run required SQL migrations before API startup.

This script is intentionally conservative: it executes only a curated ordered set
of SQL migration files needed for authentication/tenant enforcement to function.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS = [
    "001_create_identity_tables.sql",
    "002_add_super_admin.sql",
    "0055_rbac_roles.sql",
    "0056_agency_access.sql",
    "0057_access_revocation.sql",
]


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def run() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migrations_dir = backend_root / "migrations"

    db_url = get_database_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    logger.info("Running required migrations", extra={"count": len(MIGRATIONS)})

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))

    for migration_file in MIGRATIONS:
        path = migrations_dir / migration_file
        if not path.exists():
            raise FileNotFoundError(f"Required migration missing: {path}")

        sql = path.read_text(encoding="utf-8")
        logger.info("Applying migration %s", migration_file)
        try:
            with engine.begin() as conn:
                raw = conn.connection
                with raw.cursor() as cur:
                    cur.execute(sql)
        except SQLAlchemyError as e:
            logger.exception("Failed migration %s", migration_file)
            raise RuntimeError(f"Migration failed: {migration_file}: {e}") from e

    logger.info("Required migrations completed")


if __name__ == "__main__":
    run()
