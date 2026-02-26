"""
Async dbt incremental runner.

Runs `dbt run` against all models in the analytics/ project.

Called two ways:
  1. Event-driven: fired as an asyncio background task by sync_executor after a
     batch of Airbyte syncs succeed (raw data just landed — transform it now).
  2. Scheduled:    invoked directly as a Render cron job (hourly fallback) via
                   `python -m src.workers.dbt_runner`.

Concurrency guard: a module-level asyncio.Lock prevents two simultaneous dbt
runs regardless of how many executor cycles trigger it at the same time. If
dbt is already running when the trigger fires, the new request is dropped and
logged — the in-progress run will transform the same data.

Analytics dir: worker.Dockerfile copies analytics/ to /analytics and generates
profiles.yml from profiles.yml.example there. dbt_runner passes --profiles-dir
and --project-dir pointing at that location. Override via DBT_PROJECT_DIR env
var for local development.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Lock that prevents two concurrent dbt runs (module-level so it's shared
# across all callers within a single process lifetime).
_dbt_lock = asyncio.Lock()

# /analytics is where worker.Dockerfile places the dbt project.
# Override with DBT_PROJECT_DIR for local or CI use.
_ANALYTICS_DIR = Path(os.environ.get("DBT_PROJECT_DIR", "/analytics"))


async def run_dbt_incremental() -> bool:
    """
    Execute `dbt run` for all incremental models.

    Returns True on success, False on failure or if a run was already
    in progress and was skipped.
    """
    if _dbt_lock.locked():
        logger.info("dbt_runner.skipped_already_running")
        return False

    async with _dbt_lock:
        logger.info(
            "dbt_runner.starting",
            extra={"project_dir": str(_ANALYTICS_DIR)},
        )

        cmd = [
            "dbt",
            "run",
            "--profiles-dir", str(_ANALYTICS_DIR),
            "--project-dir", str(_ANALYTICS_DIR),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_ANALYTICS_DIR),
                env=os.environ.copy(),
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(
                    "dbt_runner.success",
                    extra={
                        "output_tail": stdout.decode()[-500:] if stdout else "",
                    },
                )
                return True

            logger.error(
                "dbt_runner.failed",
                extra={
                    "returncode": process.returncode,
                    "stderr_tail": stderr.decode()[-500:] if stderr else "",
                },
            )
            return False

        except Exception as exc:
            logger.error(
                "dbt_runner.exception",
                extra={"error": str(exc)},
            )
            return False


def main() -> None:
    """Entry point for the Render dbt-incremental cron job."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    success = asyncio.run(run_dbt_incremental())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
