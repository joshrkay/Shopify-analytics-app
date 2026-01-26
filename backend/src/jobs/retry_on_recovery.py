"""
Auto-retry blocked jobs when billing state recovers.

When billing returns to active, automatically retry jobs that were blocked_due_to_billing.
Caps retry count (configurable).
All actions are audited.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from src.entitlements.policy import EntitlementPolicy, BillingState
from src.models.subscription import Subscription
from src.platform.audit import AuditAction, log_system_audit_event
from src.jobs.models import BackgroundJob, JobStatus, JobCategory

logger = logging.getLogger(__name__)

# Default max retries for auto-retry
DEFAULT_MAX_AUTO_RETRIES = 3


class JobRetryOnRecovery:
    """
    Handles auto-retry of blocked jobs when billing state recovers.
    
    When billing returns to active:
    - Finds all jobs with status=blocked_due_to_billing
    - Checks if billing state is now active
    - Retries jobs (respecting retry count cap)
    - All actions are audited
    """
    
    def __init__(self, db_session: Session, max_auto_retries: int = DEFAULT_MAX_AUTO_RETRIES):
        """
        Initialize job retry on recovery handler.
        
        Args:
            db_session: Database session for job tracking
            max_auto_retries: Maximum auto-retry attempts (configurable)
        """
        self.db = db_session
        self.policy = EntitlementPolicy(db_session)
        self.max_auto_retries = max_auto_retries
    
    async def check_and_retry_blocked_jobs(
        self,
        tenant_id: str,
        audit_db: Optional[AsyncSession] = None,
    ) -> List[BackgroundJob]:
        """
        Check if billing state recovered and retry blocked jobs.
        
        Args:
            tenant_id: Tenant ID to check
            audit_db: Optional async audit database session
            
        Returns:
            List of jobs that were retried
        """
        # Fetch subscription
        subscription = self.db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id
        ).order_by(Subscription.created_at.desc()).first()
        
        # Get current billing state
        billing_state = self.policy.get_billing_state(subscription)
        
        # Only retry if billing state is now active
        if billing_state != BillingState.ACTIVE:
            logger.debug(
                "Billing state not active - skipping retry",
                extra={
                    "tenant_id": tenant_id,
                    "billing_state": billing_state.value,
                }
            )
            return []
        
        # Find blocked jobs for this tenant
        blocked_jobs = self.db.query(BackgroundJob).filter(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.status == JobStatus.BLOCKED_DUE_TO_BILLING,
        ).all()
        
        if not blocked_jobs:
            return []
        
        logger.info(
            "Found blocked jobs to retry",
            extra={
                "tenant_id": tenant_id,
                "count": len(blocked_jobs),
            }
        )
        
        retried_jobs = []
        
        for job in blocked_jobs:
            # Check retry count cap
            if job.retry_count >= self.max_auto_retries:
                logger.warning(
                    "Job retry count exceeded - not retrying",
                    extra={
                        "tenant_id": tenant_id,
                        "job_id": job.id,
                        "job_type": job.job_type,
                        "retry_count": job.retry_count,
                        "max_retries": self.max_auto_retries,
                    }
                )
                continue
            
            # Mark as retrying
            job.mark_retrying()
            self.db.commit()
            
            # Audit log
            await self._audit_job_retry(
                tenant_id=tenant_id,
                job_id=job.id,
                job_type=job.job_type,
                retry_count=job.retry_count,
                audit_db=audit_db,
            )
            
            logger.info(
                "Job marked for retry after billing recovery",
                extra={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "retry_count": job.retry_count,
                }
            )
            
            retried_jobs.append(job)
        
        return retried_jobs
    
    async def retry_all_recovered_tenants(
        self,
        audit_db: Optional[AsyncSession] = None,
    ) -> dict:
        """
        Check all tenants with blocked jobs and retry if billing recovered.
        
        Args:
            audit_db: Optional async audit database session
            
        Returns:
            Dictionary with tenant_id -> list of retried jobs
        """
        # Find all unique tenants with blocked jobs
        blocked_tenants = self.db.query(BackgroundJob.tenant_id).filter(
            BackgroundJob.status == JobStatus.BLOCKED_DUE_TO_BILLING,
        ).distinct().all()
        
        tenant_ids = [tenant_id for (tenant_id,) in blocked_tenants]
        
        logger.info(
            "Checking tenants for billing recovery",
            extra={
                "tenant_count": len(tenant_ids),
            }
        )
        
        results = {}
        
        for tenant_id in tenant_ids:
            retried_jobs = await self.check_and_retry_blocked_jobs(
                tenant_id=tenant_id,
                audit_db=audit_db,
            )
            if retried_jobs:
                results[tenant_id] = retried_jobs
        
        return results
    
    async def _audit_job_retry(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        retry_count: int,
        audit_db: Optional[AsyncSession],
    ) -> None:
        """Audit log job retry event."""
        try:
            if audit_db:
                await log_system_audit_event(
                    db=audit_db,
                    tenant_id=tenant_id,
                    action=AuditAction.BACKFILL_STARTED,  # Reusing existing action
                    resource_type="job",
                    resource_id=job_id,
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "status": "retrying",
                        "retry_count": retry_count,
                        "reason": "billing_recovered",
                    },
                )
            else:
                logger.info(
                    "Job retry after billing recovery",
                    extra={
                        "tenant_id": tenant_id,
                        "job_id": job_id,
                        "action": "job.retry_on_recovery",
                        "job_type": job_type,
                        "retry_count": retry_count,
                    }
                )
        except Exception as e:
            logger.error(
                "Failed to audit job retry event",
                extra={"error": str(e), "job_id": job_id}
            )


async def retry_blocked_jobs_on_recovery(
    db_session: Session,
    tenant_id: Optional[str] = None,
    max_auto_retries: int = DEFAULT_MAX_AUTO_RETRIES,
    audit_db: Optional[AsyncSession] = None,
) -> dict:
    """
    Convenience function to retry blocked jobs when billing recovers.
    
    Args:
        db_session: Database session
        tenant_id: Optional tenant ID (if None, checks all tenants)
        max_auto_retries: Maximum auto-retry attempts
        audit_db: Optional async audit database session
        
    Returns:
        Dictionary with tenant_id -> list of retried jobs
    """
    retry_handler = JobRetryOnRecovery(
        db_session=db_session,
        max_auto_retries=max_auto_retries,
    )
    
    if tenant_id:
        retried_jobs = await retry_handler.check_and_retry_blocked_jobs(
            tenant_id=tenant_id,
            audit_db=audit_db,
        )
        return {tenant_id: retried_jobs} if retried_jobs else {}
    else:
        return await retry_handler.retry_all_recovered_tenants(audit_db=audit_db)
