"""
Cron-based sync scheduler for data ingestion connections.

Scans all enabled tenant connections, resolves plan-based sync SLAs,
and dispatches IngestionJobs for connections that are due. Designed to
run as a Render cron job (e.g., every 15 minutes).

FLOW:
1. Load all active, enabled connections across all tenants
2. For each connection, check plan SLA (Free=daily, Growth=6h, Enterprise=hourly)
3. If connection is due for sync, dispatch IngestionJob via JobDispatcher
4. JobDispatcher enforces one-active-sync-per-connection isolation
5. Entitlements are checked at execution time by the executor

CONSTRAINTS:
- One active sync per connection at a time (enforced by JobDispatcher)
- Plan limits are respected strictly (via SyncPlanResolver)
- No Celery, no Temporal — Postgres job state only

SECURITY:
- tenant_id comes from the database (trusted), not client input
- Structured logging with no secret leakage

Usage:
    python -m src.workers.sync_scheduler

Deployed as a Render cron job in render.yaml.
"""

import os
import sys
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Maximum connections to evaluate per scheduler run (guard against runaway queries)
MAX_CONNECTIONS_PER_RUN = 500


@dataclass
class SchedulerStats:
    """Track scheduler run statistics."""

    connections_evaluated: int = 0
    jobs_dispatched: int = 0
    jobs_skipped_not_due: int = 0
    jobs_skipped_active: int = 0
    jobs_skipped_entitlement: int = 0
    errors: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return {
            "connections_evaluated": self.connections_evaluated,
            "jobs_dispatched": self.jobs_dispatched,
            "jobs_skipped_not_due": self.jobs_skipped_not_due,
            "jobs_skipped_active": self.jobs_skipped_active,
            "jobs_skipped_entitlement": self.jobs_skipped_entitlement,
            "errors": self.errors,
            "duration_seconds": round(duration, 2),
        }


def _get_database_session() -> Session:
    """Create database session for scheduler job."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_factory()


def _get_enabled_connections(db_session: Session, limit: int = MAX_CONNECTIONS_PER_RUN):
    """
    Fetch all enabled, active connections across all tenants.

    Returns:
        List of TenantAirbyteConnection rows eligible for scheduling.
    """
    from src.models.airbyte_connection import (
        TenantAirbyteConnection,
        ConnectionStatus,
    )

    stmt = (
        select(TenantAirbyteConnection)
        .where(
            TenantAirbyteConnection.is_enabled.is_(True),
            TenantAirbyteConnection.status.in_([
                ConnectionStatus.ACTIVE,
                ConnectionStatus.PENDING,
            ]),
        )
        .order_by(TenantAirbyteConnection.last_sync_at.asc().nullsfirst())
        .limit(limit)
    )

    return db_session.execute(stmt).scalars().all()


def _check_entitlement(db_session: Session, tenant_id: str) -> bool:
    """
    Check if tenant is entitled to run sync jobs.

    Returns:
        True if allowed, False otherwise.
    """
    from src.jobs.job_entitlements import JobEntitlementChecker, JobType

    checker = JobEntitlementChecker(db_session)
    result = checker.check_job_entitlement(tenant_id, JobType.SYNC)
    return result.is_allowed


def run_scheduler(db_session: Session) -> SchedulerStats:
    """
    Evaluate all enabled connections and dispatch sync jobs for those due.

    This is the core scheduler logic. For each connection:
    1. Check if sync is due per plan SLA
    2. Check entitlement (plan allows sync jobs)
    3. Dispatch IngestionJob (dispatcher enforces one-active-per-connection)

    Args:
        db_session: Database session

    Returns:
        SchedulerStats with run summary
    """
    from src.services.sync_plan_resolver import SyncPlanResolver
    from src.ingestion.jobs.dispatcher import JobDispatcher, JobIsolationError

    stats = SchedulerStats()
    resolver = SyncPlanResolver(db_session)
    connections = _get_enabled_connections(db_session)

    logger.info(
        "Scheduler run started",
        extra={"connection_count": len(connections)},
    )

    for conn in connections:
        stats.connections_evaluated += 1

        try:
            # 1. Check if sync is due per plan SLA
            if not resolver.is_sync_due(conn.tenant_id, conn.last_sync_at):
                stats.jobs_skipped_not_due += 1
                continue

            # 2. Check entitlement
            if not _check_entitlement(db_session, conn.tenant_id):
                stats.jobs_skipped_entitlement += 1
                logger.info(
                    "scheduler.skipped_entitlement",
                    extra={
                        "tenant_id": conn.tenant_id,
                        "connection_id": conn.id,
                    },
                )
                continue

            # 3. Dispatch job (enforces one-active-per-connection)
            dispatcher = JobDispatcher(db_session, conn.tenant_id)
            dispatcher.dispatch(
                connector_id=conn.id,
                external_account_id=conn.airbyte_connection_id,
                job_metadata={
                    "trigger": "scheduler",
                    "source_type": conn.source_type,
                    "connection_name": conn.connection_name,
                },
            )
            db_session.commit()
            stats.jobs_dispatched += 1

            logger.info(
                "scheduler.job_dispatched",
                extra={
                    "tenant_id": conn.tenant_id,
                    "connection_id": conn.id,
                    "source_type": conn.source_type,
                },
            )

        except JobIsolationError:
            # Active job already exists for this connection — expected
            stats.jobs_skipped_active += 1
            db_session.rollback()

        except Exception:
            stats.errors += 1
            db_session.rollback()
            logger.exception(
                "scheduler.connection_error",
                extra={
                    "tenant_id": conn.tenant_id,
                    "connection_id": conn.id,
                },
            )

    logger.info("Scheduler run completed", extra=stats.to_dict())
    return stats


async def run_scheduler_async() -> dict:
    """
    Async entry point for the scheduler.

    Creates a database session, runs the scheduler, and cleans up.

    Returns:
        Stats dictionary.
    """
    session = _get_database_session()
    try:
        stats = run_scheduler(session)
        return stats.to_dict()
    finally:
        session.close()


def main():
    """Entry point for running scheduler from command line."""
    try:
        result = asyncio.run(run_scheduler_async())
        logger.info("Scheduler finished", extra=result)
        sys.exit(0)
    except Exception as e:
        logger.error("Scheduler failed", extra={"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
