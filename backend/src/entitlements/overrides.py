"""
Per-tenant entitlement overrides. Governance: Super Admin + Support only.
Every override requires feature_key, tenant_id, expiry (required), reason.
Full audit: created, updated, expired, removed.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from src.entitlements.models import OverrideEntry
from src.models.entitlement_override import EntitlementOverrideRow
from src.platform.audit import (
    AuditAction,
    AuditEvent,
    AuditOutcome,
    write_audit_log_sync,
)
from src.repositories import entitlement_override_repository as repo

logger = logging.getLogger(__name__)

# Role names that may create/update/delete overrides
ALLOWED_OVERRIDE_ROLES = frozenset({"super_admin", "support"})


def _get_db_session_sync():
    from src.database.session import get_db_session_sync as _get
    return _get()


def _emit_override_audit(
    tenant_id: str,
    action: AuditAction,
    user_id: str,
    feature_key: str,
    metadata: Optional[dict] = None,
) -> None:
    try:
        db_gen = _get_db_session_sync()
        db = next(db_gen)
        try:
            event = AuditEvent(
                tenant_id=tenant_id,
                action=action,
                user_id=user_id,
                resource_type="entitlement_override",
                resource_id=feature_key,
                metadata=metadata or {},
                source="api",
                outcome=AuditOutcome.SUCCESS,
            )
            write_audit_log_sync(db, event)
        finally:
            db.close()
    except Exception as e:
        logger.error("Audit log write failed for entitlement override", extra={"action": action.value, "error": str(e)})


def can_manage_overrides(roles: List[str]) -> bool:
    """True if user has Super Admin or Support role."""
    return any(r.lower() in ALLOWED_OVERRIDE_ROLES for r in roles)


def list_active_overrides(
    tenant_id: str, now: Optional[datetime] = None
) -> List[OverrideEntry]:
    """Non-expired overrides for tenant."""
    if now is None:
        now = datetime.now(timezone.utc)
    db_gen = _get_db_session_sync()
    db = next(db_gen)
    try:
        return repo.list_active_overrides_for_tenant(db, tenant_id, now)
    finally:
        db.close()


def create_override(
    tenant_id: str,
    feature_key: str,
    expires_at: datetime,
    reason: str,
    actor_id: str,
    actor_roles: List[str],
) -> EntitlementOverrideRow:
    """Create override. Raises if not allowed or expiry in past."""
    if not can_manage_overrides(actor_roles):
        raise PermissionError("Only Super Admin or Support can create overrides")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("Override expiry must be in the future")
    db_gen = _get_db_session_sync()
    db = next(db_gen)
    try:
        row = repo.create_override(
            db, tenant_id=tenant_id, feature_key=feature_key,
            expires_at=expires_at, reason=reason, actor_id=actor_id,
        )
        db.commit()
        _emit_override_audit(
            tenant_id, AuditAction.ENTITLEMENT_OVERRIDE_CREATED,
            actor_id, feature_key,
            metadata={"expires_at": expires_at.isoformat(), "reason": reason},
        )
        return row
    finally:
        db.close()


def update_override(
    tenant_id: str,
    feature_key: str,
    expires_at: datetime,
    reason: str,
    actor_id: str,
    actor_roles: List[str],
) -> Optional[EntitlementOverrideRow]:
    """Update existing override. Audit: entitlement.override.updated."""
    if not can_manage_overrides(actor_roles):
        raise PermissionError("Only Super Admin or Support can update overrides")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    db_gen = _get_db_session_sync()
    db = next(db_gen)
    try:
        row = repo.update_override(
            db, tenant_id=tenant_id, feature_key=feature_key,
            expires_at=expires_at, reason=reason, actor_id=actor_id,
        )
        if row:
            db.commit()
            _emit_override_audit(
                tenant_id, AuditAction.ENTITLEMENT_OVERRIDE_UPDATED,
                actor_id, feature_key,
                metadata={"expires_at": expires_at.isoformat(), "reason": reason},
            )
        return row
    finally:
        db.close()


def delete_override(
    tenant_id: str, feature_key: str, actor_id: str, actor_roles: List[str]
) -> bool:
    """Remove override. Audit: entitlement.override.removed."""
    if not can_manage_overrides(actor_roles):
        raise PermissionError("Only Super Admin or Support can remove overrides")
    db_gen = _get_db_session_sync()
    db = next(db_gen)
    try:
        deleted = repo.delete_override(db, tenant_id=tenant_id, feature_key=feature_key)
        if deleted:
            db.commit()
            _emit_override_audit(
                tenant_id, AuditAction.ENTITLEMENT_OVERRIDE_REMOVED,
                actor_id, feature_key,
            )
        return deleted
    finally:
        db.close()


def remove_expired_overrides(now: Optional[datetime] = None) -> int:
    """
    Delete overrides with expires_at <= now. Emit entitlement.override.expired audit per row.
    Returns count removed. Used by reconciliation job.
    """
    _, count = remove_expired_overrides_and_return_tenants(now=now)
    return count


def remove_expired_overrides_and_return_tenants(now: Optional[datetime] = None) -> tuple[List[str], int]:
    """
    Delete expired overrides, emit audit, return (affected_tenant_ids, count_removed).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    db_gen = _get_db_session_sync()
    db = next(db_gen)
    removed = 0
    affected_tenants: List[str] = []
    try:
        for row in repo.list_expired(db, now):
            repo.delete_override(db, tenant_id=row.tenant_id, feature_key=row.feature_key)
            _emit_override_audit(
                row.tenant_id, AuditAction.ENTITLEMENT_OVERRIDE_EXPIRED,
                row.actor_id, row.feature_key,
                metadata={"expires_at": row.expires_at.isoformat()},
            )
            removed += 1
            if row.tenant_id not in affected_tenants:
                affected_tenants.append(row.tenant_id)
        if removed:
            db.commit()
    finally:
        db.close()
    return (affected_tenants, removed)
