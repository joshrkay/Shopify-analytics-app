"""
Audit logging for AI Growth Analytics.

CRITICAL SECURITY REQUIREMENTS:
- Audit logs MUST be append-only (no UPDATE/DELETE)
- All sensitive actions MUST write an audit event
- Events must include: tenant_id, user_id, action, timestamp, IP, user_agent, metadata
- PII fields MUST be redacted before persistence
- Failed logging attempts MUST fall back to secondary logger

Sensitive actions that require audit logging:
- Auth/session events
- Billing changes
- Connector changes (store add/remove)
- AI key/model changes
- Data exports
- Automation approvals/executions
- Feature flag changes
- Permission/role changes
- Admin actions

Story 10.1 - Audit Event Schema & Logging Foundation
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, FrozenSet

from dataclasses import dataclass, field, asdict

from fastapi import Request
from sqlalchemy import Column, String, DateTime, Text, Index, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.db_base import Base

logger = logging.getLogger(__name__)
fallback_logger = logging.getLogger("audit.fallback")


class AuditAction(str, Enum):
    """
    Enumeration of all auditable actions.

    Add new actions here as features are developed.
    """
    # Auth events
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"
    AUTH_PASSWORD_CHANGE = "auth.password_change"
    AUTH_MFA_ENABLED = "auth.mfa_enabled"
    AUTH_MFA_DISABLED = "auth.mfa_disabled"

    # Billing events
    BILLING_PLAN_CHANGED = "billing.plan_changed"
    BILLING_SUBSCRIPTION_CREATED = "billing.subscription_created"
    BILLING_SUBSCRIPTION_CANCELLED = "billing.subscription_cancelled"
    BILLING_PAYMENT_FAILED = "billing.payment_failed"
    BILLING_PAYMENT_SUCCESS = "billing.payment_success"

    # Store/connector events
    STORE_CONNECTED = "store.connected"
    STORE_DISCONNECTED = "store.disconnected"
    STORE_UPDATED = "store.updated"
    STORE_SYNC_STARTED = "store.sync_started"
    STORE_SYNC_COMPLETED = "store.sync_completed"
    STORE_SYNC_FAILED = "store.sync_failed"

    # AI events
    AI_KEY_CREATED = "ai.key_created"
    AI_KEY_ROTATED = "ai.key_rotated"
    AI_KEY_DELETED = "ai.key_deleted"
    AI_MODEL_CHANGED = "ai.model_changed"
    AI_ACTION_REQUESTED = "ai.action_requested"
    AI_ACTION_EXECUTED = "ai.action_executed"
    AI_ACTION_REJECTED = "ai.action_rejected"

    # Data export events
    EXPORT_REQUESTED = "export.requested"
    EXPORT_COMPLETED = "export.completed"
    EXPORT_FAILED = "export.failed"
    EXPORT_DOWNLOADED = "export.downloaded"

    # Automation events
    AUTOMATION_CREATED = "automation.created"
    AUTOMATION_UPDATED = "automation.updated"
    AUTOMATION_DELETED = "automation.deleted"
    AUTOMATION_APPROVED = "automation.approved"
    AUTOMATION_REJECTED = "automation.rejected"
    AUTOMATION_EXECUTED = "automation.executed"
    AUTOMATION_FAILED = "automation.failed"

    # Feature flag events
    FEATURE_FLAG_ENABLED = "feature_flag.enabled"
    FEATURE_FLAG_DISABLED = "feature_flag.disabled"
    FEATURE_FLAG_OVERRIDE = "feature_flag.override"

    # Team/permission events
    TEAM_MEMBER_INVITED = "team.member_invited"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    TEAM_ROLE_CHANGED = "team.role_changed"

    # Settings events
    SETTINGS_UPDATED = "settings.updated"

    # Admin events
    ADMIN_PLAN_CREATED = "admin.plan_created"
    ADMIN_PLAN_UPDATED = "admin.plan_updated"
    ADMIN_PLAN_DELETED = "admin.plan_deleted"
    ADMIN_CONFIG_CHANGED = "admin.config_changed"

    # Backfill events
    BACKFILL_STARTED = "backfill.started"
    BACKFILL_COMPLETED = "backfill.completed"
    BACKFILL_FAILED = "backfill.failed"
    
    # Entitlement events
    ENTITLEMENT_DENIED = "entitlement.denied"
    ENTITLEMENT_ALLOWED = "entitlement.allowed"
    
    # Job entitlement events
    JOB_SKIPPED_DUE_TO_ENTITLEMENT = "job.skipped_due_to_entitlement"
    JOB_ALLOWED = "job.allowed"

    # AI Safety events (Story 8.6)
    AI_RATE_LIMIT_HIT = "ai.safety.rate_limit_hit"
    AI_COOLDOWN_ENFORCED = "ai.safety.cooldown_enforced"
    AI_ACTION_BLOCKED = "ai.safety.action_blocked"
    AI_ACTION_SUPPRESSED = "ai.safety.action_suppressed"
    AI_KILL_SWITCH_ACTIVATED = "ai.safety.kill_switch_activated"

    # AI Lifecycle events (Story 8.7)
    AI_INSIGHT_GENERATED = "ai.insight.generated"
    AI_RECOMMENDATION_CREATED = "ai.recommendation.created"
    AI_ACTION_CREATED = "ai.action.created"
    AI_ACTION_APPROVED = "ai.action.approved"
    AI_ACTION_EXECUTION_STARTED = "ai.action.execution_started"
    AI_ACTION_EXECUTION_SUCCEEDED = "ai.action.execution_succeeded"
    AI_ACTION_EXECUTION_FAILED = "ai.action.execution_failed"
    AI_ROLLBACK_REQUESTED = "ai.rollback.requested"
    AI_ROLLBACK_SUCCEEDED = "ai.rollback.succeeded"
    AI_ROLLBACK_FAILED = "ai.rollback.failed"

    # Data Access events (Story 10.1)
    DATA_ACCESSED = "data.accessed"
    DATA_EXPORTED = "data.exported"
    DATA_DELETED = "data.deleted"

    # Governance events (Story 10.1)
    GOVERNANCE_CONFIG_CHANGED = "governance.config_changed"
    GOVERNANCE_RETENTION_APPLIED = "governance.retention_applied"


class AuditOutcome(str, Enum):
    """Outcome of the audited action."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class PIIRedactor:
    """
    Redacts PII fields from audit metadata before persistence.

    Redacted fields are replaced with "[REDACTED]" to maintain
    structure while removing sensitive data.

    Story 10.1 - Audit Event Schema & Logging Foundation
    """

    REDACTED_FIELDS: FrozenSet[str] = frozenset({
        # Authentication
        "email",
        "phone",
        "phone_number",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "api_secret",
        "password",
        "secret",
        "credential",
        "credentials",
        # Personal identifiers
        "ssn",
        "social_security",
        "tax_id",
        "national_id",
        # Financial
        "credit_card",
        "card_number",
        "cvv",
        "bank_account",
        "routing_number",
        # Address components
        "street_address",
        "address_line_1",
        "address_line_2",
    })

    REDACTION_MARKER = "[REDACTED]"

    @classmethod
    def redact(cls, data: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively redact PII from a dictionary.

        Args:
            data: Dictionary potentially containing PII

        Returns:
            New dictionary with PII fields redacted
        """
        if not isinstance(data, dict):
            return data
        return cls._redact_dict(data)

    @classmethod
    def _redact_dict(cls, d: dict[str, Any]) -> dict[str, Any]:
        """Recursively process a dictionary."""
        result = {}
        for key, value in d.items():
            lower_key = key.lower()
            if lower_key in cls.REDACTED_FIELDS:
                result[key] = cls._redact_value(lower_key, value)
            elif isinstance(value, dict):
                result[key] = cls._redact_dict(value)
            elif isinstance(value, list):
                result[key] = cls._redact_list(value)
            else:
                result[key] = value
        return result

    @classmethod
    def _redact_value(cls, key: str, value: Any) -> str:
        """Redact a single value, with partial redaction for some fields."""
        if value is None:
            return cls.REDACTION_MARKER
        # Partial redaction for email (show domain)
        if key == "email" and isinstance(value, str) and "@" in value:
            try:
                return f"***@{value.split('@')[1]}"
            except (IndexError, AttributeError):
                return cls.REDACTION_MARKER
        # Partial redaction for phone (show last 4)
        if key in ("phone", "phone_number") and value:
            str_val = str(value)
            if len(str_val) >= 4:
                return f"***{str_val[-4:]}"
        return cls.REDACTION_MARKER

    @classmethod
    def _redact_list(cls, lst: list[Any]) -> list[Any]:
        """Process a list, redacting any nested dicts."""
        result = []
        for item in lst:
            if isinstance(item, dict):
                result.append(cls._redact_dict(item))
            elif isinstance(item, list):
                result.append(cls._redact_list(item))
            else:
                result.append(item)
        return result


class AuditLog(Base):
    """
    Audit log database model.

    CRITICAL: This table is append-only. No UPDATE or DELETE operations are allowed.
    Immutability is enforced via database trigger.

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=True, index=True)  # NULL for system events
    action = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(Text, nullable=True)
    resource_type = Column(String(100), nullable=True, index=True)
    resource_id = Column(String(255), nullable=True, index=True)
    event_metadata = Column(JSONB, nullable=False, default=dict)
    correlation_id = Column(String(36), nullable=False, index=True)
    # New fields for Story 10.1
    source = Column(String(50), nullable=False, default="api")  # api, worker, system, webhook
    outcome = Column(String(20), nullable=False, default="success")  # success, failure, denied
    error_code = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_tenant_timestamp", "tenant_id", "timestamp"),
        Index("ix_audit_logs_tenant_action", "tenant_id", "action"),
        Index("ix_audit_logs_tenant_user", "tenant_id", "user_id"),
        Index("ix_audit_logs_correlation", "correlation_id"),
    )


