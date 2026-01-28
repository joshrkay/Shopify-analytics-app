"""
Credential redaction and audit logging utilities.

SECURITY REQUIREMENTS:
- Tokens NEVER appear in logs (access_token, refresh_token)
- ALLOWED in logs per PII policy: account_name, connector_name
- All credential operations logged for audit trail

Audit Events:
- credential.stored
- credential.refreshed
- credential.revoked
- credential.purged

Usage:
    from src.credentials.redaction import CredentialAuditLogger, AuditEventType
    
    audit = CredentialAuditLogger(tenant_id)
    audit.log(
        event_type=AuditEventType.CREDENTIAL_STORED,
        credential_id=cred.id,
        provider="shopify",
        account_name="My Store",
    )
"""

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Dict

from src.platform.secrets import (
    redact_secrets,
    is_secret_key,
    REDACTED_VALUE,
    SECRET_PATTERNS,
    SECRET_VALUE_PATTERNS,
)

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Credential audit event types."""
    CREDENTIAL_STORED = "credential.stored"
    CREDENTIAL_REFRESHED = "credential.refreshed"
    CREDENTIAL_REVOKED = "credential.revoked"
    CREDENTIAL_PURGED = "credential.purged"
    CREDENTIAL_ACCESSED = "credential.accessed"
    CREDENTIAL_ERROR = "credential.error"


# Additional patterns specific to OAuth credentials
CREDENTIAL_SECRET_PATTERNS = [
    re.compile(r"(oauth[_-]?token)", re.IGNORECASE),
    re.compile(r"(bearer[_-]?token)", re.IGNORECASE),
    re.compile(r"(shpat_[a-fA-F0-9]+)"),  # Shopify access tokens
    re.compile(r"(shpss_[a-zA-Z0-9]+)"),  # Shopify shared secrets
    re.compile(r"(ya29\.[a-zA-Z0-9_-]+)"),  # Google OAuth tokens
    re.compile(r"(EAA[a-zA-Z0-9]+)"),  # Facebook tokens
]


def is_credential_secret_key(key: str) -> bool:
    """
    Check if a key name indicates a credential secret.

    Extends platform-level secret detection with credential-specific patterns.

    Args:
        key: The key name to check

    Returns:
        True if the key likely contains a secret
    """
    # Use platform-level detection first
    if is_secret_key(key):
        return True

    # Additional credential-specific patterns
    key_lower = key.lower()
    credential_patterns = [
        "token", "secret", "credential", "auth", "bearer",
        "oauth", "api_key", "apikey", "password"
    ]
    return any(pattern in key_lower for pattern in credential_patterns)


def redact_credential_value(value: Any) -> Any:
    """
    Redact secret patterns from a credential value.

    Args:
        value: The value to redact

    Returns:
        Redacted value
    """
    if not isinstance(value, str):
        return value

    result = value

    # Apply credential-specific patterns
    for pattern in CREDENTIAL_SECRET_PATTERNS:
        result = pattern.sub(REDACTED_VALUE, result)

    # Apply platform-level patterns
    for pattern in SECRET_VALUE_PATTERNS:
        result = pattern.sub(REDACTED_VALUE, result)

    return result


def redact_credential_data(data: Any, _depth: int = 0) -> Any:
    """
    Recursively redact credential secrets from a data structure.

    Extends platform-level redaction with credential-specific patterns.

    SECURITY:
    - Always use this before logging credential-related data
    - account_name and connector_name are NOT redacted (allowed per PII policy)

    Args:
        data: Dictionary, list, or other data structure

    Returns:
        Copy of data with secrets redacted

    Usage:
        safe_data = redact_credential_data({"access_token": "shpat_xxx", "name": "test"})
        logger.info("Credential data", extra=safe_data)
    """
    # Prevent infinite recursion
    if _depth > 10:
        return data

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Check if key indicates a secret
            if is_credential_secret_key(key):
                result[key] = REDACTED_VALUE
            # Allow account_name and connector_name per PII policy
            elif key in ("account_name", "connector_name", "shop_name", "store_name"):
                result[key] = value
            else:
                result[key] = redact_credential_data(value, _depth + 1)
        return result

    if isinstance(data, list):
        return [redact_credential_data(item, _depth + 1) for item in data]

    if isinstance(data, str):
        return redact_credential_value(data)

    return data


class CredentialAuditLogger:
    """
    Structured audit logger for credential operations.

    SECURITY:
    - Tokens are NEVER logged
    - account_name and connector_name ARE logged (allowed per PII policy)
    - All operations are logged for audit compliance
    """

    def __init__(self, tenant_id: str):
        """
        Initialize audit logger.

        Args:
            tenant_id: Tenant ID for context
        """
        self.tenant_id = tenant_id
        self.logger = logging.getLogger("credentials.audit")

    def log(
        self,
        event_type: AuditEventType,
        credential_id: str,
        provider: str,
        account_name: Optional[str] = None,
        connector_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an audit event.

        SECURITY:
        - metadata is automatically redacted
        - Tokens must NEVER be passed in metadata

        Args:
            event_type: Type of audit event
            credential_id: Credential ID
            provider: OAuth provider name
            account_name: Account display name (allowed in logs)
            connector_name: Connector display name (allowed in logs)
            metadata: Additional context (will be redacted)
        """
        # Redact any secrets that might be in metadata
        safe_metadata = redact_credential_data(metadata) if metadata else {}

        audit_record = {
            "event_type": event_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": self.tenant_id,
            "credential_id": credential_id,
            "provider": provider,
            "account_name": account_name,  # Allowed per PII policy
            "connector_name": connector_name,  # Allowed per PII policy
            **safe_metadata,
        }

        self.logger.info(
            f"Credential audit: {event_type.value}",
            extra=audit_record
        )

    def log_error(
        self,
        credential_id: str,
        provider: str,
        error: str,
        account_name: Optional[str] = None,
        connector_name: Optional[str] = None,
    ) -> None:
        """
        Log a credential error.

        Args:
            credential_id: Credential ID
            provider: OAuth provider name
            error: Error message (will be redacted)
            account_name: Account display name (allowed in logs)
            connector_name: Connector display name (allowed in logs)
        """
        # Redact any tokens that might be in error message
        safe_error = redact_credential_value(error)

        self.log(
            event_type=AuditEventType.CREDENTIAL_ERROR,
            credential_id=credential_id,
            provider=provider,
            account_name=account_name,
            connector_name=connector_name,
            metadata={"error": safe_error},
        )


