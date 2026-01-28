"""
Job runner for insight generation.

Processes queued InsightJobs by calling InsightGenerationService.
Handles job lifecycle: QUEUED -> RUNNING -> SUCCESS/FAILED/SKIPPED.

SECURITY: All operations are tenant-scoped.

Story 8.1 - AI Insight Generation (Read-Only Analytics)
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.models.insight_job import InsightJob, InsightJobStatus
from src.services.insight_generation_service import InsightGenerationService
from src.services.insight_thresholds import get_thresholds_for_tier
from src.services.billing_entitlements import BillingEntitlementsService


logger = logging.getLogger(__name__)


class InsightJobRunner:
    """
    Executes insight generation jobs.

    Processes jobs in QUEUED status, generates insights using
    InsightGenerationService, and updates job status.
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def _get_tenant_tier(self, tenant_id: str) -> str:
        """Get billing tier for tenant."""
        service = BillingEntitlementsService(self.db, tenant_id)
        return service.get_billing_tier()

    def execute_job(self, job: InsightJob) -> None:
        """
        Execute a single insight generation job.

        Args:
            job: InsightJob to execute
        """
        logger.info(
            "insight_job.started",
            extra={
                "job_id": job.job_id,
                "tenant_id": job.tenant_id,
                "cadence": job.cadence.value if job.cadence else None,
            },
        )

        # Mark as running
        job.mark_running()
        self.db.flush()

        try:
            # Get thresholds based on plan tier
            tier = self._get_tenant_tier(job.tenant_id)
            thresholds = get_thresholds_for_tier(tier)

            # Generate insights
            service = InsightGenerationService(
                db_session=self.db,
                tenant_id=job.tenant_id,
                thresholds=thresholds,
            )

            insights = service.generate_insights(job_id=job.job_id)

            # Mark success
            job.mark_success(
                insights_generated=len(insights),
                metadata={
                    "tier": tier,
                    "period_types_analyzed": ["weekly", "last_30_days"],
                },
            )
            self.db.flush()

            logger.info(
                "insight_job.completed",
                extra={
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "insights_generated": len(insights),
                },
            )

        except Exception as e:
            # Mark failed
            job.mark_failed(str(e))
            self.db.flush()

            logger.error(
                "insight_job.failed",
                extra={
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "error": str(e),
                },
                exc_info=True,
            )

    def process_queued_jobs(self, limit: int = 10) -> int:
        """
        Process batch of queued insight jobs.

        Args:
            limit: Maximum number of jobs to process

        Returns:
            Number of jobs processed
        """
        jobs = (
            self.db.query(InsightJob)
            .filter(InsightJob.status == InsightJobStatus.QUEUED)
            .order_by(InsightJob.created_at.asc())
            .limit(limit)
            .all()
        )

        if not jobs:
            logger.debug("No queued insight jobs to process")
            return 0

        processed = 0
        for job in jobs:
            try:
                self.execute_job(job)
                processed += 1
            except Exception as e:
                logger.error(
                    "Error processing insight job",
                    extra={
                        "job_id": job.job_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        self.db.commit()
        return processed


def run_insight_worker_cycle(db_session: Session, limit: int = 10) -> dict:
    """
    Run one cycle of the insight worker.

    Called by cron trigger or background worker.

    Args:
        db_session: Database session
        limit: Maximum jobs to process per cycle

    Returns:
        Dict with processing results
    """
    runner = InsightJobRunner(db_session)
    processed = runner.process_queued_jobs(limit=limit)

    logger.info(
        "Insight worker cycle completed",
        extra={"processed": processed},
    )

    return {"processed": processed}
