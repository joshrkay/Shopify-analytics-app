"""Server-side RBAC enforcement. UI gating is UX only — all checks must go through this module."""

import logging
from functools import wraps
from typing import Callable

from fastapi import Request, HTTPException, status

from src.platform.tenant_context import TenantContext, get_tenant_context
from src.platform.errors import PermissionDeniedError
from src.constants.permissions import (
    Permission,
    Role,
    roles_have_permission,
    get_permissions_for_roles,
)

logger = logging.getLogger(__name__)


class RBACError(PermissionDeniedError):
    """RBAC-specific permission denied error."""

    def __init__(self, required: str, user_roles: list[str]):
        super().__init__(
            message="You do not have permission to perform this action",
            details={"required": required},
        )
        # Log detailed info server-side but don't expose to client
        logger.warning(
            "RBAC check failed",
            extra={
                "required": required,
                "user_roles": user_roles,
            }
        )


def _get_request_from_args(args, kwargs) -> Request:
    """Extract Request object from function arguments."""
    for arg in args:
        if isinstance(arg, Request):
            return arg
    if "request" in kwargs:
        return kwargs["request"]
    raise ValueError("Request object not found in function arguments")


def has_permission(tenant_context: TenantContext, permission: Permission) -> bool:
    """Return True if the context holds the given permission. Prefers resolved_permissions; falls back to ROLE_PERMISSIONS matrix."""
    resolved = getattr(tenant_context, "resolved_permissions", None)
    if resolved is not None:
        return permission.value in resolved
    return roles_have_permission(tenant_context.roles, permission)


def has_any_permission(tenant_context: TenantContext, permissions: list[Permission]) -> bool:
    """Return True if the context holds at least one of the given permissions."""
    resolved = getattr(tenant_context, "resolved_permissions", None)
    if resolved is not None:
        return any(p.value in resolved for p in permissions)
    user_permissions = get_permissions_for_roles(tenant_context.roles)
    return bool(user_permissions.intersection(permissions))


def has_all_permissions(tenant_context: TenantContext, permissions: list[Permission]) -> bool:
    """Return True if the context holds every one of the given permissions."""
    resolved = getattr(tenant_context, "resolved_permissions", None)
    if resolved is not None:
        return all(p.value in resolved for p in permissions)
    user_permissions = get_permissions_for_roles(tenant_context.roles)
    return all(p in user_permissions for p in permissions)


def has_role(tenant_context: TenantContext, role: Role) -> bool:
    """Return True if the context carries the given role."""
    return role.value in [r.lower() for r in tenant_context.roles]


def _try_emit_rbac_denied(
    tenant_id: str,
    user_id: str,
    permission_str: str,
    endpoint: str,
    method: str,
    roles: list[str],
) -> None:
    """Emit rbac.denied audit event, never crashing the caller."""
    try:
        from src.database.session import get_db_session_sync
        from src.services.audit_logger import emit_rbac_denied

        session = next(get_db_session_sync())
        try:
            emit_rbac_denied(
                db=session,
                tenant_id=tenant_id,
                user_id=user_id,
                permission=permission_str,
                endpoint=endpoint,
                method=method,
                roles=roles,
            )
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
    except Exception:
        logger.debug(
            "rbac.emit_audit_failed",
            extra={"user_id": user_id, "permission": permission_str},
            exc_info=True,
        )


def _enforce_permission(
    *,
    allowed: bool,
    permission_str: str,
    tenant_context: TenantContext,
    request: Request,
) -> None:
    """
    Shared denial path for all RBAC decorators and programmatic checks.

    Permission denials are normal operations (hiding UI elements, guarding sub-resources)
    and are logged at DEBUG rather than WARNING to avoid alert noise. The audit event
    (rbac.denied) written by _try_emit_rbac_denied provides the durable record for
    compliance, so the log line is only needed during development.
    """
    if allowed:
        return
    logger.debug(
        "rbac.denied",
        extra={
            "user_id": tenant_context.user_id,
            "required": permission_str,
            "path": request.url.path,
        },
    )
    _try_emit_rbac_denied(
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        permission_str=permission_str,
        endpoint=request.url.path,
        method=request.method,
        roles=tenant_context.roles,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to perform this action",
    )


def require_permission(permission: Permission) -> Callable:
    """Decorator — raises 403 if context lacks the given permission."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _get_request_from_args(args, kwargs)
            ctx = get_tenant_context(request)
            _enforce_permission(
                allowed=has_permission(ctx, permission),
                permission_str=permission.value,
                tenant_context=ctx,
                request=request,
            )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(*permissions: Permission) -> Callable:
    """Decorator — raises 403 if context lacks every one of the given permissions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _get_request_from_args(args, kwargs)
            ctx = get_tenant_context(request)
            _enforce_permission(
                allowed=has_any_permission(ctx, list(permissions)),
                permission_str=",".join(p.value for p in permissions),
                tenant_context=ctx,
                request=request,
            )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_all_permissions(*permissions: Permission) -> Callable:
    """Decorator — raises 403 unless context holds all of the given permissions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _get_request_from_args(args, kwargs)
            ctx = get_tenant_context(request)
            _enforce_permission(
                allowed=has_all_permissions(ctx, list(permissions)),
                permission_str=",".join(p.value for p in permissions),
                tenant_context=ctx,
                request=request,
            )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_role(role: Role) -> Callable:
    """Decorator — raises 403 if context doesn't carry the given role. Prefer require_permission() where possible."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _get_request_from_args(args, kwargs)
            ctx = get_tenant_context(request)
            _enforce_permission(
                allowed=has_role(ctx, role),
                permission_str=f"role:{role.value}",
                tenant_context=ctx,
                request=request,
            )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """Shorthand for @require_role(Role.ADMIN)."""
    return require_role(Role.ADMIN)(func)


def check_permission_or_raise(
    tenant_context: TenantContext,
    permission: Permission,
    request: Request,
) -> None:
    """Programmatic permission check — use inside handler bodies when a decorator isn't convenient."""
    _enforce_permission(
        allowed=has_permission(tenant_context, permission),
        permission_str=permission.value,
        tenant_context=tenant_context,
        request=request,
    )
