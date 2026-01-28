"""
Entitlement policy evaluation.

Determines billing_state from subscription and evaluates feature access.
Implements category-based enforcement matrix for premium endpoints.
"""

import json
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sqlalchemy.orm import Session

from src.models.subscription import Subscription, SubscriptionStatus
from src.models.plan import Plan, PlanFeature
from src.entitlements.categories import PremiumCategory, is_write_method

logger = logging.getLogger(__name__)


class BillingState(str, Enum):
    """Billing state values."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE_PERIOD = "grace_period"
    CANCELED = "canceled"
    EXPIRED = "expired"
    NONE = "none"  # No subscription


@dataclass
class EntitlementCheckResult:
    """Result of an entitlement check."""
    is_entitled: bool
    billing_state: BillingState
    plan_id: Optional[str]
    feature: str
    reason: Optional[str] = None
    required_plan: Optional[str] = None
    grace_period_ends_on: Optional[datetime] = None


@dataclass
class CategoryEntitlementResult:
    """
    Result of a category-based entitlement check.
    
    Includes billing state, grace period info, and action required.
    """
    is_entitled: bool
    billing_state: BillingState
    category: PremiumCategory
    plan_id: Optional[str]
    reason: Optional[str] = None
    grace_period_remaining_days: Optional[int] = None
    action_required: Optional[str] = None  # update_payment, upgrade, contact_support
    current_period_end: Optional[datetime] = None
    is_degraded_access: bool = False  # True if allowed but in degraded mode


class EntitlementPolicy:
    """
    Evaluates feature entitlements based on billing state and plan features.
    
    Loads plan configuration from:
    1. PlanFeature table (primary source of truth)
    2. config/plans.json (optional policy overrides)
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize entitlement policy.
        
        Args:
            db_session: Database session for querying PlanFeature
        """
        self.db = db_session
        self._config_cache: Optional[Dict[str, Any]] = None
        self._grace_period_days = 3  # Default grace period
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config/plans.json if it exists."""
        if self._config_cache is not None:
            return self._config_cache
        
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "plans.json"
        
        if not config_path.exists():
            logger.debug("config/plans.json not found, using database PlanFeature table only")
            self._config_cache = {}
            return self._config_cache
        
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            
            # Extract grace period if configured
            if "grace_period_days" in config:
                self._grace_period_days = int(config["grace_period_days"])
            
            self._config_cache = config
            logger.info("Loaded entitlement config from config/plans.json")
            return config
        except Exception as e:
            logger.warning(f"Failed to load config/plans.json: {e}, using database only")
            self._config_cache = {}
            return self._config_cache
    
    def get_billing_state(self, subscription: Optional[Subscription]) -> BillingState:
        """
        Determine billing_state from subscription.
        
        Args:
            subscription: Subscription object or None
            
        Returns:
            BillingState enum value
        """
        if not subscription:
            return BillingState.NONE
        
        status_value = subscription.status
        
        if status_value == SubscriptionStatus.ACTIVE.value:
            return BillingState.ACTIVE
        
        elif status_value == SubscriptionStatus.FROZEN.value:
            # Check if grace period is still active
            if subscription.grace_period_ends_on:
                now = datetime.now(timezone.utc)
                if now <= subscription.grace_period_ends_on:
                    return BillingState.GRACE_PERIOD
                else:
                    return BillingState.PAST_DUE
            else:
                # Frozen without grace period = past due
                return BillingState.PAST_DUE
        
        elif status_value == SubscriptionStatus.CANCELLED.value:
            return BillingState.CANCELED
        
        elif status_value == SubscriptionStatus.EXPIRED.value:
            return BillingState.EXPIRED
        
        elif status_value == SubscriptionStatus.DECLINED.value:
            return BillingState.EXPIRED
        
        else:
            # PENDING or unknown status
            return BillingState.NONE
    
    def check_feature_entitlement(
        self,
        tenant_id: str,
        feature: str,
        subscription: Optional[Subscription] = None,
    ) -> EntitlementCheckResult:
        """
        Check if tenant is entitled to a feature.
        
        Args:
            tenant_id: Tenant ID
            feature: Feature key to check
            subscription: Optional subscription (will be fetched if not provided)
            
        Returns:
            EntitlementCheckResult with entitlement status
        """
        # Fetch subscription if not provided
        if subscription is None:
            subscription = self.db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id
            ).order_by(Subscription.created_at.desc()).first()
        
        billing_state = self.get_billing_state(subscription)
        plan_id = subscription.plan_id if subscription else None
        
        # Check billing_state-based access rules
        if billing_state == BillingState.EXPIRED:
            return EntitlementCheckResult(
                is_entitled=False,
                billing_state=billing_state,
                plan_id=plan_id,
                feature=feature,
                reason="Subscription has expired",
            )
        
        if billing_state == BillingState.CANCELED:
            # Check config for canceled behavior (end-of-period vs immediate)
            config = self._load_config()
            canceled_behavior = config.get("canceled_behavior", "immediate")
            
            if canceled_behavior == "immediate":
                return EntitlementCheckResult(
                    is_entitled=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    feature=feature,
                    reason="Subscription has been canceled",
                )
            # else: end-of-period allows access until period_end
        
        if billing_state == BillingState.PAST_DUE:
            # Past due = hard block
            return EntitlementCheckResult(
                is_entitled=False,
                billing_state=billing_state,
                plan_id=plan_id,
                feature=feature,
                reason="Payment is past due",
            )
        
        if billing_state == BillingState.GRACE_PERIOD:
            # Grace period: allow access but with warning
            # Check if feature is enabled for plan
            if subscription and plan_id:
                is_enabled = self._check_plan_feature(plan_id, feature)
                if not is_enabled:
                    return EntitlementCheckResult(
                        is_entitled=False,
                        billing_state=billing_state,
                        plan_id=plan_id,
                        feature=feature,
                        reason=f"Feature '{feature}' not available in current plan",
                    )
                
                return EntitlementCheckResult(
                    is_entitled=True,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    feature=feature,
                    grace_period_ends_on=subscription.grace_period_ends_on,
                )
            else:
                return EntitlementCheckResult(
                    is_entitled=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    feature=feature,
                    reason="No active subscription",
                )
        
        if billing_state == BillingState.ACTIVE:
            # Active subscription: check plan features
            if subscription and plan_id:
                is_enabled = self._check_plan_feature(plan_id, feature)
                if not is_enabled:
                    # Find which plan has this feature
                    required_plan = self._find_plan_with_feature(feature)
                    return EntitlementCheckResult(
                        is_entitled=False,
                        billing_state=billing_state,
                        plan_id=plan_id,
                        feature=feature,
                        reason=f"Feature '{feature}' requires a higher plan",
                        required_plan=required_plan,
                    )
                
                return EntitlementCheckResult(
                    is_entitled=True,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    feature=feature,
                )
            else:
                return EntitlementCheckResult(
                    is_entitled=False,
                    billing_state=billing_state,
                    plan_id=plan_id,
                    feature=feature,
                    reason="No active subscription",
                )
        
        # BillingState.NONE or unknown
        return EntitlementCheckResult(
            is_entitled=False,
            billing_state=billing_state,
            plan_id=plan_id,
            feature=feature,
            reason="No subscription found",
        )
    
    def _check_plan_feature(self, plan_id: str, feature: str) -> bool:
        """
        Check if a plan has a feature enabled.
        
        Args:
            plan_id: Plan ID
            feature: Feature key
            
        Returns:
            True if feature is enabled for plan
        """
        plan_feature = self.db.query(PlanFeature).filter(
            PlanFeature.plan_id == plan_id,
            PlanFeature.feature_key == feature,
            PlanFeature.is_enabled == True
        ).first()
        
        return plan_feature is not None
    
    def _find_plan_with_feature(self, feature: str) -> Optional[str]:
        """
        Find a plan that has the feature enabled.
        
        Args:
            feature: Feature key
            
        Returns:
            Plan ID that has the feature, or None
        """
        plan_feature = self.db.query(PlanFeature).filter(
            PlanFeature.feature_key == feature,
            PlanFeature.is_enabled == True
        ).join(Plan).filter(
            Plan.is_active == True
        ).order_by(Plan.price_monthly_cents.asc().nullslast()).first()
        
        if plan_feature:
            return plan_feature.plan_id
        return None
    
    def check_category_entitlement(
        self,
        tenant_id: str,
        category: PremiumCategory,
        method: str,
        subscription: Optional[Subscription] = None,
    ) -> CategoryEntitlementResult:
        """
        Check category-based entitlement based on billing state matrix.
        
        ENFORCEMENT MATRIX:
        - active: full access
        - past_due: allow requests BUT add warning headers
        - grace_period: READ-ONLY (block write/export/ai/heavy recompute)
        - canceled: READ-ONLY until period end (use subscription.current_period_end)
        - expired: HARD BLOCK premium endpoints with HTTP 402
        
        Args:
            tenant_id: Tenant ID
            category: Premium category (exports, ai, heavy_recompute, other)
            method: HTTP method (GET, POST, etc.)
            subscription: Optional subscription (will be fetched if not provided)
            
        Returns:
            CategoryEntitlementResult with entitlement status and metadata
        """
        # Fetch subscription if not provided
        if subscription is None:
            subscription = self.db.query(Subscription).filter(
                Subscription.tenant_id == tenant_id
            ).order_by(Subscription.created_at.desc()).first()
        
        billing_state = self.get_billing_state(subscription)
        plan_id = subscription.plan_id if subscription else None
        is_write = is_write_method(method)
        is_premium_category = category in (
            PremiumCategory.EXPORTS,
            PremiumCategory.AI,
            PremiumCategory.HEAVY_RECOMPUTE,
        )
        
        # Calculate grace period remaining days
        grace_period_remaining = None
        if subscription and subscription.grace_period_ends_on:
            now = datetime.now(timezone.utc)
            if now <= subscription.grace_period_ends_on:
                delta = subscription.grace_period_ends_on - now
                grace_period_remaining = max(0, delta.days)
        
        # EXPIRED: HARD BLOCK premium endpoints
        if billing_state == BillingState.EXPIRED:
            if is_premium_category:
                return CategoryEntitlementResult(
                    is_entitled=False,
                    billing_state=billing_state,
                    category=category,
                    plan_id=plan_id,
                    reason="Subscription has expired. Premium features require active subscription.",
                    action_required="update_payment",
                )
            # Non-premium endpoints allowed even when expired (read-only)
            return CategoryEntitlementResult(
                is_entitled=True,
                billing_state=billing_state,
                category=category,
                plan_id=plan_id,
                is_degraded_access=True,
                action_required="update_payment",
            )
        
        # CANCELED: READ-ONLY until period end
        if billing_state == BillingState.CANCELED:
            if subscription and subscription.current_period_end:
                now = datetime.now(timezone.utc)
                if now > subscription.current_period_end:
                    # Period ended - hard block premium
                    if is_premium_category:
                        return CategoryEntitlementResult(
                            is_entitled=False,
                            billing_state=billing_state,
                            category=category,
                            plan_id=plan_id,
                            reason="Subscription canceled and billing period ended",
                            action_required="update_payment",
                            current_period_end=subscription.current_period_end,
                        )
                    # Non-premium read-only allowed
                    return CategoryEntitlementResult(
                        is_entitled=not is_write,  # Read-only only
                        billing_state=billing_state,
                        category=category,
                        plan_id=plan_id,
                        is_degraded_access=True,
                        action_required="update_payment",
                        current_period_end=subscription.current_period_end,
                    )
                else:
                    # Still within period - READ-ONLY access
                    if is_premium_category:
                        # Premium categories blocked during canceled period
                        return CategoryEntitlementResult(
                            is_entitled=False,
                            billing_state=billing_state,
                            category=category,
                            plan_id=plan_id,
                            reason="Subscription canceled. Premium features require active subscription.",
                            action_required="update_payment",
                            current_period_end=subscription.current_period_end,
                        )
                    # Non-premium: read-only allowed
                    return CategoryEntitlementResult(
                        is_entitled=not is_write,
                        billing_state=billing_state,
                        category=category,
                        plan_id=plan_id,
                        is_degraded_access=True,
                        action_required="update_payment",
                        current_period_end=subscription.current_period_end,
                    )
            else:
                # No period_end - treat as expired
                if is_premium_category:
                    return CategoryEntitlementResult(
                        is_entitled=False,
                        billing_state=billing_state,
                        category=category,
                        plan_id=plan_id,
                        reason="Subscription canceled",
                        action_required="update_payment",
                    )
                return CategoryEntitlementResult(
                    is_entitled=not is_write,
                    billing_state=billing_state,
                    category=category,
                    plan_id=plan_id,
                    is_degraded_access=True,
                    action_required="update_payment",
                )
        
        # GRACE_PERIOD: READ-ONLY (block write/export/ai/heavy recompute)
        if billing_state == BillingState.GRACE_PERIOD:
            if is_premium_category:
                # Premium categories blocked in grace period
                return CategoryEntitlementResult(
                    is_entitled=False,
                    billing_state=billing_state,
                    category=category,
                    plan_id=plan_id,
                    reason="Payment grace period active. Premium features require payment update.",
                    grace_period_remaining_days=grace_period_remaining,
                    action_required="update_payment",
                )
            # Non-premium: read-only allowed
            return CategoryEntitlementResult(
                is_entitled=not is_write,
                billing_state=billing_state,
                category=category,
                plan_id=plan_id,
                is_degraded_access=True,
                grace_period_remaining_days=grace_period_remaining,
                action_required="update_payment",
            )
        
        # PAST_DUE: allow requests BUT add warning headers
        if billing_state == BillingState.PAST_DUE:
            # All requests allowed but with warning
            return CategoryEntitlementResult(
                is_entitled=True,
                billing_state=billing_state,
                category=category,
                plan_id=plan_id,
                is_degraded_access=True,
                action_required="update_payment",
            )
        
        # ACTIVE: full access
        if billing_state == BillingState.ACTIVE:
            return CategoryEntitlementResult(
                is_entitled=True,
                billing_state=billing_state,
                category=category,
                plan_id=plan_id,
            )
        
        # NONE: no subscription - block premium, allow basic read
        if is_premium_category:
            return CategoryEntitlementResult(
                is_entitled=False,
                billing_state=billing_state,
                category=category,
                plan_id=plan_id,
                reason="No active subscription. Premium features require subscription.",
                action_required="upgrade",
            )
        return CategoryEntitlementResult(
            is_entitled=not is_write,  # Read-only for non-premium
            billing_state=billing_state,
            category=category,
            plan_id=plan_id,
            is_degraded_access=True,
            action_required="upgrade",
        )


def get_billing_state_from_subscription(
    subscription: Optional[Subscription]
) -> BillingState:
    """
    Convenience function to get billing state from subscription.
    
    Args:
        subscription: Subscription object or None
        
    Returns:
        BillingState enum value
    """
    if not subscription:
        return BillingState.NONE
    
    status_value = subscription.status
    
    if status_value == SubscriptionStatus.ACTIVE.value:
        return BillingState.ACTIVE
    
    elif status_value == SubscriptionStatus.FROZEN.value:
        # Check if grace period is still active
        if subscription.grace_period_ends_on:
            now = datetime.now(timezone.utc)
            if now <= subscription.grace_period_ends_on:
                return BillingState.GRACE_PERIOD
            else:
                return BillingState.PAST_DUE
        else:
            return BillingState.PAST_DUE
    
    elif status_value == SubscriptionStatus.CANCELLED.value:
        return BillingState.CANCELED
    
    elif status_value == SubscriptionStatus.EXPIRED.value:
        return BillingState.EXPIRED
    
    elif status_value == SubscriptionStatus.DECLINED.value:
        return BillingState.EXPIRED
    
    else:
        return BillingState.NONE
