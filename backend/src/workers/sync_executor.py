"""
Sync executor — Render managed worker for processing ingestion jobs.

Runs as a long-lived Render worker process. Loops continuously, picking
up QUEUED IngestionJobs and executing them via the existing JobRunner.
Also processes failed jobs that are due for retry.

This worker delegates all sync execution, retry logic, and DLQ handling
to the existing ingestion infrastructure:
- JobRunner: executes jobs, triggers Airbyte syncs
- RetryPolicy: exponential backoff with jitter
- JobDispatcher: isolation enforcement (one active per connection)
- JobEntitlementChecker: billing-gated execution

CONSTRAINTS:
- One active sync per connection (enforced by JobRunner/JobDispatcher)
- No Celery, no Temporal — driven by Postgres job state
- Graceful shutdown on SIGTERM/SIGINT

Usage:
    python -m src.workers.sync_executor

Deployed as a Render worker service in render.yaml.
"""

import os
import sys
import signal
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configurable via environment variables
POLL_INTERVAL_SECONDS = int(
    os.getenv("WORKER_SYNC_CHECK_INTERVAL_SECONDS", "30")
)
MAX_JOBS_PER_CYCLE = int(
    os.getenv("WORKER_MAX_CONCURRENT_SYNCS", "5")
)


@dataclass
class ExecutorStats:
    """Cumulative statistics for the executor process lifetime."""

    cycles: int = 0
    total_queued_processed: int = 0
    total_retry_processed: int = 0
    total_errors: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        uptime = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return {
            "cycles": self.cycles,
            "total_queued_processed": self.total_queued_processed,
            "total_retry_processed": self.total_retry_processed,
            "total_errors": self.total_errors,
            "uptime_seconds": round(uptime, 2),
        }


def _get_database_session() -> Session:
    """Create database session for executor."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_factory()


def _update_last_sync_timestamps(db_session: Session) -> None:
    """
    Update last_sync_at on connections whose latest job succeeded.

    Scans recently completed SUCCESS jobs and propagates the timestamp
    back to the connection record so the scheduler knows when the
    connection last synced.
    """
    from src.ingestion.jobs.models import IngestionJob, JobStatus
    from src.models.airbyte_connection import TenantAirbyteConnection

    from sqlalchemy import select, update
    from datetime import timedelta

    # Find jobs completed in the last poll interval window
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=POLL_INTERVAL_SECONDS * 2)

    stmt = (
        select(IngestionJob)
        .where(
            IngestionJob.status == JobStatus.SUCCESS,
            IngestionJob.completed_at >= cutoff,
        )
    )
    recent_successes = db_session.execute(stmt).scalars().all()

    for job in recent_successes:
        db_session.execute(
            update(TenantAirbyteConnection)
            .where(
                TenantAirbyteConnection.id == job.connector_id,
                TenantAirbyteConnection.tenant_id == job.tenant_id,
            )
            .values(
                last_sync_at=job.completed_at,
                last_sync_status="success",
            )
        )

    if recent_successes:
        db_session.commit()
        logger.info(
            "executor.timestamps_updated",
            extra={"count": len(recent_successes)},
        )


async def run_cycle(db_session: Session, stats: ExecutorStats) -> None:
    """
    Run one executor cycle: process queued jobs, then retry jobs.

    Delegates to the existing JobRunner from ingestion infrastructure.

    Args:
        db_session: Database session
        stats: Cumulative stats tracker
    """
    from src.ingestion.jobs.runner import JobRunner

    runner = JobRunner(db_session=db_session)

    try:
        queued = await runner.process_queued_jobs(limit=MAX_JOBS_PER_CYCLE)
        stats.total_queued_processed += queued

        retried = await runner.process_retry_jobs(limit=MAX_JOBS_PER_CYCLE)
        stats.total_retry_processed += retried

        # Propagate success timestamps back to connection records
        _update_last_sync_timestamps(db_session)

        stats.cycles += 1

        if queued > 0 or retried > 0:
            logger.info(
                "executor.cycle_completed",
                extra={
                    "cycle": stats.cycles,
                    "queued_processed": queued,
                    "retry_processed": retried,
                },
            )

    except Exception:
        stats.total_errors += 1
        db_session.rollback()
        logger.exception("executor.cycle_error", extra={"cycle": stats.cycles})


async def run_executor() -> None:
    """
    Main executor loop. Runs until SIGTERM/SIGINT.

    Creates a fresh DB session each cycle for connection health.
    Sleeps between cycles to avoid busy-waiting.
    """
    stats = ExecutorStats()
    shutdown_event = asyncio.Event()

    def _handle_signal(sig, _frame):
        logger.info("Received signal %s, shutting down gracefully", sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "Sync executor starting",
        extra={
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            "max_jobs_per_cycle": MAX_JOBS_PER_CYCLE,
        },
    )

    while not shutdown_event.is_set():
        session = _get_database_session()
        try:
            await run_cycle(session, stats)
        finally:
            session.close()

        # Sleep until next cycle or shutdown signal
        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=POLL_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass  # Normal: timeout means no shutdown signal, continue loop

    logger.info("Sync executor stopped", extra=stats.to_dict())


def main():
    """Entry point for running executor from command line."""
    try:
        asyncio.run(run_executor())
        sys.exit(0)
    except Exception as e:
        logger.error("Executor crashed", extra={"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
