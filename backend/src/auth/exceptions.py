"""
Authentication exceptions.

Shared exception types used across auth modules (middleware, tests, etc.).
"""


class ClerkVerificationError(Exception):
    """Exception raised when Clerk JWT verification fails."""

    def __init__(self, message: str, error_code: str = "verification_failed"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
