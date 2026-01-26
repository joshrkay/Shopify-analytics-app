"""
Background job entitlement gating.

Stricter than API gating - blocks premium jobs in grace_period, canceled, expired.
Logs warnings for past_due but allows execution.
"""

import logging
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.entitlements.policy import EntitlementPolicy, BillingState
from src.entitlements.categories import PremiumCategory
from src.models.subscription import Subscription
from src.jobs.models import JobCategory

logger = logging.getLogger(__name__)


@dataclass
class JobGatingResult:
    """Result of a job gating check."""
    is_allowed: bool
    billing_state: BillingState
    plan_id: Optional[str]
    reason: Optional[str] = None
    should_log_warning: bool = False


class JobGatingChecker:
    """
    Checks if a background job should be allowed to run.
    
    BACKGROUND JOB RULES (STRICTER THAN API):
    - active: run
    - past_due: run BUT log warning
    - grace_period: block premium jobs (exports|ai|heavy_recompute)
    - canceled: block premium jobs
    - expired: block premium jobs
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize job gating checker.
        
        Args:
            db_session: Database session for querying subscriptions
        """
        self.db = db_session
        self.policy = EntitlementPolicy(db_session)
    
    def check_job_gating(
        self,
        tenant_id: str,
        category: JobCategory,
        subscription: Optional[Subscription] = None,
    ) -> JobGatingResult:
        """
        Check if a job should be allowed to run based on billing state and category.
        
        Args:
            tenant_id: Tenant ID
            category: Job category (exports, ai, heavy_recompute, other)
            subscription: Optional subscription (will be fetched if not provided)
            
        Returns:
            JobGatingResult with gating decision
        """
        # Fetch subscription if not provided
        if subscription is None:
            subscription = self.db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id
            ).order_by(Subscription.created_at.desc()).first()
        
        # Get billing state
        billing_state = self.policy.get_billing_state(subscription)
        plan_id = subscription.plan_id if subscription else None
        
        # Map JobCategory to PremiumCategory for policy check
        premium_category_map = {
            JobCategory.EXPORTS: PremiumCategory.EXPORTS,
            JobCategory.AI: PremiumCategory.AI,
            JobCategory.HEAVY_RECOMPUTE: PremiumCategory.HEAVY_RECOMPUTE,
            JobCategory.OTHER: PremiumCategory.OTHER,
        }
        premium_category = premium_category_map.get(category, PremiumCategory.OTHER)
        is_premium_category = premium_category in (
            PremiumCategory.EXPORTS,
            PremiumCategory.AI,
            PremiumCategory.HEAVY_RECOMPUTE,
        )
        
        # ACTIVE: run
        if billing_state == BillingState.ACTIVE:
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
            )
        
        # PAST_DUE: run BUT log warning
        if billing_state == BillingState.PAST_DUE:
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
                reason="Payment is past due - job will run with warning",
                should_log_warning=True,
            )
        
        # GRACE_PERIOD: block premium jobs
        if billing_state == BillingState.GRACE_PERIOD:
            if is_premium_category:
                return JobGatingResult(
                    is_allowed=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    reason=f"Premium jobs ({category.value}) are blocked during grace period",
                )
            # Non-premium jobs allowed
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
                reason="Non-premium job allowed during grace period",
            )
        
        # CANCELED: block premium jobs
        if billing_state == BillingState.CANCELED:
            if is_premium_category:
                return JobGatingResult(
                    is_allowed=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    reason=f"Premium jobs ({category.value}) are blocked for canceled subscription",
                )
            # Non-premium jobs allowed (read-only)
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
                reason="Non-premium job allowed for canceled subscription",
            )
        
        # EXPIRED: block premium jobs
        if billing_state == BillingState.EXPIRED:
            if is_premium_category:
                return JobGatingResult(
                    is_allowed=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    reason=f"Premium jobs ({category.value}) are blocked for expired subscription",
                )
            # Non-premium jobs allowed (read-only)
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
                reason="Non-premium job allowed for expired subscription",
            )
        
        # NONE: block premium jobs
        if billing_state == BillingState.NONE:
            if is_premium_category:
                return JobGatingResult(
                    is_allowed=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    reason=f"Premium jobs ({category.value}) require active subscription",
                )
            # Non-premium jobs allowed
            return JobGatingResult(
                is_allowed=True,
                billing_state=billing_state,
                plan_id=plan_id,
                reason="Non-premium job allowed without subscription",
            )
        
        # Unknown state - block premium, allow non-premium
        if is_premium_category:
            return JobGatingResult(
                is_allowed=False,
                billing_state=billing_state,
                plan_id=plan_id,
                reason=f"Unknown billing state - blocking premium job",
            )
        
        return JobGatingResult(
            is_allowed=True,
            billing_state=billing_state,
            plan_id=plan_id,
        )
