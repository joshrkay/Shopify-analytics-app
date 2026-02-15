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
    "audit_logs_schema.sql",
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


def _is_identifier_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into executable statements.

    Handles semicolons in:
    - single-quoted strings
    - double-quoted identifiers
    - line/block comments
    - PostgreSQL dollar-quoted blocks (e.g., $$ ... $$, $func$ ... $func$)
    """
    statements: list[str] = []
    buf: list[str] = []

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        if dollar_tag is not None:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
            else:
                buf.append(ch)
                i += 1
            continue

        if in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                else:
                    in_single = False
                    i += 1
            else:
                i += 1
            continue

        if in_double:
            buf.append(ch)
            if ch == '"':
                if nxt == '"':
                    buf.append(nxt)
                    i += 2
                else:
                    in_double = False
                    i += 1
            else:
                i += 1
            continue

        if ch == "-" and nxt == "-":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_line_comment = True
            continue

        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_block_comment = True
            continue

        if ch == "'":
            buf.append(ch)
            in_single = True
            i += 1
            continue

        if ch == '"':
            buf.append(ch)
            in_double = True
            i += 1
            continue

        if ch == "$":
            j = i + 1
            while j < n and _is_identifier_char(sql[j]):
                j += 1
            if j < n and sql[j] == "$":
                tag = sql[i : j + 1]
                buf.append(tag)
                i = j + 1
                dollar_tag = tag
                continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)

    return statements


def run() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migrations_dir = backend_root / "migrations"

    db_url = get_database_url()
    engine = create_engine(db_url, pool_pre_ping=True)

    logger.info("Running required migrations", extra={"count": len(MIGRATIONS)})

    with engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))

    for migration_file in MIGRATIONS:
        path = migrations_dir / migration_file
        if not path.exists():
            raise FileNotFoundError(f"Required migration missing: {path}")

        sql = path.read_text(encoding="utf-8")
        statements = split_sql_statements(sql)
        logger.info("Applying migration %s", migration_file)
        try:
            with engine.begin() as conn:
                raw = conn.connection
                with raw.cursor() as cur:
                    for statement in statements:
                        cur.execute(statement)
        except SQLAlchemyError as e:
            logger.exception("Failed migration %s", migration_file)
            raise RuntimeError(f"Migration failed: {migration_file}: {e}") from e

    logger.info("Required migrations completed")


if __name__ == "__main__":
    run()
