#!/usr/bin/env python3
"""
Import verification script — catches the deploy-failure pattern where a route
module is imported in main.py but either (a) the file doesn't exist on disk or
(b) the file uses names it never imports (NameError at load time).

Both failures crash the entire FastAPI app on startup — no routes serve at all.

Two phases:
  Phase 1 (Static / AST):
    Parses main.py and every file under src/api/routes/ with the Python AST.
    For each `from src.X import Y` statement, verifies the resolved .py file
    exists on disk.  Catches missing-file failures before any process starts.

  Phase 2 (Runtime / subprocess):
    For each route module imported in main.py, spawns a subprocess that tries
    `from src.api.routes import <module>`.  A non-zero exit means the module
    raises NameError, ImportError, or similar at load time — which would crash
    main.py on startup.  The full traceback is printed so the broken import is
    immediately visible.

Usage (from backend/):
    python scripts/check_imports.py

Exit codes:
    0 — all imports verified clean
    1 — one or more failures found
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/


# ---------------------------------------------------------------------------
# Phase 1 helpers
# ---------------------------------------------------------------------------

def _find_local_from_imports(filepath: Path) -> list[tuple[str, str, int]]:
    """
    Return all `from src.* import NAME` statements in a Python file.
    Returns [(module_dotted, name, lineno), ...]
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {filepath.relative_to(ROOT)}: {e}")
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module.startswith("src.") or node.module == "src"
            ):
                for alias in node.names:
                    results.append((node.module, alias.name, node.lineno))
    return results


def _import_to_candidates(module: str, name: str) -> list[Path]:
    """
    Return candidate file paths for `from {module} import {name}`.

    Examples:
      from src.api.routes import health
        → src/api/routes/health.py
        → src/api/routes/health/__init__.py
      from src.api.routes import routes   (module itself, '*' alias)
        → src/api/routes.py
        → src/api/routes/__init__.py
    """
    parts = module.replace(".", "/")
    return [
        # name is a sub-module
        ROOT / f"{parts}/{name}.py",
        ROOT / f"{parts}/{name}/__init__.py",
        # name might refer to the module itself (e.g. `from src.api import dq`)
        ROOT / f"{parts.rsplit('/', 1)[0]}/{name}.py"
        if "/" in parts else ROOT / f"{name}.py",
        # name is a symbol (class/function/var) defined inside the module file
        ROOT / f"{parts}.py",
        ROOT / f"{parts}/__init__.py",
    ]


def phase1_static_check(entry_points: list[Path]) -> list[str]:
    """
    Check every local import in each entry point resolves to a disk file.
    Returns a list of error strings (empty = clean).
    """
    errors: list[str] = []

    for filepath in entry_points:
        if not filepath.exists():
            print(f"  WARNING: {filepath.relative_to(ROOT)} not found, skipping")
            continue

        file_errors: list[str] = []
        for module, name, lineno in _find_local_from_imports(filepath):
            candidates = _import_to_candidates(module, name)
            if not any(c.exists() for c in candidates):
                primary = ROOT / f"{module.replace('.', '/')}/{name}.py"
                file_errors.append(
                    f"  line {lineno:4d}: from {module} import {name}\n"
                    f"           → {primary.relative_to(ROOT)} [NOT FOUND]"
                )

        if file_errors:
            print(f"\n{filepath.relative_to(ROOT)}:")
            for e in file_errors:
                print(e)
            errors.extend(file_errors)

    return errors


# ---------------------------------------------------------------------------
# Phase 2 helpers
# ---------------------------------------------------------------------------

def _build_env() -> dict[str, str]:
    """Minimal environment for importing the app without real credentials."""
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT),
        "DATABASE_URL": "sqlite:///:memory:",
        "CLERK_FRONTEND_API": "test.clerk.accounts.dev",
        "ENV": "test",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def _try_import(stmt: str, env: dict[str, str]) -> str | None:
    """
    Run `python -c "{stmt}"` in a subprocess.
    Returns None on success, or an error string on failure.
    """
    result = subprocess.run(
        [sys.executable, "-c", stmt],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()
        # Find the root cause line (last non-blank line)
        last_err = next(
            (line.strip() for line in reversed(stderr) if line.strip()),
            "unknown error",
        )
        return last_err
    return None


def phase2_runtime_check(import_statements: list[str]) -> list[str]:
    """
    Try each import statement in a subprocess.
    Returns a list of error strings (empty = clean).
    """
    env = _build_env()
    errors: list[str] = []

    for stmt in import_statements:
        err = _try_import(stmt, env)
        if err:
            print(f"  ✗ {stmt}")
            print(f"      → {err}")
            errors.append(f"{stmt}: {err}")
        else:
            print(f"  ✓ {stmt}")

    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    # ── Phase 1: Static ────────────────────────────────────────────────────
    print("=" * 65)
    print("Phase 1 — Static: verify all imported module files exist on disk")
    print("=" * 65)

    entry_points: list[Path] = [ROOT / "main.py"]
    routes_dir = ROOT / "src" / "api" / "routes"
    if routes_dir.exists():
        entry_points.extend(sorted(routes_dir.glob("*.py")))

    static_errors = phase1_static_check(entry_points)

    if not static_errors:
        print(f"✓ Phase 1 passed — all local imports resolve to existing files")
    else:
        print(f"\n✗ Phase 1 FAILED — {len(static_errors)} missing file(s)")

    # ── Phase 2: Runtime ───────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("Phase 2 — Runtime: subprocess-import each route module")
    print("=" * 65)

    # Extract route imports from main.py (they're the ones that could crash startup)
    main_py = ROOT / "main.py"
    route_stmts: list[str] = []
    if main_py.exists():
        seen: set[str] = set()
        for module, name, _ in _find_local_from_imports(main_py):
            stmt = f"from {module} import {name}"
            if stmt not in seen:
                seen.add(stmt)
                route_stmts.append(stmt)

    if not route_stmts:
        print("  (no route imports found in main.py)")
    else:
        print(f"  Checking {len(route_stmts)} import(s) from main.py ...\n")

    runtime_errors = phase2_runtime_check(route_stmts)

    if not runtime_errors:
        print(
            f"\n✓ Phase 2 passed — "
            f"{len(route_stmts)} import(s) load without errors"
        )
    else:
        print(f"\n✗ Phase 2 FAILED — {len(runtime_errors)} runtime import error(s)")

    # ── Summary ────────────────────────────────────────────────────────────
    total = len(static_errors) + len(runtime_errors)
    print()
    print("=" * 65)
    if total == 0:
        print("✓ IMPORT VERIFICATION PASSED")
    else:
        print(f"✗ IMPORT VERIFICATION FAILED ({total} error(s) across both phases)")
        print("  These errors crash the entire app at startup — no routes serve at all.")
        print("  Fix before pushing to main.")
    print("=" * 65)

    return 1 if total > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
