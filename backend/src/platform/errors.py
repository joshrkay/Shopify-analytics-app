"""Application error classes with consistent API response format. Stack traces are never returned to clients."""

import logging
import re
import uuid
from typing import Any, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AppError(Exception):
    """
    Base application error with consistent error shape.

    All custom errors should inherit from this class.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        """Convert to API error response format."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(AppError):
    """Validation error (400)."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class AuthenticationError(AppError):
    """Authentication failure (401)."""

    def __init__(self, message: str = "Authentication required", details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="AUTHENTICATION_ERROR",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class PaymentRequiredError(AppError):
    """Feature requires payment (402)."""

    def __init__(self, message: str = "This feature requires a paid plan", details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="PAYMENT_REQUIRED",
            message=message,
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details=details,
        )


class PermissionDeniedError(AppError):
    """Permission denied (403)."""

    def __init__(self, message: str = "Permission denied", details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="PERMISSION_DENIED",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class TenantIsolationError(AppError):
    """Cross-tenant access attempt (403) - CRITICAL SECURITY ERROR."""

    def __init__(self, message: str = "Access denied"):
        # SECURITY: Never expose details about tenant isolation violations to clients
        # Always use generic message regardless of what was passed in
        super().__init__(
            code="ACCESS_DENIED",
            message="Access denied",  # Always use generic message
            status_code=status.HTTP_403_FORBIDDEN,
            details={},
        )


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, resource: str, identifier: Optional[str] = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(AppError):
    """Resource conflict (409)."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class RateLimitError(AppError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ServiceUnavailableError(AppError):
    """Service unavailable (503)."""

    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class FeatureDisabledError(AppError):
    """Feature is disabled via feature flag (503)."""

    def __init__(self, feature: str):
        super().__init__(
            code="FEATURE_DISABLED",
            message=f"Feature '{feature}' is currently disabled",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing."""
    return str(uuid.uuid4())


_CORR_ID_SAFE = re.compile(r"[^a-zA-Z0-9_\-]")
_CORR_ID_MAX_LEN = 64


def _sanitize_correlation_id(raw: str) -> str:
    """
    Strip any character that is not alphanumeric, dash, or underscore, then
    truncate to 64 chars.

    Client-supplied X-Correlation-ID values must be sanitised before they reach
    log records or response headers; unvalidated pass-through enables header
    injection and log-forging attacks.
    """
    sanitized = _CORR_ID_SAFE.sub("", raw)[:_CORR_ID_MAX_LEN]
    # If sanitisation ate the whole string, generate a safe replacement.
    return sanitized if sanitized else generate_correlation_id()


def get_correlation_id(request: Request) -> str:
    """Get correlation ID from request headers (sanitised) or generate a fresh one."""
    raw = request.headers.get("X-Correlation-ID")
    if raw:
        return _sanitize_correlation_id(raw)

    if hasattr(request.state, "correlation_id"):
        return request.state.correlation_id

    return generate_correlation_id()


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that catches all exceptions and returns consistent error responses.

    IMPORTANT: Stack traces are NEVER returned to clients.
    """

    async def dispatch(self, request: Request, call_next):
        # Generate or extract correlation ID
        correlation_id = get_correlation_id(request)
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            return response

        except AppError as e:
            # Log with correlation ID
            logger.warning(
                "Application error",
                extra={
                    "correlation_id": correlation_id,
                    "error_code": e.code,
                    "status_code": e.status_code,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            return JSONResponse(
                status_code=e.status_code,
                content=e.to_dict(),
                headers={"X-Correlation-ID": correlation_id},
            )

        except HTTPException as e:
            # Convert FastAPI HTTPException to standard format
            logger.warning(
                "HTTP exception",
                extra={
                    "correlation_id": correlation_id,
                    "status_code": e.status_code,
                    "detail": e.detail,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": "HTTP_ERROR",
                        "message": str(e.detail),
                        "details": {},
                    }
                },
                headers={"X-Correlation-ID": correlation_id},
            )

        except Exception as e:
            # Log full exception for debugging (server-side only)
            logger.exception(
                "Unhandled exception",
                extra={
                    "correlation_id": correlation_id,
                    "error_type": type(e).__name__,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            # Return generic error to client (no stack trace!)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "details": {"correlation_id": correlation_id},
                    }
                },
                headers={"X-Correlation-ID": correlation_id},
            )
