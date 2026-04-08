"""Clerk Organization Membership API integration."""

import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


class ClerkOrganizationError(Exception):
    """Raised when Clerk organization membership sync fails."""


def _get_base_url() -> str:
    return os.getenv("CLERK_BACKEND_API_URL", "https://api.clerk.com/v1").rstrip("/")


def _get_secret_key() -> str:
    secret = os.getenv("CLERK_SECRET_KEY", "").strip()
    if not secret:
        raise ClerkOrganizationError("CLERK_SECRET_KEY is required for Clerk dual-write")
    return secret


def add_organization_membership(
    *,
    clerk_org_id: str,
    clerk_user_id: str,
    role: str = "org:member",
) -> Dict[str, Any]:
    """Create Clerk organization membership (idempotent for existing membership)."""
    if not clerk_org_id:
        raise ClerkOrganizationError("clerk_org_id is required")
    if not clerk_user_id:
        raise ClerkOrganizationError("clerk_user_id is required")

    secret_key = _get_secret_key()
    url = f"{_get_base_url()}/organizations/{clerk_org_id}/memberships"

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }
    payload = {"user_id": clerk_user_id, "role": role}

    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise ClerkOrganizationError(f"Failed to call Clerk API: {exc}") from exc

    if response.status_code in (200, 201):
        body = response.json()
        logger.info(
            "Clerk org membership created",
            extra={
                "clerk_org_id": clerk_org_id,
                "clerk_user_id": clerk_user_id,
                "membership_id": body.get("id"),
            },
        )
        return body

    if response.status_code == 409:
        logger.info(
            "Clerk org membership already exists",
            extra={"clerk_org_id": clerk_org_id, "clerk_user_id": clerk_user_id},
        )
        return {"status": "already_exists", "clerk_org_id": clerk_org_id, "clerk_user_id": clerk_user_id}

    message = response.text[:500]
    raise ClerkOrganizationError(
        f"Clerk membership create failed: status={response.status_code}, response={message}"
    )
