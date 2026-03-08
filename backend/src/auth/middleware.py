"""
FastAPI authentication dependencies for route-level auth.

This module provides FastAPI dependency injection functions that read
AuthContext from request.state (set by TenantContextMiddleware in production).

Usage:

    # Require authentication in routes
    @router.get("/protected")
    async def protected_route(user: User = Depends(require_auth)):
        return {"user_id": user.id}

    # Optional authentication
    @router.get("/public")
    async def public_route(auth: AuthContext = Depends(get_auth_context)):
        if auth.is_authenticated:
            return {"user": auth.user_id}
        return {"message": "Welcome, guest"}
"""

import logging
from typing import Optional

from starlette.requests import Request
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.exceptions import ClerkVerificationError
from src.auth.context_resolver import AuthContext, ANONYMOUS_CONTEXT

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)

# Paths that don't require authentication
EXEMPT_PATHS = {
    "/health",
    "/api/health",
    "/api/webhooks/clerk",
    "/api/webhooks/clerk/health",
    "/api/webhooks/shopify",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# Path prefixes that don't require authentication
EXEMPT_PREFIXES = [
    "/api/webhooks/",
    "/static/",
]


def is_exempt_path(path: str) -> bool:
    """Check if path is exempt from authentication."""
    if path in EXEMPT_PATHS:
        return True

    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True

    return False


# =============================================================================
# FastAPI Dependencies
# =============================================================================


def get_auth_context(request: Request) -> AuthContext:
    """
    FastAPI dependency to get AuthContext from request.

    Returns the AuthContext set by middleware, or ANONYMOUS_CONTEXT
    if no authentication was performed.

    Usage:
        @router.get("/data")
        async def get_data(auth: AuthContext = Depends(get_auth_context)):
            if auth.is_authenticated:
                ...
    """
    return getattr(request.state, "auth_context", ANONYMOUS_CONTEXT)


def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthContext:
    """
    FastAPI dependency that requires authentication.

    Raises HTTPException 401 if user is not authenticated.

    Usage:
        @router.get("/protected")
        async def protected_route(auth: AuthContext = Depends(require_auth)):
            return {"user": auth.user_id}
    """
    auth_context = get_auth_context(request)

    if not auth_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth_context


def require_tenant(
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """
    FastAPI dependency that requires authenticated user with tenant context.

    Raises HTTPException 400 if no tenant is selected.

    Usage:
        @router.get("/tenant-data")
        async def get_tenant_data(auth: AuthContext = Depends(require_tenant)):
            tenant_id = auth.current_tenant_id
            ...
    """
    if not auth.current_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant selected. Please select a tenant.",
            headers={"X-Tenant-Required": "true"},
        )

    return auth


def get_current_user(
    auth: AuthContext = Depends(require_auth),
):
    """
    FastAPI dependency to get the current authenticated user.

    Returns the User model instance.

    Usage:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return {"id": user.id, "email": user.email}
    """
    if not auth.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return auth.user


def get_current_tenant_id(
    auth: AuthContext = Depends(require_tenant),
) -> str:
    """
    FastAPI dependency to get the current tenant ID.

    Usage:
        @router.get("/data")
        async def get_data(tenant_id: str = Depends(get_current_tenant_id)):
            ...
    """
    return auth.current_tenant_id


# =============================================================================
# Permission Checking Dependencies
# =============================================================================


def require_permission(permission):
    """
    Create a dependency that requires a specific permission.

    Usage:
        @router.delete("/resource")
        async def delete_resource(
            auth: AuthContext = Depends(require_permission(Permission.RESOURCE_DELETE))
        ):
            ...
    """
    def dependency(auth: AuthContext = Depends(require_tenant)) -> AuthContext:
        if not auth.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}",
            )
        return auth

    return dependency


def require_any_permission(*permissions):
    """
    Create a dependency that requires any of the specified permissions.

    Usage:
        @router.get("/resource")
        async def get_resource(
            auth: AuthContext = Depends(require_any_permission(
                Permission.RESOURCE_VIEW,
                Permission.ADMIN_VIEW,
            ))
        ):
            ...
    """
    def dependency(auth: AuthContext = Depends(require_tenant)) -> AuthContext:
        for permission in permissions:
            if auth.has_permission(permission):
                return auth

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required one of: {[p.value for p in permissions]}",
        )

    return dependency


def require_role(role: str):
    """
    Create a dependency that requires a specific role.

    Usage:
        @router.post("/admin-action")
        async def admin_action(
            auth: AuthContext = Depends(require_role("admin"))
        ):
            ...
    """
    def dependency(auth: AuthContext = Depends(require_tenant)) -> AuthContext:
        if role.lower() not in {r.lower() for r in auth.current_roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role}",
            )
        return auth

    return dependency
