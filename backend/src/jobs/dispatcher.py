"""
Job dispatcher with entitlement gating.

Dispatches background jobs with category-based gating.
Marks jobs as blocked_due_to_billing when blocked.
All actions are audited.
"""

import logging
from typing import Optional, Callable, Any, Dict
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from src.entitlements.policy import BillingState
from src.models.subscription import Subscription
from src.platform.audit import AuditAction, log_system_audit_event
from src.jobs.models import BackgroundJob, JobStatus, JobCategory
from src.jobs.gating import JobGatingChecker, JobGatingResult

logger = logging.getLogger(__name__)


class JobDispatcher:
    """
    Dispatches background jobs with entitlement gating.
    
    Handles:
    - Job gating based on billing state and category
    - Marking jobs as blocked_due_to_billing
    - Audit logging for all actions
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize job dispatcher.
        
        Args:
            db_session: Database session for job tracking
        """
        self.db = db_session
        self.gating_checker = JobGatingChecker(db_session)
    
    async def dispatch_job(
        self,
        tenant_id: str,
        job_type: str,
        category: JobCategory,
        job_function: Callable,
        job_args: tuple = (),
        job_kwargs: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        job_metadata: Optional[Dict[str, Any]] = None,
        audit_db: Optional[AsyncSession] = None,
    ) -> Optional[BackgroundJob]:
        """
        Dispatch a background job with entitlement gating.
        
        Args:
            tenant_id: Tenant ID
            job_type: Type of job (sync, export, ai_action, etc.)
            category: Job category for premium gating
            job_function: Function to execute for the job
            job_args: Positional arguments for job function
            job_kwargs: Keyword arguments for job function
            max_retries: Maximum retry attempts
            job_metadata: Additional job metadata
            audit_db: Optional async audit database session
            
        Returns:
            BackgroundJob instance if created, None if blocked
        """
        # Fetch subscription for gating check
        subscription = self.db.query(Subscription).filter(
            Subscription.tenant_id == tenant_id
        ).order_by(Subscription.created_at.desc()).first()
        
        # Check gating
        gating_result = self.gating_checker.check_job_gating(
            tenant_id=tenant_id,
            category=category,
            subscription=subscription,
        )
        
        # Create job record
        job = BackgroundJob(
            tenant_id=tenant_id,
            job_type=job_type,
            category=category,
            status=JobStatus.PENDING,
            max_retries=max_retries,
            job_metadata=job_metadata or {},
        )
        self.db.add(job)
        self.db.flush()  # Get job ID
        
        # Log warning if past_due
        if gating_result.should_log_warning:
            logger.warning(
                "Job running with billing warning",
                extra={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "job_type": job_type,
                    "billing_state": gating_result.billing_state.value,
                    "reason": gating_result.reason,
                }
            )
        
        # Check if job is allowed
        if not gating_result.is_allowed:
            # Mark as blocked
            job.mark_blocked(gating_result.billing_state.value)
            self.db.commit()
            
            # Audit log
            await self._audit_job_blocked(
                tenant_id=tenant_id,
                job_id=job.id,
                job_type=job_type,
                category=category.value,
                billing_state=gating_result.billing_state,
                reason=gating_result.reason,
                plan_id=gating_result.plan_id,
                audit_db=audit_db,
            )
            
            logger.info(
                "Job blocked due to billing state",
                extra={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "job_type": job_type,
                    "category": category.value,
                    "billing_state": gating_result.billing_state.value,
                    "reason": gating_result.reason,
                }
            )
            
            return job
        
        # Job is allowed - execute
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        
        # Audit log
        await self._audit_job_started(
            tenant_id=tenant_id,
            job_id=job.id,
            job_type=job_type,
            category=category.value,
            billing_state=gating_result.billing_state,
            plan_id=gating_result.plan_id,
            audit_db=audit_db,
        )
        
        try:
            # Execute job function
            if job_kwargs:
                result = await job_function(*job_args, **job_kwargs)
            else:
                result = await job_function(*job_args)
            
            # Mark as completed
            job.mark_completed()
            self.db.commit()
            
            # Audit log
            await self._audit_job_completed(
                tenant_id=tenant_id,
                job_id=job.id,
                job_type=job_type,
                audit_db=audit_db,
            )
            
            logger.info(
                "Job completed successfully",
                extra={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "job_type": job_type,
                }
            )
            
            return job
            
        except Exception as e:
            # Mark as failed
            error_message = str(e)
            job.mark_failed(error_message)
            self.db.commit()
            
            # Audit log
            await self._audit_job_failed(
                tenant_id=tenant_id,
                job_id=job.id,
                job_type=job_type,
                error_message=error_message,
                audit_db=audit_db,
            )
            
            logger.error(
                "Job failed",
                extra={
                    "tenant_id": tenant_id,
                    "job_id": job.id,
                    "job_type": job_type,
                    "error": error_message,
                },
                exc_info=True,
            )
            
            raise
    
    async def _audit_job_blocked(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        category: str,
        billing_state: BillingState,
        reason: str,
        plan_id: Optional[str],
        audit_db: Optional[AsyncSession],
    ) -> None:
        """Audit log job blocked event."""
        try:
            if audit_db:
                await log_system_audit_event(
                    db=audit_db,
                    tenant_id=tenant_id,
                    action=AuditAction.JOB_SKIPPED_DUE_TO_ENTITLEMENT,
                    resource_type="job",
                    resource_id=job_id,
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "category": category,
                        "billing_state": billing_state.value,
                        "reason": reason,
                        "plan_id": plan_id,
                        "status": "blocked_due_to_billing",
                    },
                )
            else:
                logger.warning(
                    "Job blocked due to billing",
                    extra={
                        "tenant_id": tenant_id,
                        "job_id": job_id,
                        "action": "job.blocked_due_to_billing",
                        "job_type": job_type,
                        "category": category,
                        "billing_state": billing_state.value,
                        "reason": reason,
                    }
                )
        except Exception as e:
            logger.error(
                "Failed to audit job blocked event",
                extra={"error": str(e), "job_id": job_id}
            )
    
    async def _audit_job_started(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        category: str,
        billing_state: BillingState,
        plan_id: Optional[str],
        audit_db: Optional[AsyncSession],
    ) -> None:
        """Audit log job started event."""
        try:
            if audit_db:
                await log_system_audit_event(
                    db=audit_db,
                    tenant_id=tenant_id,
                    action=AuditAction.JOB_ALLOWED,
                    resource_type="job",
                    resource_id=job_id,
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "category": category,
                        "billing_state": billing_state.value,
                        "plan_id": plan_id,
                        "status": "running",
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to audit job started event",
                extra={"error": str(e), "job_id": job_id}
            )
    
    async def _audit_job_completed(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        audit_db: Optional[AsyncSession],
    ) -> None:
        """Audit log job completed event."""
        try:
            if audit_db:
                await log_system_audit_event(
                    db=audit_db,
                    tenant_id=tenant_id,
                    action=AuditAction.BACKFILL_COMPLETED,  # Reusing existing action
                    resource_type="job",
                    resource_id=job_id,
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "status": "completed",
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to audit job completed event",
                extra={"error": str(e), "job_id": job_id}
            )
    
    async def _audit_job_failed(
        self,
        tenant_id: str,
        job_id: str,
        job_type: str,
        error_message: str,
        audit_db: Optional[AsyncSession],
    ) -> None:
        """Audit log job failed event."""
        try:
            if audit_db:
                await log_system_audit_event(
                    db=audit_db,
                    tenant_id=tenant_id,
                    action=AuditAction.BACKFILL_FAILED,  # Reusing existing action
                    resource_type="job",
                    resource_id=job_id,
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "status": "failed",
                        "error": error_message,
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to audit job failed event",
                extra={"error": str(e), "job_id": job_id}
            )
