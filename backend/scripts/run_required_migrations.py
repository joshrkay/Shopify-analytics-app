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
    "0060_audit_logs.sql",
    "add_insight_dollar_impact.sql",
    "add_tenant_airbyte_workspace.sql",
    "add_configuration_column.sql",
    "create_shopify_stores.sql",
    "billing_schema.sql",
    "connector_credentials.sql",
    "ingestion_jobs.sql",
    "notifications_schema.sql",
    "ai_insights_schema.sql",
    "ai_insights_explainability.sql",
    "ai_recommendations_schema.sql",
    "ai_actions_schema.sql",
    "ai_safety_schema.sql",
    "llm_routing_schema.sql",
    "dq_schema.sql",
    "data_availability.sql",
    "backfill_jobs.sql",
    "historical_backfill_requests.sql",
    "root_cause_signals.sql",
    "oauth_shop_domain_unique_constraint.sql",
    "add_dashboard_metric_bindings.sql",
    "add_report_templates.sql",
    "performance_indexes.sql",
    "raw_schema.sql",
    "ad_budgets_schema.sql",
    "alerts_schema.sql",
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
        # Tracking table: records which migrations have been successfully applied.
        # Once a migration is recorded here it is never re-executed, so the runner
        # can be called on every deploy without re-running completed DDL.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_file  VARCHAR(255) PRIMARY KEY,
                applied_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """))

    for migration_file in MIGRATIONS:
        path = migrations_dir / migration_file
        if not path.exists():
            raise FileNotFoundError(f"Required migration missing: {path}")

        with engine.connect() as conn:
            already_applied = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE migration_file = :f"),
                {"f": migration_file},
            ).fetchone()
        if already_applied:
            logger.info("Skipping already-applied migration %s", migration_file)
            continue

        sql = path.read_text(encoding="utf-8")
        statements = split_sql_statements(sql)
        logger.info("Applying migration %s (%d statements)", migration_file, len(statements))

        has_concurrently = any("CONCURRENTLY" in s.upper() for s in statements)

        # Use raw psycopg2 connection for ALL migrations to avoid any
        # SQLAlchemy text() or connection-management quirks.
        raw_conn = engine.raw_connection()
        try:
            if has_concurrently:
                # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
                raw_conn.autocommit = True
            else:
                raw_conn.autocommit = False

            cur = raw_conn.cursor()
            try:
                for idx, statement in enumerate(statements, 1):
                    logger.info("  [%s] executing statement %d/%d", migration_file, idx, len(statements))
                    cur.execute(statement)
                    # Log row counts for INSERT/UPDATE/DELETE to aid debugging
                    # Strip leading SQL comments to find the actual command
                    stripped = statement.strip()
                    while stripped.startswith("--"):
                        stripped = stripped.split("\n", 1)[-1].strip() if "\n" in stripped else ""
                    first_word = stripped.upper()[:6]
                    if first_word.startswith(("INSERT", "UPDATE", "DELETE")):
                        logger.info("  [%s] statement %d affected %d rows", migration_file, idx, cur.rowcount)

                if not has_concurrently:
                    raw_conn.commit()
                    logger.info("  [%s] transaction committed", migration_file)
            except Exception:
                if not has_concurrently:
                    raw_conn.rollback()
                raise
            finally:
                cur.close()
        except Exception as e:
            logger.exception("Failed migration %s at statement %d", migration_file, idx)
            raise RuntimeError(f"Migration failed: {migration_file}: {e}") from e
        finally:
            raw_conn.close()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (migration_file) VALUES (:f)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"f": migration_file},
            )

    logger.info("Required migrations completed")


if __name__ == "__main__":
    run()
