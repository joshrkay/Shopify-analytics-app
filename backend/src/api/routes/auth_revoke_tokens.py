"""
Token revocation API routes.

Handles:
- Bulk revocation of all active embed tokens for the authenticated user

Security:
- Requires JWT authentication with tenant context
- Requires ANALYTICS_VIEW permission
- Emits auth.jwt_revoked audit event on revocation

Phase 1 - JWT Issuance System for Superset Embedding
"""

import logging

from fastapi import APIRouter, Request, HTTPException, status

from src.platform.tenant_context import get_tenant_context
from src.platform.rbac import require_permission
from src.constants.permissions import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/revoke-tokens")
@require_permission(Permission.ANALYTICS_VIEW)
async def revoke_tokens(request: Request):
    """
    Revoke all active embed tokens for the authenticated user and tenant.

    This endpoint invalidates every JTI tracked in the Redis token store
    for the calling user's tenant context, ensuring that previously issued
    embed tokens can no longer be used.

    Returns:
        {"revoked": true, "message": "All active embed tokens revoked"}
    """
    tenant_ctx = get_tenant_context(request)

    logger.info(
        "Revoking all embed tokens for user",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "user_id": tenant_ctx.user_id,
        },
    )

    revoked_count = 0
    try:
        from src.services.token_store import get_token_store

        store = get_token_store()
        revoked_count = store.revoke_all_for_user(
            user_id=tenant_ctx.user_id,
            tenant_id=tenant_ctx.tenant_id,
        )
    except Exception:
        logger.error(
            "Failed to revoke tokens via token store",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke tokens",
        )

    # Emit auth.jwt_revoked audit event
    try:
        from src.services.audit_logger import emit_jwt_revoked
        from src.database.session import get_db_session_sync

        db_gen = get_db_session_sync()
        db = next(db_gen)
        try:
            emit_jwt_revoked(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                reason="user_request",
                revoked_by=tenant_ctx.user_id,
            )
        finally:
            db.close()
    except Exception:
        logger.warning(
            "Failed to emit auth.jwt_revoked audit event",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )

    logger.info(
        "Successfully revoked embed tokens",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "user_id": tenant_ctx.user_id,
            "revoked_count": revoked_count,
        },
    )

    return {
        "revoked": True,
        "message": "All active embed tokens revoked",
    }
