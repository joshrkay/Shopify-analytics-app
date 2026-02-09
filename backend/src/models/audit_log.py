"""Canonical audit log model alias."""

import uuid

from src.platform.audit import AuditLog

def generate_correlation_id() -> str:
    """Generate a correlation ID for audit events."""
    return str(uuid.uuid4())


__all__ = ["AuditLog", "generate_correlation_id"]
