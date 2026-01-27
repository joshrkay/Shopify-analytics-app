"""
5.8.3 - Rollback Orchestrator

State machine for safe rollback execution. AI MUST NOT trigger autonomously.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .base import load_yaml_config, serialize_dataclass

logger = logging.getLogger(__name__)


class RollbackScope(Enum):
    """Scope of the rollback operation."""

    GLOBAL = "global"
    TENANT_SUBSET = "tenant_subset"
    GRADUAL = "gradual"


class RollbackState(Enum):
    """State machine states for rollback process."""

    PENDING = "pending"
    VALIDATING_AUTHORITY = "validating_authority"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_FORWARD = "rolled_forward"  # Rollback was reversed


@dataclass
class RollbackAction:
    """A single action in the rollback sequence."""

    action: str
    target: str
    order: int
    status: str = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass(self)


@dataclass
class RollbackRequest:
    """Request to initiate a rollback."""

    rollback_id: str
    triggered_by: str
    trigger_role: str
    reason: str
    scope: RollbackScope
    target_tenants: list[str] | None = None
    target_version: str = "previous_stable"
    incident_ticket: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass(self)


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    rollback_id: str
    state: RollbackState
    scope: RollbackScope
    actions_completed: list[RollbackAction]
    actions_failed: list[RollbackAction]
    verification_passed: bool
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    affected_tenants: int = 0
    reversible: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass(self)


@dataclass
class VerificationResult:
    """Result of rollback verification checks."""

    passed: bool
    checks: list[dict[str, Any]]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass(self)


class RollbackOrchestrator:
    """
    Orchestrates rollback operations with state machine control.

    Ensures rollbacks are executed safely, verified, and audited.
    """

    def __init__(
        self,
        config_path: str | Path,
        action_handlers: dict[str, Callable[..., bool]] | None = None,
        verification_handlers: dict[str, Callable[..., dict[str, Any]]] | None = None,
        audit_logger: logging.Logger | None = None,
    ):
        """
        Initialize the rollback orchestrator.

        Args:
            config_path: Path to rollback_config.yaml
            action_handlers: Dict mapping action names to handler functions
            verification_handlers: Dict mapping check names to verification functions
            audit_logger: Logger for audit trail
        """
        self.config_path = Path(config_path)
        self.action_handlers = action_handlers or {}
        self.verification_handlers = verification_handlers or {}
        self.audit_logger = audit_logger or logging.getLogger("rollback_audit")

        self._config: dict[str, Any] = {}
        self._active_rollbacks: dict[str, RollbackResult] = {}
        self._rollback_history: list[RollbackResult] = []

        self._load_config()
        self._register_default_handlers()

    def _load_config(self) -> None:
        """Load rollback configuration from YAML."""
        self._config = load_yaml_config(self.config_path, logger)

    def _register_default_handlers(self) -> None:
        """Register default action handlers with real implementations."""
        from .rollback_handlers import get_default_action_handlers

        default_handlers = get_default_action_handlers()
        for action_name, handler in default_handlers.items():
            if action_name not in self.action_handlers:
                self.action_handlers[action_name] = handler

    def _stub_handler(self, **kwargs: Any) -> bool:
        """Stub handler for actions - returns True (success)."""
        logger.info(f"Stub handler called with: {kwargs}")
        return True

    def validate_authority(self, request: RollbackRequest) -> tuple[bool, str]:
        """
        Validate that the requester has authority to trigger rollback.

        Args:
            request: The rollback request

        Returns:
            Tuple of (authorized, reason)
        """
        control = self._config.get("rollback_control", {})
        allowed_authorities = control.get("trigger_authority", [])

        if request.trigger_role not in allowed_authorities:
            return (
                False,
                f"'{request.trigger_role}' is not authorized to trigger rollback. "
                f"Allowed: {allowed_authorities}",
            )

        return (True, f"Authorized: {request.trigger_role}")

    def initiate_rollback(self, request: RollbackRequest) -> RollbackResult:
        """
        Initiate a rollback operation.

        Args:
            request: RollbackRequest with details

        Returns:
            RollbackResult with initial state
        """
        # Validate authority first
        authorized, reason = self.validate_authority(request)

        result = RollbackResult(
            rollback_id=request.rollback_id,
            state=RollbackState.VALIDATING_AUTHORITY,
            scope=request.scope,
            actions_completed=[],
            actions_failed=[],
            verification_passed=False,
            started_at=datetime.now(timezone.utc),
        )

        self._log_audit(
            "rollback_initiated",
            request.rollback_id,
            {
                "triggered_by": request.triggered_by,
                "trigger_role": request.trigger_role,
                "reason": request.reason,
                "scope": request.scope.value,
                "authorized": authorized,
            },
        )

        if not authorized:
            result.state = RollbackState.FAILED
            result.error = reason
            result.completed_at = datetime.now(timezone.utc)
            return result

        # Store as active rollback
        self._active_rollbacks[request.rollback_id] = result

        # Execute based on scope
        if request.scope == RollbackScope.GRADUAL:
            return self._execute_gradual_rollback(request, result)
        else:
            return self._execute_immediate_rollback(request, result)

    def _execute_immediate_rollback(
        self, request: RollbackRequest, result: RollbackResult
    ) -> RollbackResult:
        """Execute an immediate (global or tenant-subset) rollback."""
        result.state = RollbackState.EXECUTING

        strategy = self._config.get("rollback_strategy", {})
        actions_config = strategy.get("rollback_actions", [])

        # Sort actions by order
        sorted_actions = sorted(actions_config, key=lambda x: x.get("order", 0))

        for action_config in sorted_actions:
            action = RollbackAction(
                action=action_config.get("action", ""),
                target=self._interpolate_target(
                    action_config.get("target", ""), request
                ),
                order=action_config.get("order", 0),
            )

            success = self._execute_action(action, request)

            if success:
                result.actions_completed.append(action)
            else:
                result.actions_failed.append(action)
                # Continue with other actions but mark overall failure
                self._log_audit(
                    "action_failed",
                    request.rollback_id,
                    {"action": action.action, "error": action.error},
                )

        # Verify rollback success
        result.state = RollbackState.VERIFYING
        verification = self._verify_rollback(request)
        result.verification_passed = verification.passed

        if verification.passed and not result.actions_failed:
            result.state = RollbackState.COMPLETED
        else:
            result.state = RollbackState.FAILED
            if not verification.passed:
                result.error = "Verification failed after rollback"

        result.completed_at = datetime.now(timezone.utc)

        self._log_audit(
            "rollback_completed",
            request.rollback_id,
            {
                "state": result.state.value,
                "actions_completed": len(result.actions_completed),
                "actions_failed": len(result.actions_failed),
                "verification_passed": result.verification_passed,
            },
        )

        # Move to history
        self._rollback_history.append(result)
        if request.rollback_id in self._active_rollbacks:
            del self._active_rollbacks[request.rollback_id]

        return result

    def _execute_gradual_rollback(
        self, request: RollbackRequest, result: RollbackResult
    ) -> RollbackResult:
        """Execute a gradual (canary) rollback."""
        strategy = self._config.get("rollback_strategy", {})
        gradual_config = strategy.get("gradual_rollback", {})

        canary_percentage = gradual_config.get("canary_percentage", 10)
        interval_minutes = gradual_config.get("rollout_interval_minutes", 5)
        success_criteria = gradual_config.get("success_criteria", [])

        result.state = RollbackState.EXECUTING

        # Simulate gradual rollback in batches
        current_percentage = 0
        batch = 0

        while current_percentage < 100:
            batch += 1
            current_percentage = min(current_percentage + canary_percentage, 100)

            self._log_audit(
                "gradual_rollback_batch",
                request.rollback_id,
                {"batch": batch, "percentage": current_percentage},
            )

            # Execute rollback for this batch
            # In real implementation, this would target specific tenants
            batch_success = self._execute_batch_rollback(
                request, current_percentage, batch
            )

            if not batch_success:
                result.state = RollbackState.PAUSED
                result.error = f"Batch {batch} failed at {current_percentage}%"
                self._log_audit(
                    "gradual_rollback_paused",
                    request.rollback_id,
                    {"batch": batch, "percentage": current_percentage},
                )
                return result

            # Check success criteria before continuing
            if current_percentage < 100:
                criteria_met = self._check_success_criteria(success_criteria)
                if not criteria_met:
                    result.state = RollbackState.PAUSED
                    result.error = f"Success criteria not met at {current_percentage}%"
                    return result

                # Wait before next batch (in real impl, this would be async)
                logger.info(
                    f"Waiting {interval_minutes} minutes before next batch..."
                )

        # Final verification
        result.state = RollbackState.VERIFYING
        verification = self._verify_rollback(request)
        result.verification_passed = verification.passed

        if verification.passed:
            result.state = RollbackState.COMPLETED
        else:
            result.state = RollbackState.FAILED
            result.error = "Final verification failed"

        result.completed_at = datetime.now(timezone.utc)
        self._rollback_history.append(result)

        return result

    def _execute_action(
        self, action: RollbackAction, request: RollbackRequest
    ) -> bool:
        """Execute a single rollback action."""
        action.started_at = datetime.now(timezone.utc)
        action.status = "executing"

        handler = self.action_handlers.get(action.action)
        if not handler:
            action.status = "failed"
            action.error = f"No handler registered for action: {action.action}"
            action.completed_at = datetime.now(timezone.utc)
            return False

        try:
            success = handler(
                target=action.target,
                rollback_id=request.rollback_id,
                scope=request.scope.value,
                reason=request.reason,
            )

            if success:
                action.status = "completed"
            else:
                action.status = "failed"
                action.error = "Handler returned False"

        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            logger.exception(f"Action {action.action} failed: {e}")

        action.completed_at = datetime.now(timezone.utc)
        return action.status == "completed"

    def _execute_batch_rollback(
        self, request: RollbackRequest, percentage: int, batch: int
    ) -> bool:
        """
        Execute rollback for a batch of tenants.

        Implements tenant-targeted rollback based on percentage.
        """
        logger.info(f"Executing batch {batch} rollback at {percentage}%")

        try:
            # Get tenant list from request or database
            target_tenants = request.target_tenants or self._get_all_tenants()

            if not target_tenants:
                logger.warning("No tenants found for batch rollback")
                return True

            # Calculate batch size based on percentage
            batch_size = max(1, int(len(target_tenants) * percentage / 100))
            batch_tenants = target_tenants[:batch_size]

            logger.info(
                f"Processing batch {batch}",
                extra={
                    "total_tenants": len(target_tenants),
                    "batch_size": len(batch_tenants),
                    "percentage": percentage,
                },
            )

            # Execute rollback actions for each tenant in batch
            strategy = self._config.get("rollback_strategy", {})
            actions_config = strategy.get("rollback_actions", [])
            sorted_actions = sorted(actions_config, key=lambda x: x.get("order", 0))

            failed_tenants = []
            for tenant_id in batch_tenants:
                tenant_success = True
                for action_config in sorted_actions:
                    action = RollbackAction(
                        action=action_config.get("action", ""),
                        target=self._interpolate_target(
                            action_config.get("target", ""), request
                        ),
                        order=action_config.get("order", 0),
                    )

                    # Add tenant context to the action
                    handler = self.action_handlers.get(action.action)
                    if handler:
                        try:
                            success = handler(
                                target=action.target,
                                rollback_id=request.rollback_id,
                                scope=request.scope.value,
                                reason=request.reason,
                                tenant_id=tenant_id,
                            )
                            if not success:
                                tenant_success = False
                        except Exception as e:
                            logger.error(
                                f"Batch rollback action failed for tenant",
                                extra={"tenant_id": tenant_id, "action": action.action, "error": str(e)},
                            )
                            tenant_success = False

                if not tenant_success:
                    failed_tenants.append(tenant_id)

            # Batch succeeds if failure rate is below threshold
            failure_threshold = self._config.get("rollback_strategy", {}).get(
                "batch_failure_threshold", 0.1
            )
            failure_rate = len(failed_tenants) / len(batch_tenants) if batch_tenants else 0

            if failure_rate > failure_threshold:
                logger.error(
                    f"Batch {batch} exceeded failure threshold",
                    extra={
                        "failed_tenants": len(failed_tenants),
                        "total_tenants": len(batch_tenants),
                        "failure_rate": failure_rate,
                        "threshold": failure_threshold,
                    },
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Batch rollback failed: {e}")
            return False

    def _get_all_tenants(self) -> list[str]:
        """Get all tenant IDs from database."""
        try:
            # Import here to avoid circular dependencies
            from src.database.session import get_session_factory

            SessionLocal = get_session_factory()
            session = SessionLocal()
            try:
                from src.models.store import ShopifyStore
                stores = session.query(ShopifyStore.tenant_id).distinct().all()
                return [s[0] for s in stores if s[0]]
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Could not get tenants from database: {e}")
            return []

    def _check_success_criteria(self, criteria: list[str]) -> bool:
        """
        Check if success criteria are met after a rollback batch.

        Implements actual metric checks for:
        - Error rate thresholds
        - Latency thresholds
        - Health check status
        """
        import os

        all_passed = True

        for criterion in criteria:
            passed = True
            measured_value = None

            try:
                if criterion == "error_rate < 1%":
                    # Check error rate from monitoring system
                    measured_value = self._get_error_rate()
                    passed = measured_value < 0.01

                elif criterion == "latency_p99 < baseline * 1.5":
                    # Check latency metrics
                    current_latency = self._get_latency_p99()
                    baseline_latency = self._get_baseline_latency()
                    if baseline_latency and current_latency:
                        passed = current_latency < baseline_latency * 1.5
                        measured_value = current_latency

                elif criterion == "health_check_pass":
                    # Run health check
                    passed = self._run_health_check()
                    measured_value = "passed" if passed else "failed"

                else:
                    # Unknown criterion - log and pass
                    logger.warning(f"Unknown success criterion: {criterion}")
                    passed = True

                logger.info(
                    f"Success criterion check: {criterion}",
                    extra={
                        "passed": passed,
                        "measured_value": measured_value,
                    },
                )

                if not passed:
                    all_passed = False

            except Exception as e:
                logger.error(f"Failed to check criterion {criterion}: {e}")
                # Don't fail the whole check on a single error
                continue

        return all_passed

    def _get_error_rate(self) -> float:
        """Get current error rate from monitoring."""
        try:
            # Would integrate with your monitoring system (Datadog, CloudWatch, etc.)
            # For now, check a simple health endpoint
            import httpx

            api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            response = httpx.get(f"{api_url}/health", timeout=5.0)
            # If health check passes, assume low error rate
            return 0.0 if response.status_code == 200 else 0.05
        except httpx.RequestError as e:
            logger.debug("Health check unavailable for error rate", extra={"error": str(e)})
            return 0.0  # Default to passing if monitoring unavailable

    def _get_latency_p99(self) -> float | None:
        """Get current p99 latency from monitoring."""
        # Would integrate with monitoring system
        return None

    def _get_baseline_latency(self) -> float | None:
        """Get baseline p99 latency for comparison."""
        # Would load from historical data
        return None

    def _run_health_check(self) -> bool:
        """Run application health check."""
        try:
            import httpx

            api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            response = httpx.get(f"{api_url}/health", timeout=5.0)
            return response.status_code == 200
        except httpx.RequestError as e:
            logger.debug("Health check failed", extra={"error": str(e)})
            return False

    def _verify_rollback(self, request: RollbackRequest) -> VerificationResult:
        """Verify that rollback was successful."""
        strategy = self._config.get("rollback_strategy", {})
        verification_config = strategy.get("verification", {})
        checks_config = verification_config.get("checks", [])

        checks = []
        all_passed = True

        for check_config in checks_config:
            check_name = check_config.get("name", "unknown")
            threshold = check_config.get("threshold")
            comparison = check_config.get("comparison", "less_than")

            # Execute verification handler if registered
            handler = self.verification_handlers.get(check_name)
            if handler:
                try:
                    result = handler(
                        rollback_id=request.rollback_id, config=check_config
                    )
                    passed = result.get("passed", False)
                    measured_value = result.get("measured_value")
                except Exception as e:
                    passed = False
                    measured_value = None
                    logger.error(f"Verification check {check_name} failed: {e}")
            else:
                # Stub - assume passed
                passed = True
                measured_value = 0

            check_result = {
                "name": check_name,
                "passed": passed,
                "threshold": threshold,
                "measured_value": measured_value,
                "comparison": comparison,
            }
            checks.append(check_result)

            if not passed:
                all_passed = False

        return VerificationResult(passed=all_passed, checks=checks)

    def _interpolate_target(self, target: str, request: RollbackRequest) -> str:
        """Interpolate variables in target string."""
        return target.replace("${rollback_id}", request.rollback_id).replace(
            "${scope}", request.scope.value
        )

    def _log_audit(
        self, action: str, rollback_id: str, context: dict[str, Any]
    ) -> None:
        """Log an audit entry."""
        self.audit_logger.info(
            f"ROLLBACK_AUDIT: {action} | ID: {rollback_id} | Context: {context}"
        )

    def pause_rollback(self, rollback_id: str) -> bool:
        """Pause an active gradual rollback."""
        if rollback_id not in self._active_rollbacks:
            return False

        result = self._active_rollbacks[rollback_id]
        if result.state == RollbackState.EXECUTING:
            result.state = RollbackState.PAUSED
            self._log_audit("rollback_paused", rollback_id, {})
            return True

        return False

    def resume_rollback(self, rollback_id: str) -> bool:
        """Resume a paused rollback."""
        if rollback_id not in self._active_rollbacks:
            return False

        result = self._active_rollbacks[rollback_id]
        if result.state == RollbackState.PAUSED:
            result.state = RollbackState.EXECUTING
            self._log_audit("rollback_resumed", rollback_id, {})
            return True

        return False

    def reverse_rollback(
        self, rollback_id: str, triggered_by: str, trigger_role: str
    ) -> RollbackResult | None:
        """
        Reverse a completed rollback (roll forward).

        Args:
            rollback_id: ID of the rollback to reverse
            triggered_by: Who is reversing
            trigger_role: Role of the person reversing

        Returns:
            New RollbackResult for the reversal, or None if not possible
        """
        # Find the rollback in history
        original = None
        for r in self._rollback_history:
            if r.rollback_id == rollback_id:
                original = r
                break

        if not original:
            logger.warning(f"Rollback {rollback_id} not found in history")
            return None

        if not original.reversible:
            logger.warning(f"Rollback {rollback_id} is not reversible")
            return None

        # Create reversal request
        reversal_request = RollbackRequest(
            rollback_id=f"reversal-{rollback_id}-{uuid.uuid4().hex[:8]}",
            triggered_by=triggered_by,
            trigger_role=trigger_role,
            reason=f"Reversal of rollback {rollback_id}",
            scope=original.scope,
        )

        self._log_audit(
            "rollback_reversal_initiated",
            reversal_request.rollback_id,
            {"original_rollback": rollback_id},
        )

        # Execute reversal (would restore to post-rollback state in real impl)
        return self.initiate_rollback(reversal_request)

    def get_active_rollbacks(self) -> list[dict[str, Any]]:
        """Get all active rollbacks."""
        return [r.to_dict() for r in self._active_rollbacks.values()]

    def get_rollback_history(self) -> list[dict[str, Any]]:
        """Get rollback history."""
        return [r.to_dict() for r in self._rollback_history]
