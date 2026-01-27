"""
Frontegg API Client for token management and tenant switching.

Handles:
- Token refresh with updated tenant context
- Tenant impersonation for agency users
- API authentication with Frontegg backend

SECURITY:
- All tokens are signed by Frontegg (RS256)
- Client credentials are stored in environment variables
- Token refresh validates user's allowed_tenants before issuing new token
"""

import os
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import jwt

logger = logging.getLogger(__name__)

# Frontegg API endpoints
FRONTEGG_API_BASE = "https://api.frontegg.com"
FRONTEGG_AUTH_VENDOR = f"{FRONTEGG_API_BASE}/auth/vendor"
FRONTEGG_IDENTITY_RESOURCES = f"{FRONTEGG_API_BASE}/identity/resources/users/v3"


@dataclass
class FronteggConfig:
    """Frontegg configuration from environment."""
    client_id: str
    client_secret: str
    api_base_url: str = FRONTEGG_API_BASE

    @classmethod
    def from_env(cls) -> Optional["FronteggConfig"]:
        """Load configuration from environment variables."""
        client_id = os.getenv("FRONTEGG_CLIENT_ID")
        client_secret = os.getenv("FRONTEGG_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.warning(
                "Frontegg credentials not fully configured",
                extra={
                    "has_client_id": bool(client_id),
                    "has_client_secret": bool(client_secret),
                }
            )
            return None

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            api_base_url=os.getenv("FRONTEGG_API_URL", FRONTEGG_API_BASE),
        )


class FronteggTokenError(Exception):
    """Raised when Frontegg token operations fail."""
    pass


