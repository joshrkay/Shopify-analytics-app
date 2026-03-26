#!/usr/bin/env python3
"""
Migration safety check — scans SQL migration files for unsafe references to
dbt-managed tables.

dbt manages these schemas:
    canonical, analytics, attribution, marts, semantic

Migrations MUST NOT reference these tables without guards because:
  - dbt tables are absent on a fresh deploy (dbt hasn't run yet)
  - dbt drops and recreates tables on every `dbt run`
  - Creating indexes or running DML on dbt tables from a migration will raise
    "relation does not exist" — failing the deploy

SAFE pattern (guarded with information_schema check):
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'analytics' AND table_name = 'orders'
      ) THEN
        CREATE INDEX IF NOT EXISTS ... ON analytics.orders (...);
      END IF;
    END $$;

UNSAFE pattern (no guard — flagged as ERROR):
    CREATE INDEX ix_orders_tenant ON analytics.orders (tenant_id);
    -- ^ will fail on fresh deploy where dbt tables don't exist yet

Known existing issue:
    backend/migrations/performance_indexes.sql references analytics.* tables
    without guards.  These indexes are created on dbt-managed tables and should
    be wrapped in DO $$ IF EXISTS ... END $$ blocks before the next fresh deploy.

Usage (from backend/):
    python scripts/check_migration_safety.py             # strict mode (exit 1 on errors)
    python scripts/check_migration_safety.py --warn-only # report only, exit 0

Exit codes:
    0 — clean (or --warn-only)
    1 — unguarded references found (strict mode only)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent  # backend/
MIGRATIONS_DIR = ROOT / "migrations"

# dbt-managed schemas that migrations should not reference directly
DBT_SCHEMAS: frozenset[str] = frozenset(
    {"canonical", "analytics", "attribution", "marts", "semantic"}
)

# Regex: finds `schema.table` references after risky SQL keywords
# Matches: FROM schema.tbl, JOIN schema.tbl, ON schema.tbl, TABLE schema.tbl,
#          INTO schema.tbl, UPDATE schema.tbl
_SCHEMA_TABLE_RE = re.compile(
    r"""
    (?:FROM | JOIN | \bON\b | TABLE | INTO | UPDATE)
    \s+
    (?P<schema>[a-zA-Z_][a-zA-Z0-9_]*)
    \s* \. \s*
    (?P<table>[a-zA-Z_][a-zA-Z0-9_]*)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Also catch `CREATE INDEX ... ON schema.table`
_CREATE_INDEX_RE = re.compile(
    r"""
    CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?
    \S+                        # index name
    \s+ON\s+
    (?P<schema>[a-zA-Z_][a-zA-Z0-9_]*)
    \s* \. \s*
    (?P<table>[a-zA-Z_][a-zA-Z0-9_]*)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Guard markers — presence of any of these in the file indicates at least
# one guard is present (whole-file check; not per-statement).
_GUARD_RE = re.compile(
    r"information_schema\s*\.\s*tables|DO\s+\$\$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_comments(sql: str) -> str:
    """Strip SQL line comments (--) and block comments (/* */).
    Preserves line structure so line numbers remain accurate.
    """
    # Block comments — replace with spaces of same length to preserve positions
    sql = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), sql, flags=re.DOTALL)
    # Line comments — strip to end of line
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def _find_dbt_references(sql_text: str) -> list[tuple[int, str, str]]:
    """
    Scan SQL for references to dbt-managed schema tables.
    Returns [(line_number, schema, table), ...]
    """
    clean = _strip_comments(sql_text)
    refs: list[tuple[int, str, str]] = []

    for lineno, line in enumerate(clean.splitlines(), start=1):
        for pattern in (_SCHEMA_TABLE_RE, _CREATE_INDEX_RE):
            for match in pattern.finditer(line):
                schema = match.group("schema").lower()
                table = match.group("table").lower()
                if schema in DBT_SCHEMAS:
                    refs.append((lineno, schema, table))

    # Deduplicate while preserving order
    seen: set[tuple[int, str, str]] = set()
    unique: list[tuple[int, str, str]] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique.append(ref)

    return unique


def _has_guard(sql_text: str) -> bool:
    """Return True if the file contains an information_schema guard or DO $$ block."""
    return bool(_GUARD_RE.search(sql_text))


def check_file(filepath: Path) -> dict | None:
    """
    Check a single .sql file.
    Returns a result dict or None if no dbt references found.
    """
    sql = filepath.read_text(encoding="utf-8")
    refs = _find_dbt_references(sql)
    if not refs:
        return None

    return {
        "path": filepath,
        "refs": refs,
        "guarded": _has_guard(sql),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(warn_only: bool = False) -> int:
    if not MIGRATIONS_DIR.exists():
        print(f"ERROR: migrations directory not found: {MIGRATIONS_DIR}")
        return 1

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print("No .sql migration files found.")
        return 0

    print(
        f"Scanning {len(sql_files)} migration file(s) for unsafe dbt table references\n"
        f"dbt-managed schemas: {', '.join(sorted(DBT_SCHEMAS))}\n"
    )

    results = [r for f in sql_files if (r := check_file(f)) is not None]

    if not results:
        print("✓ No migration files reference dbt-managed tables.")
        return 0

    errors: list[str] = []
    warnings: list[str] = []

    for result in results:
        rel = result["path"].relative_to(ROOT)
        guarded = result["guarded"]

        if guarded:
            severity = "WARNING"
            warnings.append(str(rel))
        else:
            severity = "ERROR"
            errors.append(str(rel))

        print(f"{severity}: {rel}")
        for lineno, schema, table in result["refs"]:
            status = "[guarded — verify coverage]" if guarded else "[UNGUARDED]"
            print(f"  line {lineno:4d}: {schema}.{table}  {status}")

        if guarded:
            print(
                "  Recommendation: file has information_schema guard(s) — ensure they\n"
                "  cover ALL dbt table references above, not just some of them.\n"
            )
        else:
            print(
                "  Fix required: wrap each dbt table reference in a guard:\n"
                "\n"
                "    DO $$ BEGIN\n"
                "      IF EXISTS (\n"
                "        SELECT 1 FROM information_schema.tables\n"
                "        WHERE table_schema = '<schema>' AND table_name = '<table>'\n"
                "      ) THEN\n"
                "        -- your SQL here\n"
                "      END IF;\n"
                "    END $$;\n"
            )

    print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)\n")

    if errors:
        print("Files with unguarded dbt references (ERRORS):")
        for e in errors:
            print(f"  {e}")
        print()

    if warnings:
        print("Files with guarded dbt references (WARNINGS — verify guard coverage):")
        for w in warnings:
            print(f"  {w}")
        print()

    if errors:
        if warn_only:
            print(
                "WARN: unguarded dbt table references found (--warn-only, not failing)\n"
                "      These WILL cause migration failures on fresh deploys.\n"
                "      Add information_schema guards before the next fresh-deploy."
            )
            return 0
        else:
            print(
                "✗ MIGRATION SAFETY CHECK FAILED\n"
                "  Unguarded references to dbt tables will cause migration failures\n"
                "  on any deploy where `dbt run` has not yet been executed (e.g.,\n"
                "  fresh database, disaster recovery, CI environment).\n"
                "  Wrap all dbt table references in information_schema EXISTS guards\n"
                "  or run with --warn-only to report without failing."
            )
            return 1

    print("✓ MIGRATION SAFETY CHECK PASSED (warnings above are informational)")
    return 0


if __name__ == "__main__":
    warn_only = "--warn-only" in sys.argv
    sys.exit(main(warn_only=warn_only))