@dataclass
class AuditEvent:
    """
    Immutable audit event data structure.

    Use this to construct audit events before writing to the database.
    PII in metadata is automatically redacted before persistence.

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    tenant_id: str
    action: AuditAction
    user_id: Optional[str] = None  # NULL for system events
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "api"  # api, worker, system, webhook
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    error_code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion with PII redaction."""
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action": self.action.value if isinstance(self.action, AuditAction) else self.action,
            "timestamp": self.timestamp,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "event_metadata": PIIRedactor.redact(self.metadata),
            "correlation_id": self.correlation_id,
            "source": self.source,
            "outcome": self.outcome.value if isinstance(self.outcome, AuditOutcome) else self.outcome,
            "error_code": self.error_code,
        }


def extract_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """
    Extract client IP and user agent from request.

    Handles X-Forwarded-For for proxied requests.
    """
    # Get IP address (handle proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (client IP)
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    # Get user agent
    user_agent = request.headers.get("User-Agent")

    return ip_address, user_agent


def get_correlation_id(request: Request) -> Optional[str]:
    """Get correlation ID from request state or headers."""
    if hasattr(request.state, "correlation_id"):
        return request.state.correlation_id
    return request.headers.get("X-Correlation-ID")


def write_audit_log_sync(
    db: Session,
    event: AuditEvent,
) -> Optional[AuditLog]:
    """
    Write an audit event to the database (synchronous version).

    CRITICAL: This is an append-only operation. Events cannot be modified or deleted.
    On failure, writes to fallback logger and returns None (never crashes request flow).

    Args:
        db: SQLAlchemy Session
        event: The audit event to write

    Returns:
        The created AuditLog record, or None if fallback was used

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    audit_id = str(uuid.uuid4())
    try:
        audit_log = AuditLog(
            id=audit_id,
            **event.to_dict()
        )
        db.add(audit_log)
        db.commit()

        logger.info(
            "Audit event recorded",
            extra={
                "audit_id": audit_log.id,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "action": event.action.value if isinstance(event.action, AuditAction) else event.action,
                "correlation_id": event.correlation_id,
                "source": event.source,
                "outcome": event.outcome.value if isinstance(event.outcome, AuditOutcome) else event.outcome,
            }
        )
        return audit_log

    except Exception as e:
        # Rollback and fall back to stdout logging - NEVER crash
        try:
            db.rollback()
        except Exception:
            pass

        _write_fallback_log(event, audit_id, str(e))
        return None


def _write_fallback_log(event: AuditEvent, audit_id: str, error_reason: str) -> None:
    """Write audit event to fallback logger when primary DB fails."""
    fallback_entry = {
        "event_id": audit_id,
        "tenant_id": event.tenant_id,
        "user_id": event.user_id,
        "action": event.action.value if isinstance(event.action, AuditAction) else event.action,
        "timestamp": event.timestamp.isoformat(),
        "correlation_id": event.correlation_id,
        "source": event.source,
        "outcome": event.outcome.value if isinstance(event.outcome, AuditOutcome) else event.outcome,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "metadata": PIIRedactor.redact(event.metadata),
        "ip_address": event.ip_address,
        "fallback_reason": error_reason,
    }
    fallback_logger.error(
        "Audit log fallback",
        extra={"audit_entry": json.dumps(fallback_entry)},
    )


async def write_audit_log(
    db: Session,
    event: AuditEvent,
) -> Optional[AuditLog]:
    """
    Write an audit event to the database (async-compatible wrapper).

    CRITICAL: This is an append-only operation. Events cannot be modified or deleted.
    On failure, writes to fallback logger and returns None (never crashes request flow).

    Args:
        db: Database session (sync or async)
        event: The audit event to write

    Returns:
        The created AuditLog record, or None if fallback was used

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    # Use sync version - works with both sync and async sessions
    return write_audit_log_sync(db, event)


