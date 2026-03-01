"""
Per-platform OAuth configuration and helpers for app-managed OAuth flows.

Instead of delegating OAuth to Airbyte Cloud (which doesn't work on self-hosted
OSS — see https://github.com/airbytehq/airbyte/issues/50977), this module
implements OAuth directly with each ad platform:

1. build_auth_url()  — generates the platform's authorization URL
2. exchange_code_for_tokens() — exchanges the authorization code for access/refresh tokens
3. build_source_config() — maps tokens + env-var credentials to Airbyte source config

Each platform requires its own OAuth app registration. Configure credentials via
the environment variables listed in each PlatformOAuthConfig entry (see render.yaml).
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

_SHOP_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.myshopify\.com$")


def validate_shop_domain(shop_domain: str) -> str:
    """Validate and normalize shop_domain to prevent SSRF/Open Redirect.

    Raises HTTPException 400 if domain doesn't match *.myshopify.com pattern.
    """
    normalized = shop_domain.lower().strip()
    for prefix in ("https://", "http://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    normalized = normalized.rstrip("/")

    if not _SHOP_DOMAIN_RE.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid shop_domain: must be a valid *.myshopify.com domain",
        )
    return normalized


@dataclass
class PlatformOAuthConfig:
    """OAuth configuration for a single ad platform."""

    auth_url: str
    """Authorization endpoint URL (may contain {shop_domain} placeholder for Shopify)."""

    token_url: str
    """Token exchange endpoint URL (may contain {shop_domain} placeholder for Shopify)."""

    scope: str
    """Space- or comma-separated OAuth scopes to request."""

    client_id_env: str
    """Environment variable name holding the platform OAuth client ID."""

    client_secret_env: str
    """Environment variable name holding the platform OAuth client secret."""

    token_to_source_config: Dict[str, str]
    """Maps token response fields → Airbyte source configuration fields.
    E.g. {"access_token": "access_token", "refresh_token": "refresh_token"}"""

    extra_env_credentials: Dict[str, str] = field(default_factory=dict)
    """Additional env vars to inject into Airbyte source config.
    Maps env var name → source config field name.
    Used for app-level secrets like GOOGLE_ADS_DEVELOPER_TOKEN."""

    extra_auth_params: Dict[str, str] = field(default_factory=dict)
    """Extra query parameters added to the authorization URL.
    E.g. {"access_type": "offline", "prompt": "consent"} for Google."""


_SHOPIFY_OAUTH_CONFIG = PlatformOAuthConfig(
    auth_url="https://{shop_domain}/admin/oauth/authorize",
    token_url="https://{shop_domain}/admin/oauth/access_token",
    scope="read_orders,read_products,read_customers,read_marketing_events",
    client_id_env="SHOPIFY_API_KEY",
    client_secret_env="SHOPIFY_API_SECRET",
    token_to_source_config={"access_token": "access_token"},
)


OAUTH_REGISTRY: Dict[str, PlatformOAuthConfig] = {
    "meta_ads": PlatformOAuthConfig(
        auth_url="https://www.facebook.com/v19.0/dialog/oauth",
        token_url="https://graph.facebook.com/v19.0/oauth/access_token",
        scope="ads_read,ads_management",
        client_id_env="META_APP_ID",
        client_secret_env="META_APP_SECRET",
        token_to_source_config={"access_token": "access_token"},
    ),
    "google_ads": PlatformOAuthConfig(
        auth_url="https://accounts.google.com/o/oauth2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="https://www.googleapis.com/auth/adwords",
        client_id_env="GOOGLE_CLIENT_ID",
        client_secret_env="GOOGLE_CLIENT_SECRET",
        token_to_source_config={
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        },
        extra_env_credentials={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "developer_token",
            "GOOGLE_CLIENT_ID": "client_id",
            "GOOGLE_CLIENT_SECRET": "client_secret",
        },
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    "tiktok_ads": PlatformOAuthConfig(
        auth_url="https://business-api.tiktok.com/portal/auth",
        token_url="https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/",
        scope="",
        client_id_env="TIKTOK_APP_ID",
        client_secret_env="TIKTOK_APP_SECRET",
        token_to_source_config={"access_token": "access_token"},
    ),
    # Shopify and Shopify Email share the same OAuth config.
    # {shop_domain} is interpolated at runtime from the request.
    "shopify": _SHOPIFY_OAUTH_CONFIG,
    "shopify_email": _SHOPIFY_OAUTH_CONFIG,
    "snapchat_ads": PlatformOAuthConfig(
        auth_url="https://accounts.snapchat.com/login/oauth2/authorize",
        token_url="https://accounts.snapchat.com/login/oauth2/access_token",
        scope="snapchat-marketing-api",
        client_id_env="SNAPCHAT_CLIENT_ID",
        client_secret_env="SNAPCHAT_CLIENT_SECRET",
        token_to_source_config={
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        },
        extra_env_credentials={
            "SNAPCHAT_CLIENT_ID": "client_id",
            "SNAPCHAT_CLIENT_SECRET": "client_secret",
        },
    ),
    "pinterest_ads": PlatformOAuthConfig(
        auth_url="https://www.pinterest.com/oauth/",
        token_url="https://api.pinterest.com/v5/oauth/token",
        scope="ads:read",
        client_id_env="PINTEREST_APP_ID",
        client_secret_env="PINTEREST_APP_SECRET",
        token_to_source_config={
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        },
    ),
    "twitter_ads": PlatformOAuthConfig(
        auth_url="https://twitter.com/i/oauth2/authorize",
        token_url="https://api.twitter.com/2/oauth2/token",
        scope="tweet.read users.read offline.access ads:read",
        client_id_env="TWITTER_CLIENT_ID",
        client_secret_env="TWITTER_CLIENT_SECRET",
        token_to_source_config={
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        },
    ),
}


def _get_config(platform: str) -> PlatformOAuthConfig:
    """Return the OAuth config for a platform, raising 400 if unknown."""
    config = OAUTH_REGISTRY.get(platform)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth not supported for platform: {platform}",
        )
    return config


def _get_client_id(config: PlatformOAuthConfig) -> str:
    """Return the client ID from env, raising 502 if not configured."""
    client_id = os.getenv(config.client_id_env)
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OAuth credentials not configured: missing {config.client_id_env}",
        )
    return client_id


def build_auth_url(
    platform: str,
    state: str,
    redirect_uri: str,
    shop_domain: Optional[str] = None,
) -> str:
    """
    Build the OAuth authorization URL for a platform.

    Args:
        platform: Platform key (e.g. "meta_ads", "google_ads")
        state: CSRF state token
        redirect_uri: Callback URL registered with the platform
        shop_domain: Required for shopify/shopify_email platforms

    Returns:
        Fully-formed authorization URL

    Raises:
        HTTPException 400: If platform is unknown
        HTTPException 502: If platform OAuth credentials are not configured
    """
    config = _get_config(platform)
    client_id = _get_client_id(config)

    auth_url = config.auth_url
    if shop_domain:
        shop_domain = validate_shop_domain(shop_domain)
        auth_url = auth_url.format(shop_domain=shop_domain)

    params: Dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
    }
    if config.scope:
        params["scope"] = config.scope

    params.update(config.extra_auth_params)

    # TikTok uses app_id instead of client_id
    if platform == "tiktok_ads":
        params.pop("client_id", None)
        params["app_id"] = client_id
        params.pop("response_type", None)  # TikTok doesn't use response_type

    return f"{auth_url}?{urlencode(params)}"


async def exchange_code_for_tokens(
    platform: str,
    code: str,
    redirect_uri: str,
    shop_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchange an OAuth authorization code for access/refresh tokens.

    Makes an async HTTP request to the platform's token endpoint.

    Args:
        platform: Platform key (e.g. "meta_ads", "google_ads")
        code: Authorization code from the OAuth callback
        redirect_uri: Same redirect URI used during authorization
        shop_domain: Required for shopify/shopify_email platforms

    Returns:
        Token response dict (contains at minimum "access_token")

    Raises:
        HTTPException 400: If platform is unknown
        HTTPException 502: If credentials not configured or token exchange fails
    """
    config = _get_config(platform)
    client_id = _get_client_id(config)
    client_secret = os.getenv(config.client_secret_env, "")

    token_url = config.token_url
    if shop_domain:
        shop_domain = validate_shop_domain(shop_domain)
        token_url = token_url.format(shop_domain=shop_domain)

    # Build the token exchange payload
    if platform == "tiktok_ads":
        # TikTok uses different field names
        payload = {
            "app_id": client_id,
            "secret": client_secret,
            "auth_code": code,
        }
    elif platform in ("shopify", "shopify_email"):
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
    else:
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            # Meta uses GET, others use POST
            if platform == "meta_ads":
                response = await http.get(token_url, params=payload)
            else:
                response = await http.post(token_url, json=payload)

        if response.status_code != 200:
            logger.error(
                "Token exchange failed",
                extra={
                    "platform": platform,
                    "status_code": response.status_code,
                    "response": response.text[:200],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to exchange OAuth code with {platform}",
            )

        return response.json()

    except httpx.RequestError as exc:
        logger.error(
            "Token exchange request error",
            extra={"platform": platform, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error during {platform} token exchange",
        )


# Platforms that require a separate account-selection step before the Airbyte
# source can be created.  After exchanging the OAuth code we call discover_accounts()
# to list available accounts, then the user picks one, and finalize_oauth() creates
# the Airbyte source with the chosen account_id.
PLATFORMS_NEEDING_ACCOUNT_SELECTION: set = {"meta_ads"}


async def discover_accounts(platform: str, tokens: Dict[str, Any]) -> list:
    """
    Discover ad accounts available to the authenticated user after OAuth.

    Returns a list of dicts with 'id' and 'name' keys.

    Currently only implemented for meta_ads (Facebook Marketing API).
    Other platforms return an empty list.

    Raises:
        HTTPException 502: If the Graph API call fails.
    """
    if platform != "meta_ads":
        return []

    access_token = tokens.get("access_token", "")
    if not access_token:
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.get(
                "https://graph.facebook.com/v19.0/me/adaccounts",
                params={
                    "fields": "id,name,account_status",
                    "access_token": access_token,
                },
            )

        if response.status_code != 200:
            logger.error(
                "Failed to discover Meta ad accounts",
                extra={
                    "status_code": response.status_code,
                    "response": response.text[:200],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to retrieve your Meta ad accounts. Please try again.",
            )

        data = response.json()
        accounts = []
        for acct in data.get("data", []):
            accounts.append({"id": acct.get("id", ""), "name": acct.get("name", "")})
        return accounts

    except httpx.RequestError as exc:
        logger.error(
            "Network error discovering Meta ad accounts",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Network error while retrieving ad accounts. Please try again.",
        )


def build_source_config(platform: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the Airbyte source configuration from OAuth token response + env vars.

    Maps token response fields and app-level env var credentials into the
    configuration dict that Airbyte's create_source endpoint expects.

    Args:
        platform: Platform key (e.g. "meta_ads", "google_ads")
        tokens: Token response dict from exchange_code_for_tokens()

    Returns:
        Source configuration dict for Airbyte create_source call
    """
    config = _get_config(platform)

    # Map token response fields to source config fields
    source_config: Dict[str, Any] = {}
    for token_field, config_field in config.token_to_source_config.items():
        if token_field in tokens:
            source_config[config_field] = tokens[token_field]
        # TikTok nests access_token in data.access_token
        elif "data" in tokens and token_field in tokens["data"]:
            source_config[config_field] = tokens["data"][token_field]

    # Inject additional app-level env var credentials
    for env_var, config_field in config.extra_env_credentials.items():
        value = os.getenv(env_var)
        if value:
            source_config[config_field] = value

    return source_config
