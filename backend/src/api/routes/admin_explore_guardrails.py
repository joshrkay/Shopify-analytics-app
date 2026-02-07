"""
Admin Explore Guardrail Bypass API.

Story 5.4 - Explore Mode Guardrails (Finalized)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.auth.middleware import require_auth
from src.auth.context_resolver import AuthContext
from src.database.session import get_db_session
from src.services.super_admin_service import SuperAdminService
from src.platform.rbac import require_guardrail_bypass_approver
from src.services.explore_guardrail_exception_service import (
    ExploreGuardrailExceptionService,
    ExploreGuardrailExceptionNotFound,
    ExploreGuardrailExceptionValidationError,
)
from src.services.audit_logger import (
    emit_explore_guardrail_bypass_requested,
    emit_explore_guardrail_bypass_approved,
    emit_explore_guardrail_bypass_expired,
)
from src.api.schemas.explore_guardrail_exception import (
    CreateGuardrailBypassRequest,
    ApproveGuardrailBypassRequest,
    GuardrailBypassResponse,
    GuardrailBypassListResponse,
    GuardrailBypassRequestCreatedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/explore-guardrails",
    tags=["admin-explore-guardrails"],
)


def require_super_admin(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_session),
) -> tuple[AuthContext, Session]:
    """Dependency requiring DB-verified super admin."""
    service = SuperAdminService(
        session=db,
        actor_clerk_user_id=auth.clerk_user_id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    if not service.is_super_admin():
        logger.warning(
            "Non-super-admin attempted guardrail request",
            extra={"clerk_user_id": auth.clerk_user_id, "path": request.url.path},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return auth, db


@router.post(
    "/requests",
    response_model=GuardrailBypassRequestCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a guardrail bypass",
)
async def request_guardrail_bypass(
    request: Request,
    body: CreateGuardrailBypassRequest,
    deps: tuple[AuthContext, Session] = Depends(require_super_admin),
):
    """Super admin only. Creates a pending guardrail bypass request."""
    auth, db = deps
    service = ExploreGuardrailExceptionService(db)

    try:
        record, created, message = service.request_exception(
            user_id=body.user_id,
            dataset_names=body.dataset_names,
            reason=body.reason,
        )

        emit_explore_guardrail_bypass_requested(
            db,
            record,
            requested_by=auth.clerk_user_id,
            duration_minutes=body.requested_duration_minutes,
            correlation_id=getattr(request.state, "correlation_id", None),
        )

        response = GuardrailBypassRequestCreatedResponse(
            exception=_to_response(record),
            created=created,
            message=message,
        )
        db.commit()
        return response
    except ExploreGuardrailExceptionValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/requests/{exception_id}/approve",
    response_model=GuardrailBypassResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a guardrail bypass request",
    dependencies=[Depends(require_guardrail_bypass_approver)],
)
async def approve_guardrail_bypass(
    request: Request,
    exception_id: str,
    body: ApproveGuardrailBypassRequest,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_session),
):
    """Approver only. Approves a pending guardrail bypass request."""
    service = ExploreGuardrailExceptionService(db)
    try:
        record = service.approve_exception(
            exception_id=exception_id,
            approved_by=auth.user_id or auth.clerk_user_id,
            duration_minutes=body.duration_minutes,
        )
        emit_explore_guardrail_bypass_approved(
            db,
            record,
            duration_minutes=body.duration_minutes,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        db.commit()
        return _to_response(record)
    except ExploreGuardrailExceptionNotFound as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ExploreGuardrailExceptionValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/exceptions/active",
    response_model=GuardrailBypassListResponse,
    status_code=status.HTTP_200_OK,
    summary="List active guardrail bypass exceptions",
    dependencies=[Depends(require_guardrail_bypass_approver)],
)
async def list_active_exceptions(
    user_id: str | None = None,
    dataset_name: str | None = None,
    db: Session = Depends(get_db_session),
):
    """List active (approved, unexpired) guardrail exceptions."""
    service = ExploreGuardrailExceptionService(db)
    records = service.list_active_exceptions(
        user_id=user_id,
        dataset_name=dataset_name,
    )
    return GuardrailBypassListResponse(
        exceptions=[_to_response(r) for r in records],
        total=len(records),
    )


@router.post(
    "/exceptions/{exception_id}/revoke",
    response_model=GuardrailBypassResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke a guardrail bypass exception early",
    dependencies=[Depends(require_guardrail_bypass_approver)],
)
async def revoke_guardrail_bypass(
    request: Request,
    exception_id: str,
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db_session),
):
    """Approver only. Expires a bypass exception immediately."""
    service = ExploreGuardrailExceptionService(db)
    try:
        record = service.revoke_exception(exception_id=exception_id)
        emit_explore_guardrail_bypass_expired(
            db,
            record,
            revoked_by=auth.user_id or auth.clerk_user_id,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        db.commit()
        return _to_response(record)
    except ExploreGuardrailExceptionNotFound as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _to_response(record) -> GuardrailBypassResponse:
    """Convert DB model to response schema."""
    return GuardrailBypassResponse(
        id=record.id,
        user_id=record.user_id,
        approved_by=record.approved_by,
        dataset_names=list(record.dataset_names or []),
        expires_at=record.expires_at.isoformat() if record.expires_at else None,
        reason=record.reason,
        created_at=record.created_at,
    )
