"""
Job runner for action execution.

Processes queued ActionJobs by executing approved actions.
Handles job lifecycle: QUEUED -> RUNNING -> SUCCEEDED/FAILED/PARTIALLY_SUCCEEDED.

SECURITY: All operations are tenant-scoped.

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from src.models.ai_action import AIAction, ActionStatus
from src.models.action_job import ActionJob, ActionJobStatus
from src.services.action_execution_service import (
    ActionExecutionService,
    ActionExecutionResult,
)
from src.services.platform_credentials_service import PlatformCredentialsService
from src.services.platform_executors import RetryConfig


logger = logging.getLogger(__name__)


@dataclass
class JobRunResult:
    """Result of running an action job."""
    job_id: str
    status: ActionJobStatus
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    error_summary: Optional[dict] = None


class ActionJobRunner:
    """
    Executes action execution jobs.

    Processes jobs in QUEUED status, executes approved actions
    using ActionExecutionService, and updates job status.

    Jobs can have multiple actions. The job tracks:
    - SUCCEEDED: All actions succeeded
    - FAILED: All actions failed (or error before execution)
    - PARTIALLY_SUCCEEDED: Some actions succeeded, some failed
    """

    def __init__(
        self,
        db_session: Session,
        credentials_service: Optional[PlatformCredentialsService] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize job runner.

        Args:
            db_session: Database session
            credentials_service: Optional credentials service (shared across tenants)
            retry_config: Optional retry configuration for executors
        """
        self.db = db_session
        self._credentials_service = credentials_service
        self.retry_config = retry_config or RetryConfig()

    @property
    def credentials_service(self) -> PlatformCredentialsService:
        """Get or create credentials service."""
        if self._credentials_service is None:
            self._credentials_service = PlatformCredentialsService(self.db)
        return self._credentials_service

    # =========================================================================
    # Job Execution
    # =========================================================================

    async def execute_job(self, job: ActionJob) -> JobRunResult:
        """
        Execute a single action execution job.

        Args:
            job: ActionJob to execute

        Returns:
            JobRunResult with outcome details
        """
        logger.info(
            "action_job.started",
            extra={
                "job_id": job.job_id,
                "tenant_id": job.tenant_id,
                "action_count": len(job.action_ids or []),
            },
        )

        # Mark as running
        job.mark_running()
        self.db.flush()

        try:
            # Get actions to execute
            action_ids = job.action_ids or []

            if not action_ids:
                # No actions to execute - mark as failed
                job.mark_failed(
                    error_summary={"error": "No action IDs in job"},
                    metadata={"reason": "empty_job"},
                )
                self.db.flush()

                return JobRunResult(
                    job_id=job.job_id,
                    status=job.status,
                    actions_attempted=0,
                    actions_succeeded=0,
                    actions_failed=0,
                    error_summary={"error": "No action IDs in job"},
                )

            # Create execution service for this tenant
            execution_service = ActionExecutionService(
                db_session=self.db,
                tenant_id=job.tenant_id,
                credentials_service=self.credentials_service,
                retry_config=self.retry_config,
            )

            # Execute actions sequentially
            results = await execution_service.execute_batch(action_ids)

            # Collect results
            succeeded = 0
            failed = 0
            error_summary = {}

            for result in results:
                if result.success:
                    succeeded += 1
                else:
                    failed += 1
                    error_summary[result.action_id] = {
                        "message": result.message,
                        "code": result.error_code,
                    }

            # Finalize job based on results
            job.finalize(
                actions_succeeded=succeeded,
                actions_failed=failed,
                error_summary=error_summary if error_summary else None,
                metadata={
                    "action_ids": action_ids,
                },
            )
            self.db.flush()

            logger.info(
                "action_job.completed",
                extra={
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "status": job.status.value,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            )

            return JobRunResult(
                job_id=job.job_id,
                status=job.status,
                actions_attempted=len(action_ids),
                actions_succeeded=succeeded,
                actions_failed=failed,
                error_summary=error_summary if error_summary else None,
            )

        except Exception as e:
            # Mark job as failed
            job.mark_failed(
                error_summary={"error": str(e)},
                metadata={"exception_type": type(e).__name__},
            )
            self.db.flush()

            logger.error(
                "action_job.failed",
                extra={
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            return JobRunResult(
                job_id=job.job_id,
                status=job.status,
                actions_attempted=0,
                actions_succeeded=0,
                actions_failed=0,
                error_summary={"error": str(e)},
            )

    # =========================================================================
    # Batch Processing
    # =========================================================================

    def process_queued_jobs(self, limit: int = 10) -> int:
        """
        Process batch of queued action jobs.

        Jobs are processed sequentially. Each job may contain
        multiple actions which are also executed sequentially.

        Args:
            limit: Maximum number of jobs to process

        Returns:
            Number of jobs processed
        """
        jobs = (
            self.db.query(ActionJob)
            .filter(ActionJob.status == ActionJobStatus.QUEUED)
            .order_by(ActionJob.created_at.asc())
            .limit(limit)
            .all()
        )

        if not jobs:
            logger.debug("No queued action jobs to process")
            return 0

        processed = 0
        for job in jobs:
            try:
                # Run async in sync context
                asyncio.run(self.execute_job(job))
                processed += 1
            except Exception as e:
                logger.error(
                    "Error processing action job",
                    extra={
                        "job_id": job.job_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        self.db.commit()
        return processed

    async def process_queued_jobs_async(self, limit: int = 10) -> int:
        """
        Async version of process_queued_jobs.

        Args:
            limit: Maximum number of jobs to process

        Returns:
            Number of jobs processed
        """
        jobs = (
            self.db.query(ActionJob)
            .filter(ActionJob.status == ActionJobStatus.QUEUED)
            .order_by(ActionJob.created_at.asc())
            .limit(limit)
            .all()
        )

        if not jobs:
            logger.debug("No queued action jobs to process")
            return 0

        processed = 0
        for job in jobs:
            try:
                await self.execute_job(job)
                processed += 1
            except Exception as e:
                logger.error(
                    "Error processing action job",
                    extra={
                        "job_id": job.job_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        self.db.commit()
        return processed

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_job(self, job_id: str) -> Optional[ActionJob]:
        """Get job by ID."""
        return (
            self.db.query(ActionJob)
            .filter(ActionJob.job_id == job_id)
            .first()
        )

    def get_active_jobs(self) -> list[ActionJob]:
        """Get all active (queued or running) jobs."""
        return (
            self.db.query(ActionJob)
            .filter(
                ActionJob.status.in_([
                    ActionJobStatus.QUEUED,
                    ActionJobStatus.RUNNING,
                ])
            )
            .order_by(ActionJob.created_at.asc())
            .all()
        )

    def get_recent_jobs(self, tenant_id: str, limit: int = 20) -> list[ActionJob]:
        """Get recent jobs for a tenant."""
        return (
            self.db.query(ActionJob)
            .filter(ActionJob.tenant_id == tenant_id)
            .order_by(ActionJob.created_at.desc())
            .limit(limit)
            .all()
        )
