"""
Admin API endpoints for Super Admin management.

SECURITY CRITICAL:
- All endpoints require the actor to be an existing super admin
- Super admin status is ONLY resolved from database, NEVER from JWT claims
- All operations are audited with critical severity events

Endpoints:
- GET  /api/admin/super-admins        - List all super admins
- POST /api/admin/super-admins/grant  - Grant super admin to a user
- POST /api/admin/super-admins/revoke - Revoke super admin from a user
- GET  /api/admin/tenants             - List all tenants (super admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.middleware import require_auth
from src.auth.context_resolver import AuthContext
from src.database.session import get_db_session
from src.services.super_admin_service import (
    SuperAdminService,
    NotSuperAdminError,
    UserNotFoundError,
    AlreadySuperAdminError,
    NotCurrentlySuperAdminError,
    SelfOperationError,
    CannotRevokeLastSuperAdminError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# Request/Response Models
# =============================================================================

class GrantSuperAdminRequest(BaseModel):
    """Request to grant super admin status."""
    clerk_user_id: str = Field(
        ...,
        description="Clerk user ID of the user to grant super admin to",
        examples=["user_2abc123def456"],
    )


class RevokeSuperAdminRequest(BaseModel):
    """Request to revoke super admin status."""
    clerk_user_id: str = Field(
        ...,
        description="Clerk user ID of the user to revoke super admin from",
        examples=["user_2abc123def456"],
    )
    reason: str = Field(
        default="administrative action",
        description="Reason for revoking super admin status",
        examples=["Role change", "Security policy", "User request"],
    )


class SuperAdminResponse(BaseModel):
    """Response containing super admin user info."""
    user_id: str
    clerk_user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_super_admin: bool


class GrantRevokeResponse(BaseModel):
    """Response for grant/revoke operations."""
    success: bool
    user_id: str
    clerk_user_id: str
    is_super_admin: bool
    message: str


class TenantResponse(BaseModel):
    """Response containing tenant info."""
    tenant_id: str
    name: str
    slug: Optional[str] = None
    billing_tier: str
    clerk_org_id: Optional[str] = None


class TenantListResponse(BaseModel):
    """Response containing list of tenants."""
    tenants: list[TenantResponse]
    count: int


# =============================================================================
# Helper: Require Super Admin
# =============================================================================

def require_super_admin(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_session),
) -> tuple[AuthContext, SuperAdminService]:
    """
    Dependency that requires super admin status from database.

    SECURITY: This checks the database directly, ignoring any JWT claims.

    Returns:
        Tuple of (AuthContext, SuperAdminService)

    Raises:
        HTTPException 403: If user is not a super admin
    """
    service = SuperAdminService(
        session=db,
        actor_clerk_user_id=auth.clerk_user_id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    if not service.is_super_admin():
        logger.warning(
            "Non-super-admin attempted to access super admin endpoint",
            extra={
                "clerk_user_id": auth.clerk_user_id,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )

    return auth, service


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/super-admins",
    response_model=list[SuperAdminResponse],
    summary="List all super admins",
    description="Returns a list of all users with super admin status. Requires super admin.",
)
async def list_super_admins(
    deps: tuple[AuthContext, SuperAdminService] = Depends(require_super_admin),
):
    """
    List all super admins.

    SECURITY: Only super admins can view this list.
    """
    auth, service = deps

    try:
        admins = service.list_super_admins()
        return [SuperAdminResponse(**admin) for admin in admins]

    except NotSuperAdminError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )


@router.post(
    "/super-admins/grant",
    response_model=GrantRevokeResponse,
    summary="Grant super admin status",
    description="Grants super admin status to a user. Requires super admin.",
)
async def grant_super_admin(
    request_body: GrantSuperAdminRequest,
    deps: tuple[AuthContext, SuperAdminService] = Depends(require_super_admin),
):
    """
    Grant super admin status to a user.

    SECURITY: Only super admins can grant super admin status.
    """
    auth, service = deps

    try:
        result = service.grant_super_admin(
            target_clerk_user_id=request_body.clerk_user_id,
            source="admin_api",
        )

        return GrantRevokeResponse(
            success=True,
            user_id=result["user_id"],
            clerk_user_id=result["clerk_user_id"],
            is_super_admin=result["is_super_admin"],
            message=f"Super admin status granted to {request_body.clerk_user_id}",
        )

    except NotSuperAdminError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AlreadySuperAdminError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/super-admins/revoke",
    response_model=GrantRevokeResponse,
    summary="Revoke super admin status",
    description="Revokes super admin status from a user. Requires super admin.",
)
async def revoke_super_admin(
    request_body: RevokeSuperAdminRequest,
    deps: tuple[AuthContext, SuperAdminService] = Depends(require_super_admin),
):
    """
    Revoke super admin status from a user.

    SECURITY:
    - Only super admins can revoke super admin status
    - Cannot revoke your own super admin status
    - Cannot revoke the last super admin (prevents lockout)
    """
    auth, service = deps

    try:
        result = service.revoke_super_admin(
            target_clerk_user_id=request_body.clerk_user_id,
            reason=request_body.reason,
        )

        return GrantRevokeResponse(
            success=True,
            user_id=result["user_id"],
            clerk_user_id=result["clerk_user_id"],
            is_super_admin=result["is_super_admin"],
            message=f"Super admin status revoked from {request_body.clerk_user_id}",
        )

    except NotSuperAdminError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except NotCurrentlySuperAdminError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SelfOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except CannotRevokeLastSuperAdminError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/tenants",
    response_model=TenantListResponse,
    summary="List all tenants (super admin only)",
    description="Returns a list of all active tenants. Requires super admin.",
)
async def list_all_tenants(
    deps: tuple[AuthContext, SuperAdminService] = Depends(require_super_admin),
):
    """
    List all tenants.

    SECURITY: Only super admins have access to all tenants.
    """
    auth, service = deps

    try:
        tenants = service.get_all_tenants()
        return TenantListResponse(
            tenants=[TenantResponse(**t) for t in tenants],
            count=len(tenants),
        )

    except NotSuperAdminError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )


@router.get(
    "/super-admins/check",
    summary="Check if current user is super admin",
    description="Returns whether the current authenticated user is a super admin.",
)
async def check_super_admin_status(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_session),
):
    """
    Check if the current user is a super admin.

    SECURITY: This checks the database directly, ignoring any JWT claims.
    """
    service = SuperAdminService(
        session=db,
        actor_clerk_user_id=auth.clerk_user_id,
    )

    is_super_admin = service.is_super_admin()

    return {
        "clerk_user_id": auth.clerk_user_id,
        "is_super_admin": is_super_admin,
    }
