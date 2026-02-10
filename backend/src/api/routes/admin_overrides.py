"""
Admin routes for per-tenant entitlement overrides. Super Admin + Support only.
On create/update/delete, invalidate entitlements cache for the tenant.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field

from src.entitlements.overrides import (
    can_manage_overrides,
    create_override,
    update_override,
    delete_override,
    list_active_overrides,
)
from src.entitlements.service import invalidate_entitlements

router = APIRouter(prefix="/admin/entitlement-overrides", tags=["admin", "entitlements"])


def _get_tenant_id(request: Request) -> str:
    if hasattr(request.state, "tenant_id") and request.state.tenant_id:
        return request.state.tenant_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing tenant context")


def _get_actor_roles(request: Request) -> List[str]:
    if hasattr(request.state, "roles") and request.state.roles:
        return list(request.state.roles)
    return []


def _get_actor_id(request: Request) -> str:
    if hasattr(request.state, "user_id") and request.state.user_id:
        return request.state.user_id
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user context")


class OverrideCreateBody(BaseModel):
    tenant_id: str = Field(..., description="Target tenant (admin only)")
    feature_key: str = Field(..., description="Feature key to grant")
    expires_at: datetime = Field(..., description="Mandatory expiry")
    reason: str = Field(..., min_length=1, description="Reason for override")


class OverrideUpdateBody(BaseModel):
    expires_at: datetime = Field(..., description="New expiry")
    reason: str = Field(..., min_length=1, description="Reason for update")


@router.get("/{target_tenant_id}")
def list_overrides(request: Request, target_tenant_id: str) -> dict:
    """List active overrides for a tenant. Requires Super Admin or Support."""
    roles = _get_actor_roles(request)
    if not can_manage_overrides(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    overrides = list_active_overrides(target_tenant_id)
    return {
        "tenant_id": target_tenant_id,
        "overrides": [
            {
                "feature_key": o.feature_key,
                "expires_at": o.expires_at.isoformat(),
                "reason": o.reason,
                "actor_id": o.actor_id,
            }
            for o in overrides
        ],
    }


@router.post("")
def create_override_route(request: Request, body: OverrideCreateBody) -> dict:
    """Create override. Invalidates entitlements cache for tenant."""
    actor_id = _get_actor_id(request)
    roles = _get_actor_roles(request)
    create_override(
        tenant_id=body.tenant_id,
        feature_key=body.feature_key,
        expires_at=body.expires_at,
        reason=body.reason,
        actor_id=actor_id,
        actor_roles=roles,
    )
    invalidate_entitlements(body.tenant_id)
    return {"ok": True, "tenant_id": body.tenant_id, "feature_key": body.feature_key}


@router.patch("/{target_tenant_id}/{feature_key}")
def update_override_route(
    request: Request, target_tenant_id: str, feature_key: str, body: OverrideUpdateBody
) -> dict:
    """Update override expiry/reason. Invalidates cache."""
    actor_id = _get_actor_id(request)
    roles = _get_actor_roles(request)
    row = update_override(
        tenant_id=target_tenant_id,
        feature_key=feature_key,
        expires_at=body.expires_at,
        reason=body.reason,
        actor_id=actor_id,
        actor_roles=roles,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    invalidate_entitlements(target_tenant_id)
    return {"ok": True, "tenant_id": target_tenant_id, "feature_key": feature_key}


@router.delete("/{target_tenant_id}/{feature_key}")
def delete_override_route(request: Request, target_tenant_id: str, feature_key: str) -> dict:
    """Remove override. Invalidates cache."""
    actor_id = _get_actor_id(request)
    roles = _get_actor_roles(request)
    deleted = delete_override(
        tenant_id=target_tenant_id,
        feature_key=feature_key,
        actor_id=actor_id,
        actor_roles=roles,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    invalidate_entitlements(target_tenant_id)
    return {"ok": True, "tenant_id": target_tenant_id, "feature_key": feature_key}
