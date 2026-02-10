"""
Read-only entitlements endpoint. Returns resolved feature list for current tenant.
Backend enforcement is authoritative; this is for UX only.
"""

from fastapi import APIRouter, Request, HTTPException, status

from src.entitlements.service import get_entitlements

router = APIRouter(prefix="/entitlements", tags=["entitlements"])


def _tenant_id(request: Request) -> str:
    if hasattr(request.state, "tenant_id") and request.state.tenant_id:
        return request.state.tenant_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing tenant context")


@router.get("", response_model=dict)
def get_entitlements_for_tenant(request: Request) -> dict:
    """
    Return resolved entitlements for the current tenant (plan + overrides).
    Never exposes raw plan defaults; only the resolved feature list.
    """
    tenant_id = _tenant_id(request)
    result = get_entitlements(tenant_id)
    if not result.allowed or result.entitlement_set is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": result.error_code or "ENTITLEMENT_EVAL_FAILED", "message": result.deny_reason},
        )
    ent = result.entitlement_set
    return {
        "tenant_id": ent.tenant_id,
        "plan": ent.plan,
        "features": list(ent.features),
        "overrides_applied": list(ent.overrides_applied),
    }