def log_audit_event_sync(
    db: Session,
    request: Request,
    action: AuditAction,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    error_code: Optional[str] = None,
) -> str:
    """
    Log an audit event from a request context (synchronous version).

    Automatically extracts tenant context, IP, user agent, and correlation ID.
    Returns the correlation_id for request tracing.

    Args:
        db: Database session
        request: FastAPI request object
        action: The audit action
        resource_type: Type of resource being acted upon (e.g., "store", "plan")
        resource_id: ID of the resource
        metadata: Additional metadata to include
        outcome: Outcome of the action (success, failure, denied)
        error_code: Error code if outcome is failure

    Returns:
        The correlation_id for the logged event

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    from src.platform.tenant_context import get_tenant_context

    tenant_context = get_tenant_context(request)
    ip_address, user_agent = extract_client_info(request)
    correlation_id = get_correlation_id(request) or str(uuid.uuid4())

    event = AuditEvent(
        tenant_id=tenant_context.tenant_id,
        action=action,
        user_id=tenant_context.user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
        correlation_id=correlation_id,
        source="api",
        outcome=outcome,
        error_code=error_code,
    )

    write_audit_log_sync(db, event)
    return correlation_id


async def log_audit_event(
    db: Session,
    request: Request,
    action: AuditAction,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    error_code: Optional[str] = None,
) -> str:
    """
    Log an audit event from a request context (async-compatible).

    Automatically extracts tenant context, IP, user agent, and correlation ID.
    Returns the correlation_id for request tracing.

    Args:
        db: Database session
        request: FastAPI request object
        action: The audit action
        resource_type: Type of resource being acted upon (e.g., "store", "plan")
        resource_id: ID of the resource
        metadata: Additional metadata to include
        outcome: Outcome of the action (success, failure, denied)
        error_code: Error code if outcome is failure

    Returns:
        The correlation_id for the logged event

    Example:
        correlation_id = await log_audit_event(
            db=db,
            request=request,
            action=AuditAction.STORE_CONNECTED,
            resource_type="store",
            resource_id=store_id,
            metadata={"shop_domain": "example.myshopify.com"}
        )

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    return log_audit_event_sync(
        db=db,
        request=request,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        outcome=outcome,
        error_code=error_code,
    )


