"""Audit logging middleware for auth and dashboard access."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.platform.errors import generate_correlation_id

logger = logging.getLogger(__name__)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Emit audit events for auth and dashboard access."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or generate_correlation_id()
        request.state.correlation_id = correlation_id

        body_bytes = await request.body()

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes}

        request = Request(request.scope, receive)
        response = await call_next(request)
        response.headers.setdefault("X-Correlation-ID", correlation_id)

        await self._emit_audit_events(request, response, body_bytes, correlation_id)
        return response

    async def _emit_audit_events(
        self,
        request: Request,
        response: Response,
        body_bytes: bytes,
        correlation_id: str,
    ) -> None:
        path = request.url.path
        method = request.method.upper()
        payload = _parse_json(body_bytes)

        if path == "/api/v1/embed/token" and method == "POST":
            await _handle_embed_token_request(request, response, payload, correlation_id)
            return

        if path == "/api/v1/embed/token/refresh" and method == "POST":
            await _handle_embed_token_refresh(request, response, payload, correlation_id)
            return

        if path == "/api/v1/auth/revoke-tokens" and method == "POST":
            await _handle_token_revocation(request, response, correlation_id)
            return

        if path == "/auth/refresh-jwt" and method == "POST":
            await _handle_refresh_jwt(request, response, payload, correlation_id)


async def _handle_embed_token_request(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    correlation_id: str,
) -> None:
    tenant_ctx = _get_tenant_context(request)
    if tenant_ctx is None:
        return

    dashboard_id = str(payload.get("dashboard_id", ""))
    access_surface = str(payload.get("access_surface", "external_app"))

    from src.database.session import get_db_session_sync
    from src.services.audit_logger import (
        emit_dashboard_access_denied,
        emit_dashboard_load_failed,
    )

    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        if response.status_code == 403:
            emit_dashboard_access_denied(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                dashboard_id=dashboard_id,
                access_surface=access_surface,
                reason="dashboard_not_allowed",
                correlation_id=correlation_id,
            )
        elif response.status_code >= 500:
            emit_dashboard_load_failed(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                dashboard_id=dashboard_id,
                access_surface=access_surface,
                reason="token_generation_failed",
                correlation_id=correlation_id,
            )
    except Exception:
        logger.warning(
            "Audit middleware failed for embed token",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )
    finally:
        db.close()


async def _handle_embed_token_refresh(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    correlation_id: str,
) -> None:
    tenant_ctx = _get_tenant_context(request)
    if tenant_ctx is None:
        return

    dashboard_id = str(payload.get("dashboard_id", "unknown"))

    from src.database.session import get_db_session_sync
    from src.services.audit_logger import emit_jwt_refresh, emit_jwt_refresh_failed

    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        if 200 <= response.status_code < 300:
            emit_jwt_refresh(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                dashboard_id=dashboard_id,
                correlation_id=correlation_id,
            )
        else:
            reason = _map_refresh_failure_reason(response.status_code)
            emit_jwt_refresh_failed(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                dashboard_id=dashboard_id,
                reason=reason,
                correlation_id=correlation_id,
            )
    except Exception:
        logger.warning(
            "Audit middleware failed for embed token refresh",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )
    finally:
        db.close()


async def _handle_token_revocation(
    request: Request,
    response: Response,
    correlation_id: str,
) -> None:
    tenant_ctx = _get_tenant_context(request)
    if tenant_ctx is None or response.status_code >= 400:
        return

    from src.database.session import get_db_session_sync
    from src.services.audit_logger import emit_jwt_revoked

    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        emit_jwt_revoked(
            db=db,
            tenant_id=tenant_ctx.tenant_id,
            user_id=tenant_ctx.user_id,
            reason="user_request",
            revoked_by=tenant_ctx.user_id,
            correlation_id=correlation_id,
        )
    except Exception:
        logger.warning(
            "Audit middleware failed for token revocation",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )
    finally:
        db.close()


async def _handle_refresh_jwt(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    correlation_id: str,
) -> None:
    tenant_ctx = _get_tenant_context(request)
    if tenant_ctx is None:
        return

    access_surface = str(payload.get("access_surface", "external_app"))

    from src.database.session import get_db_session_sync
    from src.services.audit_logger import emit_jwt_refresh, emit_jwt_refresh_failed

    db_gen = get_db_session_sync()
    db = next(db_gen)
    try:
        if 200 <= response.status_code < 300:
            emit_jwt_refresh(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                access_surface=access_surface,
                correlation_id=correlation_id,
            )
        else:
            reason = response.headers.get("X-Error-Code") or _map_refresh_failure_reason(
                response.status_code
            )
            emit_jwt_refresh_failed(
                db=db,
                tenant_id=tenant_ctx.tenant_id,
                user_id=tenant_ctx.user_id,
                reason=reason,
                access_surface=access_surface,
                correlation_id=correlation_id,
            )
    except Exception:
        logger.warning(
            "Audit middleware failed for JWT refresh",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
            },
            exc_info=True,
        )
    finally:
        db.close()


def _parse_json(body_bytes: bytes) -> dict[str, Any]:
    if not body_bytes:
        return {}
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _get_tenant_context(request: Request):
    try:
        from src.platform.tenant_context import get_tenant_context

        return get_tenant_context(request)
    except Exception:
        return None


def _map_refresh_failure_reason(status_code: int) -> str:
    if status_code == 401:
        return "token_expired"
    if status_code == 400:
        return "token_validation_failed"
    if status_code == 403:
        return "access_denied"
    return "refresh_failed"
