"""
Standardized error response helpers for API routes.

Ensures consistent error response format across all endpoints.
The frontend handleResponse<T>() expects errors to have a 'detail' field
with either a string or an object containing 'message' and optional 'error_code'.
"""

from fastapi import HTTPException


def api_error(
    status_code: int,
    message: str,
    error_code: str | None = None,
) -> HTTPException:
    """
    Create a standardized API error response.

    Args:
        status_code: HTTP status code
        message: User-facing error message (must not contain internal details)
        error_code: Machine-readable error code (e.g., 'TENANT_NOT_PROVISIONED')

    Returns:
        HTTPException with consistent detail format
    """
    detail: dict | str
    if error_code:
        detail = {"message": message, "error_code": error_code}
    else:
        detail = message
    return HTTPException(status_code=status_code, detail=detail)


def internal_error(message: str = "Internal server error") -> HTTPException:
    """Create a 500 error with a generic user-facing message."""
    return api_error(500, message)
