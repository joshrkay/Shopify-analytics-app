"""
Base platform executor for external API integrations.

Provides abstract base class and common utilities for executing
actions on external platforms (Meta, Google, Shopify).

PRINCIPLES:
- External platform is source of truth
- Full request/response logging for audit
- Retry with exponential backoff for transient failures
- No blind retries - require human review for persistent failures

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypeVar, Generic

logger = logging.getLogger(__name__)


# =============================================================================
# Result Types
# =============================================================================

class ExecutionResultStatus(str, Enum):
    """Status of an execution attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"


@dataclass
class ExecutionResult:
    """
    Result of executing an action on an external platform.

    Captures the full outcome including success/failure status,
    any error details, and the confirmed state from the platform.
    """
    status: ExecutionResultStatus
    success: bool
    message: str

    # Platform response data
    response_data: Optional[dict] = None
    http_status_code: Optional[int] = None

    # Error details if failed
    error_code: Optional[str] = None
    error_details: Optional[dict] = None

    # Confirmed state from platform (source of truth)
    confirmed_state: Optional[dict] = None

    # Timing
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[float] = None

    # Retry info
    retry_after_seconds: Optional[float] = None
    is_retryable: bool = False

    @classmethod
    def success_result(
        cls,
        message: str,
        response_data: Optional[dict] = None,
        confirmed_state: Optional[dict] = None,
        http_status_code: int = 200,
        duration_ms: Optional[float] = None,
    ) -> "ExecutionResult":
        """Create a successful execution result."""
        return cls(
            status=ExecutionResultStatus.SUCCESS,
            success=True,
            message=message,
            response_data=response_data,
            confirmed_state=confirmed_state,
            http_status_code=http_status_code,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure_result(
        cls,
        message: str,
        error_code: Optional[str] = None,
        error_details: Optional[dict] = None,
        http_status_code: Optional[int] = None,
        is_retryable: bool = False,
        retry_after_seconds: Optional[float] = None,
        duration_ms: Optional[float] = None,
    ) -> "ExecutionResult":
        """Create a failed execution result."""
        # Determine status based on error type
        if http_status_code == 429:
            status = ExecutionResultStatus.RATE_LIMITED
        elif http_status_code == 401 or http_status_code == 403:
            status = ExecutionResultStatus.AUTH_ERROR
        elif http_status_code == 404:
            status = ExecutionResultStatus.NOT_FOUND
        elif http_status_code == 400 or http_status_code == 422:
            status = ExecutionResultStatus.VALIDATION_ERROR
        else:
            status = ExecutionResultStatus.FAILED

        return cls(
            status=status,
            success=False,
            message=message,
            error_code=error_code,
            error_details=error_details,
            http_status_code=http_status_code,
            is_retryable=is_retryable,
            retry_after_seconds=retry_after_seconds,
            duration_ms=duration_ms,
        )


@dataclass
class StateCapture:
    """
    Captured state of an entity from an external platform.

    Used for before/after state comparison and rollback generation.
    """
    entity_id: str
    entity_type: str
    platform: str
    state: dict
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "platform": self.platform,
            "state": self.state,
            "captured_at": self.captured_at.isoformat(),
        }


