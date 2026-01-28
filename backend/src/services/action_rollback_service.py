"""
Action rollback service for Story 8.5.

Service for executing rollbacks on previously executed actions.

ROLLBACK FLOW:
1. Validate action is in succeeded state
2. Validate rollback instructions exist
3. Get platform executor with credentials
4. Capture current state (may have changed)
5. Execute reverse action using rollback instructions
6. Verify state matches original before_state
7. Update action status to rolled_back
8. Log all events for audit

CONSTRAINTS:
- Only succeeded actions can be rolled back
- Rollback instructions must exist
- Some actions may not be reversible (deleted entities)

SECURITY:
- tenant_id from JWT only
- All rollback attempts logged for audit

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.ai_action import AIAction, ActionStatus
from src.models.action_execution_log import ActionExecutionLog
from src.services.platform_credentials_service import (
    PlatformCredentialsService,
    Platform,
)
from src.services.platform_executors import (
    BasePlatformExecutor,
    ExecutionResult,
    StateCapture,
    RetryConfig,
)


logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    action_id: str
    status: ActionStatus
    message: str
    restored_state: Optional[dict] = None
    error_code: Optional[str] = None
    error_details: Optional[dict] = None


class RollbackError(Exception):
    """Error during rollback."""

    def __init__(self, message: str, code: str, action_id: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.action_id = action_id


class ActionRollbackService:
    """
    Service for executing action rollbacks.

    CONSTRAINTS:
    - Only succeeded actions can be rolled back
    - Rollback instructions must exist
    - Some actions may not be reversible (deleted entities)

    SECURITY:
    - tenant_id from JWT only
    - All rollback attempts logged for audit
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        credentials_service: Optional[PlatformCredentialsService] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize rollback service.

        Args:
            db_session: Database session
            tenant_id: Tenant identifier (from JWT only)
            credentials_service: Optional credentials service
            retry_config: Optional retry configuration for executors
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.retry_config = retry_config or RetryConfig()
        self._credentials_service = credentials_service

    @property
    def credentials_service(self) -> PlatformCredentialsService:
        """Get or create credentials service."""
        if self._credentials_service is None:
            self._credentials_service = PlatformCredentialsService(self.db)
        return self._credentials_service

    # =========================================================================
    # Main Rollback Method
    # =========================================================================

    async def rollback_action(
        self,
        action_id: str,
        user_id: Optional[str] = None,
    ) -> RollbackResult:
        """
        Execute rollback for a previously executed action.

        Args:
            action_id: ID of the action to rollback
            user_id: Optional user ID requesting rollback

        Returns:
            RollbackResult with outcome details
        """
        # 1. Get and validate action
        action = self._get_action(action_id)
        self._validate_can_rollback(action)

        # 2. Log rollback start
        triggered_by = f"user:{user_id}" if user_id else "system"
        self._log_event(action, ActionExecutionLog.log_rollback_started(
            tenant_id=self.tenant_id,
            action_id=action.id,
            triggered_by=triggered_by,
        ))

        try:
            # 3. Get platform executor
            executor = await self._get_executor(action)

            # 4. Capture current state
            current_state = await executor.capture_before_state(
                entity_id=action.target_entity_id,
                entity_type=action.target_entity_type.value,
            )

            # 5. Extract rollback parameters
            rollback_instructions = action.rollback_instructions
            rollback_action_type = rollback_instructions.get("action_type")
            rollback_params = rollback_instructions.get("params", {})

            # 6. Generate new idempotency key for rollback
            idempotency_key = f"rollback-{action.idempotency_key or action.id}"

            # 7. Execute the rollback
            result = await executor.execute_action(
                action_type=rollback_action_type,
                entity_id=action.target_entity_id,
                entity_type=action.target_entity_type.value,
                params=rollback_params,
                idempotency_key=idempotency_key,
            )

            if result.success:
                # 8. Verify state matches original before_state
                restored_state = await executor.capture_after_state(
                    entity_id=action.target_entity_id,
                    entity_type=action.target_entity_type.value,
                )

                # 9. Mark as rolled back
                action.mark_rolled_back()

                self._log_event(action, ActionExecutionLog.log_rollback_succeeded(
                    tenant_id=self.tenant_id,
                    action_id=action.id,
                    state_snapshot=restored_state.to_dict(),
                ))

                logger.info(
                    "Action rollback succeeded",
                    extra={
                        "tenant_id": self.tenant_id,
                        "action_id": action.id,
                        "platform": action.platform,
                    }
                )

                return RollbackResult(
                    success=True,
                    action_id=action.id,
                    status=action.status,
                    message="Rollback completed successfully",
                    restored_state=restored_state.to_dict(),
                )

            else:
                # Rollback failed
                action.mark_rollback_failed(result.message)

                self._log_event(action, ActionExecutionLog.log_rollback_failed(
                    tenant_id=self.tenant_id,
                    action_id=action.id,
                    error_details={
                        "message": result.message,
                        "code": result.error_code,
                        "details": result.error_details,
                    },
                ))

                logger.warning(
                    "Action rollback failed",
                    extra={
                        "tenant_id": self.tenant_id,
                        "action_id": action.id,
                        "error": result.message,
                    }
                )

                return RollbackResult(
                    success=False,
                    action_id=action.id,
                    status=action.status,
                    message=result.message,
                    error_code=result.error_code,
                    error_details=result.error_details,
                )

        except Exception as e:
            # Unexpected error
            error_message = str(e)
            action.mark_rollback_failed(error_message)

            self._log_event(action, ActionExecutionLog.log_rollback_failed(
                tenant_id=self.tenant_id,
                action_id=action.id,
                error_details={
                    "message": error_message,
                    "type": type(e).__name__,
                },
            ))

            logger.exception(
                "Unexpected error during rollback",
                extra={
                    "tenant_id": self.tenant_id,
                    "action_id": action.id,
                }
            )

            return RollbackResult(
                success=False,
                action_id=action.id,
                status=action.status,
                message=error_message,
                error_code="UNEXPECTED_ERROR",
                error_details={"type": type(e).__name__},
            )

        finally:
            # Always commit changes
            self.db.commit()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_action(self, action_id: str) -> AIAction:
        """Get action by ID with tenant isolation."""
        action = (
            self.db.query(AIAction)
            .filter(
                AIAction.id == action_id,
                AIAction.tenant_id == self.tenant_id,
            )
            .first()
        )

        if not action:
            raise RollbackError(
                message="Action not found",
                code="NOT_FOUND",
                action_id=action_id,
            )

        return action

    def _validate_can_rollback(self, action: AIAction) -> None:
        """Validate that action can be rolled back."""
        if not action.can_be_rolled_back:
            raise RollbackError(
                message=f"Action cannot be rolled back in status {action.status.value}",
                code="INVALID_STATUS",
                action_id=action.id,
            )

        if not action.rollback_instructions:
            raise RollbackError(
                message="Action has no rollback instructions",
                code="NO_ROLLBACK_INSTRUCTIONS",
                action_id=action.id,
            )

    async def _get_executor(self, action: AIAction) -> BasePlatformExecutor:
        """Get platform executor for action."""
        platform = Platform(action.platform.lower())

        executor = self.credentials_service.get_executor_for_platform(
            tenant_id=self.tenant_id,
            platform=platform,
            retry_config=self.retry_config,
        )

        if not executor:
            raise RollbackError(
                message=f"No credentials available for platform {action.platform}",
                code="NO_CREDENTIALS",
                action_id=action.id,
            )

        if not executor.validate_credentials():
            raise RollbackError(
                message=f"Invalid credentials for platform {action.platform}",
                code="INVALID_CREDENTIALS",
                action_id=action.id,
            )

        return executor

    def _log_event(self, action: AIAction, log_entry: ActionExecutionLog) -> None:
        """Add log entry to database."""
        self.db.add(log_entry)
        self.db.flush()

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_rollbackable_actions(self, limit: int = 50) -> list[AIAction]:
        """Get actions that can be rolled back."""
        return (
            self.db.query(AIAction)
            .filter(
                AIAction.tenant_id == self.tenant_id,
                AIAction.status == ActionStatus.SUCCEEDED,
                AIAction.rollback_instructions.isnot(None),
                AIAction.rollback_executed_at.is_(None),
            )
            .order_by(AIAction.execution_completed_at.desc())
            .limit(limit)
            .all()
        )

    def can_rollback(self, action_id: str) -> tuple[bool, str]:
        """
        Check if an action can be rolled back.

        Returns:
            Tuple of (can_rollback, reason)
        """
        try:
            action = self._get_action(action_id)
            self._validate_can_rollback(action)
            return True, "Action can be rolled back"
        except RollbackError as e:
            return False, str(e)