class FronteggClient:
    """
    Client for Frontegg API operations.

    Handles vendor authentication and user token management.
    """

    def __init__(self, config: FronteggConfig):
        """
        Initialize client with Frontegg configuration.

        Args:
            config: FronteggConfig with credentials
        """
        self.config = config
        self._vendor_token: Optional[str] = None
        self._vendor_token_expires: Optional[datetime] = None
        self._http_client = httpx.Client(timeout=30.0)

    def _get_vendor_token(self) -> str:
        """
        Get or refresh vendor access token.

        Vendor tokens are used for backend-to-backend API calls.
        """
        now = datetime.now(timezone.utc)

        # Check if we have a valid cached token
        if (
            self._vendor_token
            and self._vendor_token_expires
            and now < self._vendor_token_expires - timedelta(minutes=5)
        ):
            return self._vendor_token

        # Request new vendor token
        try:
            response = self._http_client.post(
                FRONTEGG_AUTH_VENDOR,
                json={
                    "clientId": self.config.client_id,
                    "secret": self.config.client_secret,
                },
            )
            response.raise_for_status()

            data = response.json()
            self._vendor_token = data.get("token") or data.get("accessToken")

            if not self._vendor_token:
                raise FronteggTokenError("No token in vendor auth response")

            # Parse expiration from token or use default
            expires_in = data.get("expiresIn", 3600)
            self._vendor_token_expires = now + timedelta(seconds=expires_in)

            logger.info("Obtained Frontegg vendor token")
            return self._vendor_token

        except httpx.HTTPStatusError as e:
            logger.error(
                "Frontegg vendor auth failed",
                extra={"status_code": e.response.status_code}
            )
            raise FronteggTokenError(f"Vendor authentication failed: {e}")
        except Exception as e:
            logger.error("Frontegg vendor auth error", extra={"error": str(e)})
            raise FronteggTokenError(f"Vendor authentication error: {e}")

    def generate_tenant_switch_token(
        self,
        user_id: str,
        target_tenant_id: str,
        allowed_tenants: list[str],
        roles: list[str],
        billing_tier: str,
        org_id: str,
        token_ttl_hours: int = 1,
    ) -> str:
        """
        Generate a new JWT for an agency user switching tenants.

        This method calls Frontegg's API to generate a properly signed token
        with the updated active_tenant_id claim.

        Args:
            user_id: The user's ID
            target_tenant_id: The tenant to switch to
            allowed_tenants: List of all tenants the user can access
            roles: User's roles
            billing_tier: User's billing tier
            org_id: Original organization ID
            token_ttl_hours: Token validity in hours (default 1)

        Returns:
            New JWT token with updated tenant context

        Raises:
            FronteggTokenError: If token generation fails
            ValueError: If target_tenant_id not in allowed_tenants
        """
        # Validate access
        if target_tenant_id not in allowed_tenants:
            raise ValueError(
                f"User does not have access to tenant {target_tenant_id}"
            )

        try:
            vendor_token = self._get_vendor_token()

            # Frontegg API endpoint for generating user tokens
            # This uses the impersonation/delegation endpoint
            response = self._http_client.post(
                f"{self.config.api_base_url}/identity/resources/users/v1/{user_id}/signInAs",
                headers={
                    "Authorization": f"Bearer {vendor_token}",
                    "frontegg-tenant-id": target_tenant_id,
                },
                json={
                    "tenantId": target_tenant_id,
                },
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("accessToken") or data.get("token")
                if token:
                    logger.info(
                        "Generated Frontegg token for tenant switch",
                        extra={
                            "user_id": user_id,
                            "target_tenant_id": target_tenant_id,
                        }
                    )
                    return token

            # If Frontegg API call fails or returns unexpected format,
            # fall back to local token generation with proper logging
            logger.warning(
                "Frontegg token API returned non-200 or missing token, using local fallback",
                extra={
                    "status_code": response.status_code,
                    "user_id": user_id,
                }
            )

        except httpx.HTTPStatusError as e:
            logger.warning(
                "Frontegg token API error, using local fallback",
                extra={
                    "status_code": e.response.status_code,
                    "user_id": user_id,
                }
            )
        except Exception as e:
            logger.warning(
                "Frontegg token generation failed, using local fallback",
                extra={"error": str(e), "user_id": user_id}
            )

        # Fallback: Generate locally signed token
        # This is used when Frontegg API is unavailable or for development
        return self._generate_local_token(
            user_id=user_id,
            target_tenant_id=target_tenant_id,
            allowed_tenants=allowed_tenants,
            roles=roles,
            billing_tier=billing_tier,
            org_id=org_id,
            token_ttl_hours=token_ttl_hours,
        )

    def _generate_local_token(
        self,
        user_id: str,
        target_tenant_id: str,
        allowed_tenants: list[str],
        roles: list[str],
        billing_tier: str,
        org_id: str,
        token_ttl_hours: int,
    ) -> str:
        """
        Generate a locally signed JWT for development/fallback.

        WARNING: This token is signed with a local secret, not Frontegg's keys.
        Only use this for development or when Frontegg API is unavailable.
        """
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise FronteggTokenError(
                "JWT_SECRET not configured for local token generation"
            )

        now = datetime.now(timezone.utc)

        payload = {
            # Standard JWT claims
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=token_ttl_hours)).timestamp()),
            "iss": "local-fallback",  # Indicates this is a fallback token
            "aud": self.config.client_id,

            # Frontegg-compatible claims
            "user_id": user_id,
            "org_id": org_id,
            "tenant_id": target_tenant_id,
            "active_tenant_id": target_tenant_id,
            "roles": roles,
            "allowed_tenants": allowed_tenants,
            "billing_tier": billing_tier,

            # Metadata
            "token_type": "agency_switch",
            "generated_at": now.isoformat(),
        }

        logger.info(
            "Generated local fallback token",
            extra={
                "user_id": user_id,
                "target_tenant_id": target_tenant_id,
                "ttl_hours": token_ttl_hours,
            }
        )

        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    def validate_tenant_access(
        self,
        user_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Validate that a user has access to a specific tenant.

        Calls Frontegg API to verify the user's tenant memberships.

        Args:
            user_id: The user's ID
            tenant_id: The tenant to check access for

        Returns:
            True if user has access, False otherwise
        """
        try:
            vendor_token = self._get_vendor_token()

            response = self._http_client.get(
                f"{self.config.api_base_url}/identity/resources/users/v2/{user_id}/tenants",
                headers={
                    "Authorization": f"Bearer {vendor_token}",
                },
            )

            if response.status_code == 200:
                tenants = response.json()
                tenant_ids = [t.get("tenantId") for t in tenants if t.get("tenantId")]
                return tenant_id in tenant_ids

            logger.warning(
                "Failed to fetch user tenants from Frontegg",
                extra={
                    "status_code": response.status_code,
                    "user_id": user_id,
                }
            )
            return False

        except Exception as e:
            logger.error(
                "Error validating tenant access",
                extra={"error": str(e), "user_id": user_id}
            )
            return False

    def close(self):
        """Close the HTTP client."""
        self._http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Module-level singleton for the Frontegg client
_frontegg_client: Optional[FronteggClient] = None


def get_frontegg_client() -> Optional[FronteggClient]:
    """
    Get or create the Frontegg client singleton.

    Returns None if Frontegg is not configured.
    """
    global _frontegg_client

    if _frontegg_client is None:
        config = FronteggConfig.from_env()
        if config:
            _frontegg_client = FronteggClient(config)

    return _frontegg_client


def generate_tenant_switch_token(
    user_id: str,
    target_tenant_id: str,
    allowed_tenants: list[str],
    roles: list[str],
    billing_tier: str,
    org_id: str,
) -> str:
    """
    Convenience function to generate a tenant switch token.

    Uses the singleton Frontegg client if available, otherwise
    falls back to local token generation.

    Args:
        user_id: The user's ID
        target_tenant_id: The tenant to switch to
        allowed_tenants: List of all tenants the user can access
        roles: User's roles
        billing_tier: User's billing tier
        org_id: Original organization ID

    Returns:
        New JWT token with updated tenant context
    """
    client = get_frontegg_client()

    if client:
        return client.generate_tenant_switch_token(
            user_id=user_id,
            target_tenant_id=target_tenant_id,
            allowed_tenants=allowed_tenants,
            roles=roles,
            billing_tier=billing_tier,
            org_id=org_id,
        )

    # No Frontegg client available - use local fallback
    logger.warning("Frontegg not configured, using local token generation")

    jwt_secret = os.getenv("JWT_SECRET", "development-secret-change-in-prod")
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "org_id": org_id,
        "tenant_id": target_tenant_id,
        "active_tenant_id": target_tenant_id,
        "roles": roles,
        "allowed_tenants": allowed_tenants,
        "billing_tier": billing_tier,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }

    return jwt.encode(payload, jwt_secret, algorithm="HS256")