# =============================================================================
# Retry Configuration
# =============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1  # 10% random jitter
    retryable_status_codes: tuple = (429, 500, 502, 503, 504)

    def calculate_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Calculate delay before next retry attempt.

        Args:
            attempt: Current attempt number (0-indexed)
            retry_after: Optional Retry-After header value in seconds

        Returns:
            Delay in seconds before next retry
        """
        if retry_after is not None:
            # Respect Retry-After header, but cap at max_delay
            return min(retry_after, self.max_delay_seconds)

        # Exponential backoff with jitter
        import random
        base_delay = self.initial_delay_seconds * (self.backoff_multiplier ** attempt)
        jitter = random.uniform(0, base_delay * self.jitter_factor)
        return min(base_delay + jitter, self.max_delay_seconds)


# =============================================================================
# Platform API Error
# =============================================================================

class PlatformAPIError(Exception):
    """
    Error from an external platform API.

    Captures all relevant error information for logging and handling.
    """

    def __init__(
        self,
        message: str,
        platform: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        response: Optional[dict] = None,
        retry_after: Optional[float] = None,
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.platform = platform
        self.status_code = status_code
        self.error_code = error_code
        self.response = response or {}
        self.retry_after = retry_after
        self.is_retryable = is_retryable

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "message": str(self),
            "platform": self.platform,
            "status_code": self.status_code,
            "error_code": self.error_code,
            "response": self.response,
            "retry_after": self.retry_after,
            "is_retryable": self.is_retryable,
        }


# =============================================================================
# Base Platform Executor
# =============================================================================

class BasePlatformExecutor(ABC):
    """
    Abstract base class for platform-specific action executors.

    Each platform executor handles:
    - API authentication
    - Rate limiting with exponential backoff
    - State capture (before/after)
    - Action execution
    - Rollback instruction generation

    SECURITY:
    - Credentials should be encrypted at rest
    - Access tokens should have minimal required scopes
    - All API calls are logged for audit

    Subclasses must implement:
    - platform_name: The platform identifier
    - get_entity_state(): Fetch current entity state
    - _execute_action_impl(): Execute the actual action
    - generate_rollback_params(): Generate rollback parameters
    """

    # Platform identifier (override in subclass)
    platform_name: str = "base"

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize the executor.

        Args:
            retry_config: Optional retry configuration
        """
        self.retry_config = retry_config or RetryConfig()
        self._request_count = 0
        self._last_request_time: Optional[float] = None

    # =========================================================================
    # Abstract Methods (must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    async def get_entity_state(
        self,
        entity_id: str,
        entity_type: str,
    ) -> StateCapture:
        """
        Get current state of target entity from platform.

        This is called BEFORE and AFTER execution to capture state
        for audit and rollback purposes.

        Args:
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity (campaign, ad_set, ad, etc.)

        Returns:
            StateCapture with current entity state

        Raises:
            PlatformAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def _execute_action_impl(
        self,
        action_type: str,
        entity_id: str,
        entity_type: str,
        params: dict,
        idempotency_key: str,
    ) -> ExecutionResult:
        """
        Execute action on platform (internal implementation).

        This method should NOT include retry logic - that is handled
        by the public execute_action method.

        Args:
            action_type: Type of action (pause_campaign, adjust_budget, etc.)
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity
            params: Action parameters
            idempotency_key: Key for idempotent execution

        Returns:
            ExecutionResult with outcome details

        Raises:
            PlatformAPIError: If API call fails
        """
        pass

    @abstractmethod
    def generate_rollback_params(
        self,
        action_type: str,
        before_state: dict,
    ) -> dict:
        """
        Generate parameters to reverse an action.

        Given the action type and the state before execution,
        return the parameters needed to restore that state.

        Args:
            action_type: Type of action that was executed
            before_state: Entity state before the action

        Returns:
            Dictionary of parameters for rollback action
        """
        pass

    @abstractmethod
    def validate_credentials(self) -> bool:
        """
        Validate that credentials are present and properly formatted.

        Returns:
            True if credentials are valid, False otherwise
        """
        pass

    # =========================================================================
    # Public Methods
    # =========================================================================

    async def execute_action(
        self,
        action_type: str,
        entity_id: str,
        entity_type: str,
        params: dict,
        idempotency_key: str,
    ) -> ExecutionResult:
        """
        Execute action with retry logic.

        This is the main entry point for action execution. It wraps
        the internal implementation with retry logic for transient failures.

        IMPORTANT: This method does NOT retry blindly. After max retries,
        it returns a failure result for human review.

        Args:
            action_type: Type of action to execute
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity
            params: Action parameters
            idempotency_key: Key for idempotent execution

        Returns:
            ExecutionResult with outcome details
        """
        last_error: Optional[Exception] = None
        last_result: Optional[ExecutionResult] = None

        for attempt in range(self.retry_config.max_retries + 1):
            start_time = time.time()

            try:
                result = await self._execute_action_impl(
                    action_type=action_type,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    params=params,
                    idempotency_key=idempotency_key,
                )

                duration_ms = (time.time() - start_time) * 1000
                result.duration_ms = duration_ms

                if result.success:
                    logger.info(
                        "Action executed successfully",
                        extra={
                            "platform": self.platform_name,
                            "action_type": action_type,
                            "entity_id": entity_id,
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms,
                        }
                    )
                    return result

                # Check if we should retry
                if not result.is_retryable or attempt == self.retry_config.max_retries:
                    logger.warning(
                        "Action failed (not retrying)",
                        extra={
                            "platform": self.platform_name,
                            "action_type": action_type,
                            "entity_id": entity_id,
                            "attempt": attempt + 1,
                            "is_retryable": result.is_retryable,
                            "error": result.message,
                        }
                    )
                    return result

                last_result = result

            except PlatformAPIError as e:
                duration_ms = (time.time() - start_time) * 1000
                last_error = e

                # Check if retryable
                is_retryable = (
                    e.is_retryable or
                    e.status_code in self.retry_config.retryable_status_codes
                )

                if not is_retryable or attempt == self.retry_config.max_retries:
                    logger.error(
                        "Platform API error (not retrying)",
                        extra={
                            "platform": self.platform_name,
                            "action_type": action_type,
                            "entity_id": entity_id,
                            "attempt": attempt + 1,
                            "error": str(e),
                            "status_code": e.status_code,
                        }
                    )
                    return ExecutionResult.failure_result(
                        message=str(e),
                        error_code=e.error_code,
                        error_details=e.to_dict(),
                        http_status_code=e.status_code,
                        is_retryable=is_retryable,
                        retry_after_seconds=e.retry_after,
                        duration_ms=duration_ms,
                    )

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                last_error = e

                if attempt == self.retry_config.max_retries:
                    logger.exception(
                        "Unexpected error during action execution",
                        extra={
                            "platform": self.platform_name,
                            "action_type": action_type,
                            "entity_id": entity_id,
                            "attempt": attempt + 1,
                        }
                    )
                    return ExecutionResult.failure_result(
                        message=f"Unexpected error: {e}",
                        error_details={"exception": str(e), "type": type(e).__name__},
                        is_retryable=False,
                        duration_ms=duration_ms,
                    )

            # Calculate delay before retry
            retry_after = None
            if last_result and last_result.retry_after_seconds:
                retry_after = last_result.retry_after_seconds
            elif isinstance(last_error, PlatformAPIError) and last_error.retry_after:
                retry_after = last_error.retry_after

            delay = self.retry_config.calculate_delay(attempt, retry_after)

            logger.info(
                "Retrying action after delay",
                extra={
                    "platform": self.platform_name,
                    "action_type": action_type,
                    "entity_id": entity_id,
                    "attempt": attempt + 1,
                    "next_attempt": attempt + 2,
                    "delay_seconds": delay,
                }
            )

            await asyncio.sleep(delay)

        # Should not reach here, but return failure just in case
        return ExecutionResult.failure_result(
            message="Max retries exceeded",
            is_retryable=False,
        )

    async def capture_before_state(
        self,
        entity_id: str,
        entity_type: str,
    ) -> StateCapture:
        """
        Capture entity state before execution.

        Wrapper around get_entity_state for semantic clarity.

        Args:
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity

        Returns:
            StateCapture with current state
        """
        return await self.get_entity_state(entity_id, entity_type)

    async def capture_after_state(
        self,
        entity_id: str,
        entity_type: str,
    ) -> StateCapture:
        """
        Capture entity state after execution.

        Wrapper around get_entity_state for semantic clarity.

        Args:
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity

        Returns:
            StateCapture with current state
        """
        return await self.get_entity_state(entity_id, entity_type)

    def generate_rollback_instructions(
        self,
        action_type: str,
        before_state: StateCapture,
        entity_id: str,
        entity_type: str,
    ) -> dict:
        """
        Generate complete rollback instructions.

        Args:
            action_type: Type of action that was executed
            before_state: Entity state before execution
            entity_id: Platform-specific entity identifier
            entity_type: Type of entity

        Returns:
            Dictionary with rollback instructions
        """
        rollback_params = self.generate_rollback_params(action_type, before_state.state)

        return {
            "platform": self.platform_name,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "action_type": self._get_reverse_action_type(action_type),
            "params": rollback_params,
            "original_state": before_state.state,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "valid_until": None,  # Could add expiry logic
        }

    def _get_reverse_action_type(self, action_type: str) -> str:
        """
        Get the reverse action type for rollback.

        Override in subclass if platform has specific reverse action types.

        Args:
            action_type: Original action type

        Returns:
            Reverse action type for rollback
        """
        # Default mapping
        reverse_map = {
            "pause_campaign": "resume_campaign",
            "resume_campaign": "pause_campaign",
            "adjust_budget": "adjust_budget",  # Uses original value
            "adjust_bid": "adjust_bid",  # Uses original value
            "update_targeting": "update_targeting",
            "update_schedule": "update_schedule",
        }
        return reverse_map.get(action_type, action_type)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def generate_idempotency_key(
        tenant_id: str,
        action_id: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Generate a deterministic idempotency key.

        The key is based on tenant, action ID, and a 1-hour time bucket
        to allow retries within the same hour.

        Args:
            tenant_id: Tenant identifier
            action_id: Action identifier
            timestamp: Optional timestamp (defaults to now)

        Returns:
            32-character hex string
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Time bucket = floor(timestamp / 1 hour)
        time_bucket = int(timestamp.timestamp() // 3600)
        content = f"{tenant_id}:{action_id}:{time_bucket}"

        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _log_request(
        self,
        method: str,
        url: str,
        payload: Optional[dict] = None,
    ) -> dict:
        """
        Create a log entry for an API request.

        Args:
            method: HTTP method
            url: Request URL
            payload: Request payload (will be sanitized)

        Returns:
            Dictionary for logging
        """
        self._request_count += 1
        self._last_request_time = time.time()

        return {
            "method": method,
            "url": url,
            "payload": self._sanitize_payload(payload) if payload else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_number": self._request_count,
        }

    def _sanitize_payload(self, payload: dict) -> dict:
        """
        Remove sensitive data from payload for logging.

        Override in subclass if platform has specific sensitive fields.

        Args:
            payload: Original payload

        Returns:
            Sanitized payload safe for logging
        """
        sensitive_keys = {"access_token", "api_key", "secret", "password", "token"}
        sanitized = {}

        for key, value in payload.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_payload(value)
            else:
                sanitized[key] = value

        return sanitized