class CredentialLoggingFilter(logging.Filter):
    """
    Logging filter that redacts credential secrets from log records.

    Add this filter to loggers handling credential operations to ensure
    tokens never appear in logs.

    Usage:
        logger.addFilter(CredentialLoggingFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the message
        if isinstance(record.msg, str):
            record.msg = redact_credential_value(record.msg)

        # Redact args
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_credential_data(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_credential_value(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        # Redact extra fields
        if hasattr(record, "__dict__"):
            for key in list(record.__dict__.keys()):
                if is_credential_secret_key(key):
                    setattr(record, key, REDACTED_VALUE)
                elif isinstance(getattr(record, key), str):
                    setattr(record, key, redact_credential_value(getattr(record, key)))

        return True


def setup_credential_logging() -> None:
    """
    Configure credential-safe logging.

    Call this during application startup to ensure all credential
    loggers have the redaction filter applied.
    """
    filter = CredentialLoggingFilter()

    # Apply to credential-specific loggers
    credential_loggers = [
        "credentials",
        "credentials.store",
        "credentials.refresh",
        "credentials.audit",
        "src.credentials",
    ]

    for logger_name in credential_loggers:
        log = logging.getLogger(logger_name)
        log.addFilter(filter)

    logger.info("Credential logging configured with redaction filter")
