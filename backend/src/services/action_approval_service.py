"""
Action approval service for Story 8.5.

Handles the workflow for approving AI recommendations and creating
executable actions from them.

WORKFLOW:
1. User selects a recommendation to approve
2. Service validates the recommendation exists and is actionable
3. Service checks tenant entitlements for ai_actions
4. Service creates an AIAction in pending_approval or approved status
5. Action parameters can be customized during approval

SECURITY:
- tenant_id from JWT only, never from client input
- Entitlement and limit checks before creation
- All approvals are logged for audit

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.ai_action import AIAction, ActionType, ActionStatus, ActionTargetEntityType
from src.models.ai_recommendation import AIRecommendation, RecommendationType
from src.models.action_execution_log import ActionExecutionLog, ActionLogEventType
from src.services.billing_entitlements import BillingEntitlementsService, BillingFeature


logger = logging.getLogger(__name__)


# Mapping from recommendation types to action types
RECOMMENDATION_TO_ACTION_MAP = {
    RecommendationType.PAUSE_CAMPAIGN: ActionType.PAUSE_CAMPAIGN,
    RecommendationType.SCALE_CAMPAIGN: ActionType.RESUME_CAMPAIGN,
    RecommendationType.REDUCE_SPEND: ActionType.ADJUST_BUDGET,
    RecommendationType.INCREASE_SPEND: ActionType.ADJUST_BUDGET,
    RecommendationType.REALLOCATE_BUDGET: ActionType.ADJUST_BUDGET,
    RecommendationType.ADJUST_BIDDING: ActionType.ADJUST_BID,
}


class ActionApprovalError(Exception):
    """Error during action approval."""

    def __init__(self, message: str, code: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ActionApprovalService:
    """
    Service for approving recommendations and creating actions.

    Handles:
    - Recommendation to action conversion
    - Entitlement validation
    - Monthly limit enforcement
    - Action parameter customization

    SECURITY: tenant_id must come from JWT, never from client input.
    """

    def __init__(self, db_session: Session, tenant_id: str):
        """
        Initialize the approval service.

        Args:
            db_session: Database session
            tenant_id: Tenant identifier (from JWT only)
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self._billing_service: Optional[BillingEntitlementsService] = None

    @property
    def billing_service(self) -> BillingEntitlementsService:
        """Lazy-load billing service."""
        if self._billing_service is None:
            self._billing_service = BillingEntitlementsService(self.db, self.tenant_id)
        return self._billing_service

    # =========================================================================
    # Main Approval Method
    # =========================================================================

    def approve_recommendation(
        self,
        recommendation_id: str,
        user_id: str,
        override_params: Optional[dict] = None,
        auto_queue: bool = True,
    ) -> AIAction:
        """
        Approve a recommendation and create an executable action.

        Args:
            recommendation_id: ID of the recommendation to approve
            user_id: ID of the user approving (from JWT)
            override_params: Optional parameters to override defaults
            auto_queue: If True, set status to APPROVED (ready for execution)
                       If False, set status to PENDING_APPROVAL

        Returns:
            Created AIAction

        Raises:
            ActionApprovalError: If approval fails
        """
        # 1. Check entitlements
        self._check_entitlement()

        # 2. Check monthly limits
        self._check_monthly_limit()

        # 3. Get and validate recommendation
        recommendation = self._get_recommendation(recommendation_id)

        # 4. Check if action already exists for this recommendation
        existing_action = self._get_existing_action(recommendation_id)
        if existing_action:
            raise ActionApprovalError(
                message="An action already exists for this recommendation",
                code="ACTION_EXISTS",
                status_code=409,
            )

        # 5. Determine action type from recommendation
        action_type = self._get_action_type(recommendation)

        # 6. Build action parameters
        action_params = self._build_action_params(recommendation, override_params)

        # 7. Determine target entity
        target_entity_id, target_entity_type = self._get_target_entity(recommendation)

        # 8. Generate content hash for deduplication
        content_hash = self._generate_content_hash(
            recommendation_id, action_type, action_params
        )

        # 9. Create the action
        action = AIAction(
            tenant_id=self.tenant_id,
            recommendation_id=recommendation_id,
            action_type=action_type,
            platform=self._get_platform(recommendation),
            target_entity_id=target_entity_id,
            target_entity_type=target_entity_type,
            action_params=action_params,
            status=ActionStatus.APPROVED if auto_queue else ActionStatus.PENDING_APPROVAL,
            approved_by=user_id,
            approved_at=datetime.now(timezone.utc),
            content_hash=content_hash,
        )

        self.db.add(action)
        self.db.flush()  # Get the ID

        # 10. Log the approval
        log_entry = ActionExecutionLog.log_approved(
            tenant_id=self.tenant_id,
            action_id=action.id,
            user_id=user_id,
        )
        self.db.add(log_entry)

        logger.info(
            "Action approved from recommendation",
            extra={
                "tenant_id": self.tenant_id,
                "recommendation_id": recommendation_id,
                "action_id": action.id,
                "action_type": action_type.value,
                "approved_by": user_id,
            }
        )

        return action

    # =========================================================================
    # Validation Methods
    # =========================================================================

    def _check_entitlement(self) -> None:
        """Check if tenant is entitled to AI actions."""
        result = self.billing_service.check_feature_entitlement(BillingFeature.AI_ACTIONS)
        if not result.is_entitled:
            raise ActionApprovalError(
                message="AI Actions requires Pro or Enterprise plan",
                code="NOT_ENTITLED",
                status_code=402,
            )

    def _check_monthly_limit(self) -> None:
        """Check if tenant has reached monthly action limit."""
        limit = self.billing_service.get_feature_limit("ai_actions_per_month")

        # -1 means unlimited
        if limit == -1:
            return

        # Count actions this month
        current_count = self._get_monthly_action_count()

        if current_count >= limit:
            raise ActionApprovalError(
                message=f"Monthly action limit ({limit}) reached",
                code="LIMIT_REACHED",
                status_code=402,
            )

    def _get_monthly_action_count(self) -> int:
        """Count actions created this month for tenant."""
        start_of_month = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.tenant_id == self.tenant_id,
                AIAction.created_at >= start_of_month,
            )
            .count()
        )

    def _get_recommendation(self, recommendation_id: str) -> AIRecommendation:
        """Get and validate recommendation."""
        recommendation = (
            self.db.query(AIRecommendation)
            .filter(
                AIRecommendation.id == recommendation_id,
                AIRecommendation.tenant_id == self.tenant_id,
            )
            .first()
        )

        if not recommendation:
            raise ActionApprovalError(
                message="Recommendation not found",
                code="NOT_FOUND",
                status_code=404,
            )

        if recommendation.is_dismissed:
            raise ActionApprovalError(
                message="Cannot approve a dismissed recommendation",
                code="DISMISSED",
                status_code=400,
            )

        return recommendation

    def _get_existing_action(self, recommendation_id: str) -> Optional[AIAction]:
        """Check if an action already exists for this recommendation."""
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.recommendation_id == recommendation_id,
                AIAction.tenant_id == self.tenant_id,
                # Only check non-terminal actions
                AIAction.status.notin_([
                    ActionStatus.FAILED,
                    ActionStatus.ROLLED_BACK,
                    ActionStatus.ROLLBACK_FAILED,
                ])
            )
            .first()
        )

    # =========================================================================
    # Action Building Methods
    # =========================================================================

    def _get_action_type(self, recommendation: AIRecommendation) -> ActionType:
        """Determine action type from recommendation type."""
        action_type = RECOMMENDATION_TO_ACTION_MAP.get(recommendation.recommendation_type)

        if action_type is None:
            raise ActionApprovalError(
                message=f"Recommendation type {recommendation.recommendation_type.value} is not actionable",
                code="NOT_ACTIONABLE",
                status_code=400,
            )

        return action_type

    def _build_action_params(
        self,
        recommendation: AIRecommendation,
        override_params: Optional[dict] = None,
    ) -> dict:
        """
        Build action parameters from recommendation.

        Args:
            recommendation: Source recommendation
            override_params: Optional user-provided overrides

        Returns:
            Dictionary of action parameters
        """
        params = {}

        # Extract default params based on recommendation type
        rec_type = recommendation.recommendation_type

        if rec_type == RecommendationType.PAUSE_CAMPAIGN:
            params["status"] = "PAUSED"

        elif rec_type == RecommendationType.SCALE_CAMPAIGN:
            params["status"] = "ACTIVE"

        elif rec_type in (
            RecommendationType.REDUCE_SPEND,
            RecommendationType.INCREASE_SPEND,
            RecommendationType.REALLOCATE_BUDGET,
        ):
            # Budget adjustment - user must provide new_budget
            params["budget_type"] = "daily"  # Default to daily

        elif rec_type == RecommendationType.ADJUST_BIDDING:
            # Bid adjustment - user must provide bid params
            pass

        # Add currency if available
        if recommendation.currency:
            params["currency"] = recommendation.currency

        # Apply user overrides
        if override_params:
            params.update(override_params)

        return params

    def _get_target_entity(
        self,
        recommendation: AIRecommendation,
    ) -> tuple[str, ActionTargetEntityType]:
        """
        Get target entity from recommendation.

        Returns:
            Tuple of (entity_id, entity_type)
        """
        entity_id = recommendation.affected_entity
        entity_type_str = recommendation.affected_entity_type

        if not entity_id:
            raise ActionApprovalError(
                message="Recommendation does not have a target entity",
                code="NO_TARGET",
                status_code=400,
            )

        # Map recommendation entity type to action entity type
        entity_type_map = {
            "campaign": ActionTargetEntityType.CAMPAIGN,
            "platform": ActionTargetEntityType.CAMPAIGN,  # Default to campaign
            "account": ActionTargetEntityType.CAMPAIGN,  # Default to campaign
        }

        entity_type = entity_type_map.get(
            entity_type_str.value if entity_type_str else "campaign",
            ActionTargetEntityType.CAMPAIGN
        )

        return entity_id, entity_type

    def _get_platform(self, recommendation: AIRecommendation) -> str:
        """Get platform from recommendation or related insight."""
        # Try to get from the related insight
        if recommendation.related_insight_id:
            from src.models.ai_insight import AIInsight
            insight = (
                self.db.query(AIInsight)
                .filter(AIInsight.id == recommendation.related_insight_id)
                .first()
            )
            if insight and insight.platform:
                return insight.platform.lower()

        # Default to meta if unknown
        return "meta"

    def _generate_content_hash(
        self,
        recommendation_id: str,
        action_type: ActionType,
        params: dict,
    ) -> str:
        """Generate SHA256 hash for deduplication."""
        import json
        content = f"{recommendation_id}:{action_type.value}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    # =========================================================================
    # Additional Methods
    # =========================================================================

    def get_action(self, action_id: str) -> Optional[AIAction]:
        """Get an action by ID for this tenant."""
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.id == action_id,
                AIAction.tenant_id == self.tenant_id,
            )
            .first()
        )

    def cancel_action(self, action_id: str, user_id: str) -> bool:
        """
        Cancel a pending action.

        Args:
            action_id: ID of the action to cancel
            user_id: ID of the user cancelling

        Returns:
            True if cancelled, False if not found or not cancellable
        """
        action = self.get_action(action_id)

        if not action:
            return False

        if action.status not in (ActionStatus.PENDING_APPROVAL, ActionStatus.APPROVED):
            return False

        # Delete the action (or mark as cancelled)
        self.db.delete(action)

        logger.info(
            "Action cancelled",
            extra={
                "tenant_id": self.tenant_id,
                "action_id": action_id,
                "cancelled_by": user_id,
            }
        )

        return True

    def list_pending_actions(self, limit: int = 50) -> list[AIAction]:
        """List pending actions for this tenant."""
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.tenant_id == self.tenant_id,
                AIAction.status.in_([
                    ActionStatus.PENDING_APPROVAL,
                    ActionStatus.APPROVED,
                    ActionStatus.QUEUED,
                ])
            )
            .order_by(AIAction.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_actions_for_recommendation(self, recommendation_id: str) -> list[AIAction]:
        """Get all actions created from a recommendation."""
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.recommendation_id == recommendation_id,
                AIAction.tenant_id == self.tenant_id,
            )
            .order_by(AIAction.created_at.desc())
            .all()
        )
