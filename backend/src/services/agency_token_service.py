"""Agency store-switch token issuance service.

This module centralizes how we mint refreshed auth tokens when an agency user
switches active tenants.

Production path:
- Request a signed token from the canonical auth issuer (e.g., Clerk)

Local-dev/test fallback path:
- Optional HS256 local signing, enabled only when explicitly gated by env var
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class SwitchTokenClaims:
    """Claims required when issuing a switched-tenant token."""

    user_id: str
    tenant_id: str
    org_id: str
    roles: list[str]
    allowed_tenants: list[str]
    billing_tier: str
    access_surface: str = "external_app"
    access_expiring_at: Optional[datetime] = None


class AuthIssuerError(RuntimeError):
    """Raised when a switched token cannot be issued."""


class ClerkTokenIssuerAdapter:
    """Adapter that requests a signed switched token from Clerk/canonical issuer."""

    def __init__(
        self,
        issuer_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 8.0,
    ):
        self.issuer_url = issuer_url or os.getenv("AUTH_ISSUER_SWITCH_TOKEN_URL")
        self.api_key = api_key or os.getenv("AUTH_ISSUER_API_KEY")
        self.timeout_seconds = timeout_seconds

    def issue_switched_token(self, claims: SwitchTokenClaims) -> str:
        """Request a signed switched-session token from the auth issuer."""
        if not self.issuer_url:
            raise AuthIssuerError(
                "AUTH_ISSUER_SWITCH_TOKEN_URL is required for auth-issuer token issuance"
            )

        payload: dict[str, Any] = {
            "sub": claims.user_id,
            "user_id": claims.user_id,
            "org_id": claims.org_id,
            "tenant_id": claims.tenant_id,
            "active_tenant_id": claims.tenant_id,
            "roles": claims.roles,
            "allowed_tenants": claims.allowed_tenants,
            "billing_tier": claims.billing_tier,
            "access_surface": claims.access_surface,
        }
        if claims.access_expiring_at:
            payload["access_expiring_at"] = claims.access_expiring_at.isoformat()

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = httpx.post(
                self.issuer_url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuthIssuerError(f"Auth issuer request failed: {exc}") from exc

        body = response.json() if response.content else {}
        token = body.get("jwt_token") or body.get("token")
        if not token:
            raise AuthIssuerError("Auth issuer response missing jwt token")

        return token


class AgencyTokenService:
    """Service that issues store-switch tokens via auth issuer with gated fallback."""

    def __init__(self, adapter: Optional[ClerkTokenIssuerAdapter] = None):
        self._adapter = adapter or ClerkTokenIssuerAdapter()

    @staticmethod
    def _allow_local_fallback() -> bool:
        return os.getenv("AUTH_ALLOW_LOCAL_JWT_FALLBACK", "false").lower() == "true"

    def issue_switched_token(self, claims: SwitchTokenClaims) -> str:
        """Issue switched token through auth issuer; use local fallback only when gated."""
        try:
            return self._adapter.issue_switched_token(claims)
        except Exception:
            if not self._allow_local_fallback():
                raise
            return self._issue_local_fallback_token(claims)

    def _issue_local_fallback_token(self, claims: SwitchTokenClaims) -> str:
        """Local-dev/testing fallback JWT signer (explicitly gated by env)."""
        import jwt

        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise AuthIssuerError(
                "JWT_SECRET environment variable must be set when local fallback is enabled"
            )

        payload: dict[str, Any] = {
            "sub": claims.user_id,
            "user_id": claims.user_id,
            "org_id": claims.org_id,
            "tenant_id": claims.tenant_id,
            "active_tenant_id": claims.tenant_id,
            "roles": claims.roles,
            "allowed_tenants": claims.allowed_tenants,
            "billing_tier": claims.billing_tier,
            "access_surface": claims.access_surface,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        if claims.access_expiring_at:
            payload["access_expiring_at"] = claims.access_expiring_at.isoformat()

        return jwt.encode(payload, jwt_secret, algorithm="HS256")
