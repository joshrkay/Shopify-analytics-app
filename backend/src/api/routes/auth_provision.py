"""
Explicit tenant provisioning endpoint.

Called by the frontend when it receives a TENANT_NOT_PROVISIONED (403) response.
This endpoint bypasses TenantContextMiddleware (listed in PUBLIC_PATHS) and
explicitly drives the ClerkSyncService provisioning flow.

This is a safety valve for three failure modes:
  1. Clerk webhook never fired (network hiccup, misconfigured endpoint URL)
  2. _resolve_tenant_from_db lazy-sync failed silently on first request
  3. Race condition left the tenant partially provisioned / unflushed

The endpoint verifies the Clerk JWT itself, then calls:
  ClerkSyncService.get_or_create_user()
  ClerkSyncService.sync_tenant_from_org()
  ClerkSyncService.sync_membership()

It is fully idempotent — safe to call multiple times from retry loops.
"""

import logging
import os
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.database.session import get_db_session_sync
from src.models.tenant import Tenant, TenantStatus
from src.services.clerk_sync_service import ClerkSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ProvisionResponse(BaseModel):
    tenant_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_clerk_jwt(token: str) -> dict:
    """
    Verify and decode a Clerk JWT.

    Replicates the same decode logic used by TenantContextMiddleware so that
    this endpoint enforces the same trust boundary even though it runs outside
    the middleware.
    """
    clerk_frontend_api = os.getenv("CLERK_FRONTEND_API")
    if not clerk_frontend_api:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured (CLERK_FRONTEND_API missing).",
        )

    from src.platform.tenant_context import ClerkJWKSClient

    jwks_client = ClerkJWKSClient(clerk_frontend_api)
    signing_key = jwks_client.get_signing_key(token)
    issuer = (
        clerk_frontend_api
        if clerk_frontend_api.startswith("http")
        else f"https://{clerk_frontend_api.rstrip('/')}"
    )
    payload = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={
            "verify_signature": True,
            "verify_aud": False,
            "verify_iss": True,
            "verify_exp": True,
        },
    )
    return payload


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/provision", response_model=ProvisionResponse)
async def provision_tenant(request: Request):
    """
    Explicitly provision the tenant for the authenticated user.

    The frontend calls this whenever all API calls return
    ``error_code: "TENANT_NOT_PROVISIONED"``.  It creates the User, Tenant,
    and UserTenantRole records that the normal middleware lazy-sync should have
    created on first login.

    Returns the resolved ``tenant_id`` on success.
    Idempotent: safe to call many times — subsequent calls return the same
    ``tenant_id`` and ``status: "ok"``.
    """
    # --- 1. Extract and verify JWT ---
    credentials: Optional[HTTPAuthorizationCredentials] = await _security(request)
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token.",
        )

    try:
        payload = _decode_clerk_jwt(credentials.credentials)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "JWT decode failed in provision endpoint",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization token.",
        )

    # --- 2. Extract claims (supports Clerk JWT v1 and v2 formats) ---
    user_id: Optional[str] = payload.get("sub")
    org_id: Optional[str] = payload.get("org_id") or (payload.get("o") or {}).get("id")
    org_role: str = (
        payload.get("org_role", "")
        or (payload.get("o") or {}).get("rol", "")
        or "org:member"
    )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing the user identifier (sub claim).",
        )
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Token is missing an organization identifier. "
                "Ensure the user belongs to a Clerk Organization."
            ),
        )

    # --- 3. Run provisioning ---
    db = next(get_db_session_sync())
    try:
        sync = ClerkSyncService(db, skip_audit=True)

        sync.get_or_create_user(clerk_user_id=user_id)
        sync.sync_tenant_from_org(
            clerk_org_id=org_id,
            name=f"Tenant {org_id[-8:]}",
            source="provision_endpoint",
        )
        # Flush so sync_membership can locate both records within this session.
        db.flush()
        sync.sync_membership(
            clerk_user_id=user_id,
            clerk_org_id=org_id,
            role=org_role,
            source="provision_endpoint",
            assigned_by="system",
        )
        db.commit()

        tenant = (
            db.query(Tenant)
            .filter(
                Tenant.clerk_org_id == org_id,
                Tenant.status == TenantStatus.ACTIVE,
            )
            .first()
        )
        if not tenant:
            # Committed but not readable — should not happen under normal operation.
            logger.error(
                "Tenant not found after provision commit",
                extra={"clerk_org_id": org_id, "user_id": user_id},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provisioning completed but tenant record not found. Please retry.",
            )

        logger.info(
            "Tenant provisioned via /api/auth/provision",
            extra={
                "clerk_org_id": org_id,
                "tenant_id": tenant.id,
                "user_id": user_id,
            },
        )
        return ProvisionResponse(
            tenant_id=tenant.id,
            status="ok",
            message="Organization provisioned successfully.",
        )

    except HTTPException:
        raise

    except IntegrityError:
        # Concurrent provision call raced us — re-query and return success.
        db.rollback()
        tenant = (
            db.query(Tenant)
            .filter(
                Tenant.clerk_org_id == org_id,
                Tenant.status == TenantStatus.ACTIVE,
            )
            .first()
        )
        if tenant:
            logger.info(
                "Provision concurrent-create resolved",
                extra={"clerk_org_id": org_id, "tenant_id": tenant.id},
            )
            return ProvisionResponse(
                tenant_id=tenant.id,
                status="ok",
                message="Organization already provisioned.",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provisioning conflict. Please retry.",
        )

    except Exception as exc:
        db.rollback()
        logger.error(
            "Tenant provisioning failed",
            extra={
                "clerk_org_id": org_id,
                "user_id": user_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Provisioning failed ({type(exc).__name__}). Please retry.",
        )

    finally:
        db.close()
