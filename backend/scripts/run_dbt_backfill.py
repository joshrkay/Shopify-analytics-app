"""
dbt Backfill Execution Script

Executes dbt backfills with date-range and tenant filtering, with audit logging.

Usage:
    python -m scripts.run_dbt_backfill \
        --start-date 2024-01-01 \
        --end-date 2024-01-31 \
        --tenant-id tenant-123 \
        --models staging+ facts+

Environment variables:
    DATABASE_URL: PostgreSQL connection string
    DB_HOST, DB_USER, DB_PASSWORD, DB_PORT, DB_NAME: dbt connection parameters
"""

import os
import sys
import subprocess
import argparse
import logging
import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db_base import Base
from src.models.backfill_execution import BackfillExecution, BackfillStatus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get database URL from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:password@localhost:5432/dbname"
        )

    # Handle Render's postgres:// URL format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def get_dbt_project_dir() -> Path:
    """Get dbt project directory (analytics/)."""
    project_root = Path(__file__).parent.parent.parent
    dbt_dir = project_root / "analytics"
    if not dbt_dir.exists():
        raise ValueError(f"dbt project directory not found: {dbt_dir}")
    return dbt_dir


def build_dbt_vars(
    start_date: str,
    end_date: str,
    tenant_id: Optional[str] = None
) -> dict:
    """Build dbt variables dictionary."""
    vars_dict = {
        "backfill_start_date": start_date,
        "backfill_end_date": end_date,
    }
    if tenant_id:
        vars_dict["tenant_id"] = tenant_id
    return vars_dict


def run_dbt_command(
    dbt_dir: Path,
    command: str,
    vars_dict: dict,
    models: Optional[List[str]] = None
) -> tuple[int, str, str]:
    """
    Execute dbt command with variables.
    
    Returns:
        (exit_code, stdout, stderr)
    """
    cmd = ["dbt", command]
    
    # Add model selection if provided
    if models:
        cmd.extend(["--select"] + models)
    
    # Add variables
    vars_json = json.dumps(vars_dict)
    cmd.extend(["--vars", vars_json])
    
    # Set working directory
    env = os.environ.copy()
    
    logger.info(f"Executing: {' '.join(cmd)}")
    logger.info(f"Working directory: {dbt_dir}")
    logger.info(f"Variables: {vars_dict}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(dbt_dir),
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
        
        if result.stdout:
            logger.info(f"dbt stdout:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"dbt stderr:\n{result.stderr}")
        
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        logger.error(f"Failed to execute dbt command: {e}")
        raise


def parse_dbt_run_output(stdout: str) -> Optional[int]:
    """
    Parse dbt run output to extract the total number of records processed.
    It sums up the numbers from lines containing patterns like '[SELECT 100]'.
    """
    try:
        # Find all occurrences of the pattern '[SELECT <number>]' in dbt's output
        matches = re.findall(r'\[SELECT (\d+)\]', stdout)
        if not matches:
            return None
        
        return sum(int(match) for match in matches)
    except Exception:
        # In case of unexpected format, return None
        logger.warning("Could not parse dbt run output for record count.")
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Execute dbt backfill with audit logging"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date for backfill (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date for backfill (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Tenant ID for tenant-scoped backfill (optional)"
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=None,
        help="Specific models to backfill (e.g., staging+ facts+)"
    )
    parser.add_argument(
        "--database-url",
        type=str,
        help="Database URL (overrides DATABASE_URL env var)"
    )

    args = parser.parse_args()

    # Validate date format
    try:
        start_dt = datetime.fromisoformat(args.start_date)
        end_dt = datetime.fromisoformat(args.end_date)
        if start_dt > end_dt:
            raise ValueError("start_date must be <= end_date")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        sys.exit(1)

    database_url = args.database_url or get_database_url()
    dbt_dir = get_dbt_project_dir()

    # Create database session
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # Create backfill execution record
    backfill_exec = BackfillExecution(
        tenant_id=args.tenant_id,  # Can be None for global backfills
        start_date=start_dt,
        end_date=end_dt,
        models_run=args.models if args.models else None,
        status=BackfillStatus.RUNNING,
    )
    session.add(backfill_exec)
    session.commit()
    execution_id = backfill_exec.id

    logger.info(f"Created backfill execution record: {execution_id}")
    logger.info(f"Date range: {args.start_date} to {args.end_date}")
    if args.tenant_id:
        logger.info(f"Tenant ID: {args.tenant_id}")
    if args.models:
        logger.info(f"Models: {', '.join(args.models)}")

    start_time = time.time()
    exit_code = 0
    error_message = None
    records_processed = None

    try:
        # Build dbt variables
        vars_dict = build_dbt_vars(
            args.start_date,
            args.end_date,
            args.tenant_id
        )

        # Run dbt compile first (validate SQL)
        logger.info("Compiling dbt models...")
        compile_code, compile_stdout, compile_stderr = run_dbt_command(
            dbt_dir,
            "compile",
            vars_dict,
            args.models
        )

        if compile_code != 0:
            raise RuntimeError(f"dbt compile failed: {compile_stderr}")

        # Run dbt run
        logger.info("Running dbt models...")
        run_code, run_stdout, run_stderr = run_dbt_command(
            dbt_dir,
            "run",
            vars_dict,
            args.models
        )

        if run_code != 0:
            raise RuntimeError(f"dbt run failed: {run_stderr}")

        # Try to extract records processed
        records_processed = parse_dbt_run_output(run_stdout)

        logger.info("Backfill completed successfully")

    except Exception as e:
        exit_code = 1
        error_message = str(e)
        logger.error(f"Backfill failed: {error_message}")
        session.rollback()

    finally:
        # Update backfill execution record
        duration = time.time() - start_time

        backfill_exec = session.query(BackfillExecution).filter_by(id=execution_id).first()
        if backfill_exec:
            backfill_exec.status = BackfillStatus.COMPLETED if exit_code == 0 else BackfillStatus.FAILED
            backfill_exec.duration_seconds = duration
            backfill_exec.records_processed = records_processed
            backfill_exec.error_message = error_message
            session.commit()

        session.close()

    if exit_code != 0:
        sys.exit(exit_code)

    logger.info(f"Backfill execution complete. Duration: {duration:.2f}s")


if __name__ == "__main__":
    main()