def log_system_audit_event_sync(
    db: Session,
    tenant_id: str,
    action: AuditAction,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    source: str = "system",
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    error_code: Optional[str] = None,
) -> str:
    """
    Log an audit event from a system context (synchronous version).

    Use this when there is no request context available.
    Returns the correlation_id for request tracing.

    Args:
        db: Database session
        tenant_id: The tenant ID
        action: The audit action
        resource_type: Type of resource being acted upon
        resource_id: ID of the resource
        metadata: Additional metadata to include
        correlation_id: Optional correlation ID for tracing
        source: Event source (system, worker, webhook)
        outcome: Outcome of the action
        error_code: Error code if outcome is failure

    Returns:
        The correlation_id for the logged event

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    correlation_id = correlation_id or str(uuid.uuid4())

    event = AuditEvent(
        tenant_id=tenant_id,
        action=action,
        user_id=None,  # System events have no user
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
        correlation_id=correlation_id,
        source=source,
        outcome=outcome,
        error_code=error_code,
    )

    write_audit_log_sync(db, event)
    return correlation_id


async def log_system_audit_event(
    db: Session,
    tenant_id: str,
    action: AuditAction,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    source: str = "system",
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    error_code: Optional[str] = None,
) -> str:
    """
    Log an audit event from a system context (async-compatible).

    Use this when there is no request context available.
    Returns the correlation_id for request tracing.

    Args:
        db: Database session
        tenant_id: The tenant ID
        action: The audit action
        resource_type: Type of resource being acted upon
        resource_id: ID of the resource
        metadata: Additional metadata to include
        correlation_id: Optional correlation ID for tracing
        source: Event source (system, worker, webhook)
        outcome: Outcome of the action
        error_code: Error code if outcome is failure

    Returns:
        The correlation_id for the logged event

    Story 10.1 - Audit Event Schema & Logging Foundation
    """
    return log_system_audit_event_sync(
        db=db,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        correlation_id=correlation_id,
        source=source,
        outcome=outcome,
        error_code=error_code,
    )


def create_audit_decorator(
    action: AuditAction,
    resource_type: Optional[str] = None,
    resource_id_param: Optional[str] = None,
):
    """
    Create a decorator that automatically logs audit events.

    Args:
        action: The audit action to log
        resource_type: Type of resource being acted upon
        resource_id_param: Name of the parameter that contains the resource ID

    Usage:
        @app.post("/api/stores/{store_id}/disconnect")
        @create_audit_decorator(AuditAction.STORE_DISCONNECTED, "store", "store_id")
        async def disconnect_store(request: Request, store_id: str, db: AsyncSession = Depends(get_db)):
            ...
    """
    def decorator(func):
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute the function first
            result = await func(*args, **kwargs)

            # Find request and db in kwargs
            request = kwargs.get("request")
            db = kwargs.get("db")

            if request and db:
                resource_id = kwargs.get(resource_id_param) if resource_id_param else None

                try:
                    await log_audit_event(
                        db=db,
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        resource_id=str(resource_id) if resource_id else None,
                    )
                except Exception as e:
                    # Don't fail the request if audit logging fails
                    # But do log the error for investigation
                    logger.error(
                        "Failed to write audit log",
                        extra={
                            "error": str(e),
                            "action": action.value,
                            "resource_type": resource_type,
                            "resource_id": str(resource_id) if resource_id else None,
                        }
                    )

            return result
        return wrapper
    return decorator
