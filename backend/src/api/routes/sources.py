"""
Unified Sources API routes for data source connections.

Provides:
- GET /api/sources — List all connected sources
- GET /api/sources/catalog — Available source definitions
- POST /api/sources/{platform}/oauth/initiate — Start OAuth flow
- POST /api/sources/oauth/callback — Complete OAuth flow
- DELETE /api/sources/{source_id} — Disconnect a source
- POST /api/sources/{source_id}/test — Test a connection
- PATCH /api/sources/{source_id}/config — Update sync config
- GET /api/sources/sync-settings — Get global sync settings
- PUT /api/sources/sync-settings — Update global sync settings

SECURITY: All routes require valid tenant context from JWT.

Story 2.1.1 — Unified Source domain model
Phase 3 — Data Sources wizard backend routes
"""

import json
import logging
import os
import secrets
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, status, Depends

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.airbyte_service import (
    AirbyteService,
    ConnectionNotFoundServiceError,
    DuplicateConnectionError,
)
from src.services.ad_ingestion import AdPlatform, AIRBYTE_SOURCE_TYPES
from src.services.airbyte_workspace import ensure_tenant_workspace
from src.integrations.airbyte.client import get_airbyte_client, AirbyteError
from src.integrations.airbyte.models import (
    SourceCreationRequest,
    ConnectionCreationRequest,
    DestinationCreationRequest,
)
from src.integrations.airbyte.oauth_registry import (
    PLATFORMS_NEEDING_ACCOUNT_SELECTION,
    build_auth_url,
    build_source_config,
    discover_accounts,
    exchange_code_for_tokens,
    validate_shop_domain,
)
from src.api.schemas.sources import (
    SourceSummary,
    SourceListResponse,
    SourceCatalogEntry,
    SourceCatalogResponse,
    OAuthInitiateRequest,
    OAuthInitiateResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthFinalizeRequest,
    DiscoveredAccount,
    TestConnectionResponse,
    UpdateSyncConfigRequest,
    GlobalSyncSettingsResponse,
    UpdateGlobalSyncSettingsRequest,
    ApiKeyConnectRequest,
    ApiKeyConnectResponse,
    normalize_connection_to_source,
    PLATFORM_DISPLAY_NAMES,
    PLATFORM_AUTH_TYPE,
    PLATFORM_DESCRIPTIONS,
    PLATFORM_CATEGORIES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])

# =============================================================================
# OAuth URL builders per platform
# =============================================================================

OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    "https://app.localhost/api/sources/oauth/callback",
)

# OAuth state TTL in seconds (10 minutes)
OAUTH_STATE_TTL_SECONDS = 600

# Sync settings key prefix for Redis
_SYNC_SETTINGS_REDIS_PREFIX = "sync_settings:"
_SYNC_SETTINGS_TTL_SECONDS = 86400  # 24 hours


# =============================================================================
# Redis-backed OAuth state store with in-memory fallback
# =============================================================================

def _get_redis_client():
    """Get the singleton RedisClient. Returns None if unavailable."""
    try:
        from src.entitlements.cache import RedisClient
        client = RedisClient()
        if client.available:
            return client
    except Exception:
        pass
    return None


# In-memory fallback when Redis is unavailable
_oauth_state_store_fallback: dict[str, dict] = {}


def _store_oauth_state(state: str, data: dict) -> None:
    """Store OAuth state in Redis (with TTL) or in-memory fallback."""
    redis = _get_redis_client()
    if redis:
        redis.set(f"oauth_state:{state}", json.dumps(data), OAUTH_STATE_TTL_SECONDS)
    else:
        _oauth_state_store_fallback[state] = data


def _pop_oauth_state(state: str) -> Optional[dict]:
    """Retrieve and delete OAuth state from Redis or in-memory fallback."""
    redis = _get_redis_client()
    if redis:
        raw = redis.get(f"oauth_state:{state}")
        if raw:
            redis.delete(f"oauth_state:{state}")
            return json.loads(raw)
        return None
    return _oauth_state_store_fallback.pop(state, None)


# =============================================================================
# DB-backed sync settings helpers
# =============================================================================

_GLOBAL_SETTINGS_CONNECTION_NAME = "__global_sync_settings__"

DEFAULT_SYNC_SETTINGS = {
    "default_frequency": "hourly",
    "pause_all_syncs": False,
    "max_concurrent_syncs": 5,
}

FREQUENCY_TO_MINUTES = {
    "hourly": 60,
    "daily": 1440,
    "weekly": 10080,
}


def _get_sync_settings_from_db(service: AirbyteService) -> dict:
    """Load global sync settings from the DB via a sentinel connection record."""
    result = service.list_connections(
        connection_type="source",
    )
    for conn in result.connections:
        if conn.connection_name == _GLOBAL_SETTINGS_CONNECTION_NAME:
            # Settings stored in the sync_frequency_minutes field as JSON
            if conn.sync_frequency_minutes:
                try:
                    return json.loads(conn.sync_frequency_minutes)
                except (json.JSONDecodeError, TypeError):
                    pass
            break
    return DEFAULT_SYNC_SETTINGS.copy()


def _save_sync_settings_to_db(service: AirbyteService, settings: dict) -> None:
    """Persist global sync settings to the DB via a sentinel connection record."""
    result = service.list_connections(connection_type="source")
    sentinel_id = None
    for conn in result.connections:
        if conn.connection_name == _GLOBAL_SETTINGS_CONNECTION_NAME:
            sentinel_id = conn.id
            break

    settings_json = json.dumps(settings)

    if sentinel_id:
        # Update existing sentinel record's sync_frequency_minutes field
        connection = service._repository.get_by_id(sentinel_id)
        if connection:
            connection.sync_frequency_minutes = settings_json
            service.db.commit()
    else:
        # Create sentinel connection to hold settings
        service.register_connection(
            airbyte_connection_id=f"settings-{service.tenant_id[:16]}",
            connection_name=_GLOBAL_SETTINGS_CONNECTION_NAME,
            connection_type="source",
            source_type="settings",
            configuration={"type": "global_sync_settings"},
            sync_frequency_minutes=settings_json,
        )


# =============================================================================
# Airbyte source type mapping
# =============================================================================

# Maps our internal platform keys → Airbyte source type strings used in
# create_source calls (embedded as sourceType inside configuration).
PLATFORM_TO_AIRBYTE_SOURCE_TYPE: dict[str, str] = {
    "shopify": "source-shopify",
    "shopify_email": "source-shopify",
    "meta_ads": "source-facebook-marketing",
    "google_ads": "source-google-ads",
    "tiktok_ads": "source-tiktok-marketing",
    "snapchat_ads": "source-snapchat-marketing",
    "pinterest_ads": "source-pinterest-ads",
    "twitter_ads": "source-twitter-ads",
    # API-key platforms
    "klaviyo": "source-klaviyo",
    "attentive": "source-attentive",
    "postscript": "source-postscript",
    "smsbump": "source-smsbump",
}


def _resolve_airbyte_source_type(platform: str) -> Optional[str]:
    """Return the Airbyte source type string for a platform, or None."""
    return PLATFORM_TO_AIRBYTE_SOURCE_TYPE.get(platform)


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "",
    response_model=SourceListResponse,
)
async def list_sources(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    List all data source connections for the authenticated tenant.

    Returns a unified list of Shopify and ad platform connections,
    each normalized to a common Source schema.

    SECURITY: Only returns connections belonging to the tenant.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    result = service.list_connections(connection_type="source")

    sources: List[SourceSummary] = [
        normalize_connection_to_source(conn)
        for conn in result.connections
        if conn.status != "deleted"
        and conn.connection_name != _GLOBAL_SETTINGS_CONNECTION_NAME
    ]

    logger.info(
        "Listed unified sources",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "count": len(sources),
        },
    )

    return SourceListResponse(sources=sources, total=len(sources))


@router.get(
    "/catalog",
    response_model=SourceCatalogResponse,
)
async def get_source_catalog(request: Request):
    """
    Get the catalog of available data source definitions.

    Returns all supported platforms with their display names,
    descriptions, auth types, and categories.

    SECURITY: Requires valid tenant context.
    """
    get_tenant_context(request)

    entries = []
    for platform, display_name in PLATFORM_DISPLAY_NAMES.items():
        entries.append(
            SourceCatalogEntry(
                id=platform,
                platform=platform,
                display_name=display_name,
                description=PLATFORM_DESCRIPTIONS.get(platform, ""),
                auth_type=PLATFORM_AUTH_TYPE.get(platform, "api_key"),
                category=PLATFORM_CATEGORIES.get(platform, "other"),
                is_enabled=True,
            )
        )

    return SourceCatalogResponse(sources=entries, total=len(entries))


@router.post(
    "/{platform}/oauth/initiate",
    response_model=OAuthInitiateResponse,
)
async def initiate_oauth(
    request: Request,
    platform: str,
    body: Optional[OAuthInitiateRequest] = None,
    db_session=Depends(get_db_session),
):
    """
    Initiate OAuth authorization flow for a data source platform.

    Builds the provider's OAuth authorization URL directly using per-platform
    app credentials (META_APP_ID, GOOGLE_CLIENT_ID, etc.) from the environment.
    This app-managed approach works with both Airbyte OSS and Cloud — unlike
    Airbyte's own initiateOAuth endpoint which is Cloud-only.

    Ensures the tenant has an Airbyte workspace (provisioning one on first use)
    so the subsequent oauth_callback can create the source in the correct workspace.

    For Shopify, the request body must include ``shop_domain``.

    SECURITY: State token prevents CSRF. Requires valid tenant context.
    """
    tenant_ctx = get_tenant_context(request)

    # Validate platform supports OAuth
    auth_type = PLATFORM_AUTH_TYPE.get(platform)
    if auth_type != "oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' does not support OAuth. Auth type: {auth_type}",
        )

    shop_domain = body.shop_domain if body else None

    # Shopify requires shop domain for URL interpolation
    if platform in ("shopify", "shopify_email"):
        if not shop_domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="shop_domain is required for Shopify OAuth",
            )
        shop_domain = validate_shop_domain(shop_domain)

    # Ensure the tenant has an isolated Airbyte workspace (lazy provision)
    from src.models.tenant import Tenant
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_ctx.tenant_id).first()
    tenant_name = tenant.name if tenant else tenant_ctx.tenant_id
    workspace_id = await ensure_tenant_workspace(
        tenant_id=tenant_ctx.tenant_id,
        tenant_name=tenant_name,
        db=db_session,
    )

    # Generate CSRF state token and build the platform's authorization URL.
    # build_auth_url raises 400 if platform is unknown, 502 if credentials missing.
    state = secrets.token_urlsafe(32)
    auth_url = build_auth_url(platform, state, OAUTH_REDIRECT_URI, shop_domain=shop_domain)

    state_data: dict = {
        "tenant_id": tenant_ctx.tenant_id,
        "user_id": tenant_ctx.user_id,
        "platform": platform,
        "workspace_id": workspace_id,
    }
    if shop_domain:
        state_data["shop_domain"] = shop_domain
    _store_oauth_state(state, state_data)

    logger.info(
        "OAuth flow initiated",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "platform": platform,
            "workspace_id": workspace_id,
        },
    )

    return OAuthInitiateResponse(
        authorization_url=auth_url,
        state=state,
    )


@router.post(
    "/{platform}/api-key/connect",
    response_model=ApiKeyConnectResponse,
)
async def connect_api_key_source(
    request: Request,
    platform: str,
    body: ApiKeyConnectRequest,
    db_session=Depends(get_db_session),
):
    """
    Create a data source connection using an API key.

    For platforms that use API key authentication (Klaviyo, Attentive,
    Postscript, SMSBump), this endpoint accepts the API key, creates the
    Airbyte source and connection pipeline, and registers it with the
    tenant-scoped service.

    SECURITY: Requires valid tenant context. API key is passed directly
    to Airbyte (not stored by this service — Airbyte manages the credential).
    """
    tenant_ctx = get_tenant_context(request)

    # Validate platform uses API key auth
    auth_type = PLATFORM_AUTH_TYPE.get(platform)
    if auth_type != "api_key":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform '{platform}' does not use API key auth. Auth type: {auth_type}",
        )

    # Resolve Airbyte source type
    try:
        platform_enum = AdPlatform(platform)
        airbyte_source_type = AIRBYTE_SOURCE_TYPES.get(platform_enum)
    except ValueError:
        airbyte_source_type = None

    if not airbyte_source_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No Airbyte source type configured for platform: {platform}",
        )

    # Build Airbyte source config based on platform
    source_config: dict
    if platform == "klaviyo":
        source_config = {"api_key": body.api_key}
    elif platform in ("attentive", "postscript", "smsbump"):
        source_config = {"api_key": body.api_key}
    else:
        source_config = {"api_key": body.api_key}

    display = body.display_name or PLATFORM_DISPLAY_NAMES.get(platform, platform)

    try:
        airbyte_client = get_airbyte_client()

        source_request = SourceCreationRequest(
            name=f"{display} - {tenant_ctx.tenant_id[:8]}",
            source_type=airbyte_source_type,
            configuration=source_config,
        )
        source = await airbyte_client.create_source(source_request)

        destinations = await airbyte_client.list_destinations()
        destination_id = destinations[0].destination_id if destinations else None

        if not destination_id:
            logger.error(
                "No Airbyte destination available for API key connection",
                extra={"tenant_id": tenant_ctx.tenant_id, "platform": platform},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Data pipeline could not be established: no destination configured "
                    "in the sync workspace. Please contact support."
                ),
            )

        conn_request = ConnectionCreationRequest(
            source_id=source.source_id,
            destination_id=destination_id,
            name=f"{display} sync",
        )
        connection = await airbyte_client.create_connection(conn_request)

        service = AirbyteService(db_session, tenant_ctx.tenant_id)
        conn_info = service.register_connection(
            airbyte_connection_id=connection.connection_id,
            connection_name=display,
            connection_type="source",
            airbyte_source_id=source.source_id,
            source_type=airbyte_source_type,
            configuration={"platform": platform, "auth_type": "api_key"},
        )
        service.activate_connection(conn_info.id)

        logger.info(
            "API key source connected",
            extra={"tenant_id": tenant_ctx.tenant_id, "platform": platform, "connection_id": conn_info.id},
        )

        return ApiKeyConnectResponse(
            success=True,
            connection_id=conn_info.id,
            message=f"Successfully connected {display}",
        )

    except HTTPException:
        raise
    except DuplicateConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except AirbyteError as e:
        logger.error(
            "API key connect failed - Airbyte error",
            extra={"tenant_id": tenant_ctx.tenant_id, "platform": platform, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create source connection via Airbyte",
        )
    except Exception as e:
        logger.error(
            "API key connect failed",
            extra={"tenant_id": tenant_ctx.tenant_id, "platform": platform, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect source. Please try again.",
        )


@router.post(
    "/oauth/callback",
    response_model=OAuthCallbackResponse,
)
async def oauth_callback(
    request: Request,
    body: OAuthCallbackRequest,
    db_session=Depends(get_db_session),
):
    """
    Complete OAuth authorization flow.

    Validates the CSRF state token, exchanges the authorization code
    for access tokens, encrypts and stores credentials, and creates
    the Airbyte source connection.

    SECURITY: Validates state token matches initiating tenant.
    OAuth tokens are encrypted before storage.
    """
    tenant_ctx = get_tenant_context(request)

    # Validate state token
    state_data = _pop_oauth_state(body.state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state token",
        )

    if state_data["tenant_id"] != tenant_ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OAuth state does not match current tenant",
        )

    platform = state_data["platform"]
    shop_domain = state_data.get("shop_domain")
    # workspace_id was stored in state during initiate — retrieve it here.
    # If absent (legacy state entries), fall back to ensure_tenant_workspace.
    stored_workspace_id: Optional[str] = state_data.get("workspace_id")

    try:
        airbyte_source_type = _resolve_airbyte_source_type(platform)
        if not airbyte_source_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No Airbyte source type for platform: {platform}",
            )

        # Resolve the tenant's workspace — stored_workspace_id is set for
        # flows initiated after the per-tenant workspace refactor; the fallback
        # handles any in-flight legacy state entries.
        if stored_workspace_id:
            workspace_id = stored_workspace_id
        else:
            from src.models.tenant import Tenant
            tenant = db_session.query(Tenant).filter(
                Tenant.id == tenant_ctx.tenant_id
            ).first()
            tenant_name = tenant.name if tenant else tenant_ctx.tenant_id
            workspace_id = await ensure_tenant_workspace(
                tenant_id=tenant_ctx.tenant_id,
                tenant_name=tenant_name,
                db=db_session,
            )

        # Exchange the authorization code for tokens with the platform directly.
        tokens = await exchange_code_for_tokens(
            platform, body.code, OAUTH_REDIRECT_URI, shop_domain
        )

        # Platforms like Meta Ads require the merchant to select which ad account
        # to sync before we can create the Airbyte source (source-facebook-marketing
        # requires account_id).  For these platforms we:
        #   1. Call the platform API to discover available ad accounts
        #   2. Store the access token in Redis under a pending key
        #   3. Return discovered accounts + pending_token to the frontend
        #   4. The frontend shows account selection, then calls the finalize endpoint
        if platform in PLATFORMS_NEEDING_ACCOUNT_SELECTION:
            accounts = await discover_accounts(platform, tokens)

            pending_token = secrets.token_urlsafe(32)
            pending_data: dict = {
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "workspace_id": workspace_id,
                "tokens": tokens,
            }
            if shop_domain:
                pending_data["shop_domain"] = shop_domain
            _store_oauth_state(pending_token, pending_data)

            logger.info(
                "OAuth pending account selection",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "platform": platform,
                    "account_count": len(accounts),
                },
            )

            return OAuthCallbackResponse(
                success=True,
                connection_id="",
                message="Please select the ad account you want to connect",
                needs_account_selection=True,
                discovered_accounts=[
                    DiscoveredAccount(id=a["id"], name=a["name"]) for a in accounts
                ],
                pending_token=pending_token,
            )

        # Standard flow: create the Airbyte source immediately.
        source_config: dict = build_source_config(platform, tokens)
        if shop_domain:
            source_config["shop"] = shop_domain

        conn_info = await _create_airbyte_connection(
            tenant_ctx=tenant_ctx,
            platform=platform,
            airbyte_source_type=airbyte_source_type,
            workspace_id=workspace_id,
            source_config=source_config,
            shop_domain=shop_domain,
            db_session=db_session,
        )

        return OAuthCallbackResponse(
            success=True,
            connection_id=conn_info.id,
            message=f"Successfully connected {PLATFORM_DISPLAY_NAMES.get(platform, platform)}",
        )

    except HTTPException:
        raise
    except DuplicateConnectionError as e:
        logger.warning(
            "OAuth callback rejected — duplicate connection",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except AirbyteError as e:
        logger.error(
            "OAuth callback failed - Airbyte error",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create source connection via Airbyte",
        )
    except Exception as e:
        logger.error(
            "OAuth callback failed",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete authorization. Please try again.",
        )


async def _create_airbyte_connection(
    *,
    tenant_ctx,
    platform: str,
    airbyte_source_type: str,
    workspace_id: str,
    source_config: dict,
    shop_domain: Optional[str],
    db_session,
):
    """
    Shared helper: create an Airbyte source + connection and register it in our DB.

    Called from both oauth_callback (standard platforms) and finalize_oauth (Meta Ads
    and other platforms that require account selection before source creation).

    Returns the registered ConnectionInfo.
    """
    airbyte_client = get_airbyte_client()

    source_request = SourceCreationRequest(
        name=f"{PLATFORM_DISPLAY_NAMES.get(platform, platform)} - {tenant_ctx.tenant_id[:8]}",
        source_type=airbyte_source_type,
        configuration=source_config,
    )
    source = await airbyte_client.create_source(source_request, workspace_id=workspace_id)

    destinations = await airbyte_client.list_destinations(workspace_id=workspace_id)
    if not destinations:
        from src.services.airbyte_workspace import parse_db_connection_config
        dest_request = DestinationCreationRequest(
            name=f"PostgreSQL - {tenant_ctx.tenant_id[:8]}",
            destination_type="destination-postgres",
            configuration=parse_db_connection_config(),
        )
        dest = await airbyte_client.create_destination(dest_request, workspace_id=workspace_id)
        destinations = [dest]

    destination_id = destinations[0].destination_id

    conn_request = ConnectionCreationRequest(
        source_id=source.source_id,
        destination_id=destination_id,
        name=f"{PLATFORM_DISPLAY_NAMES.get(platform, platform)} sync",
    )
    connection = await airbyte_client.create_connection(conn_request)
    connection_id = connection.connection_id

    reg_config: dict = {"platform": platform}
    if shop_domain:
        reg_config["shop_domain"] = shop_domain

    service = AirbyteService(db_session, tenant_ctx.tenant_id)
    conn_info = service.register_connection(
        airbyte_connection_id=connection_id,
        connection_name=PLATFORM_DISPLAY_NAMES.get(platform, platform),
        connection_type="source",
        airbyte_source_id=source.source_id,
        source_type=airbyte_source_type,
        configuration=reg_config,
    )
    service.activate_connection(conn_info.id)

    logger.info(
        "Airbyte connection created and registered",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "platform": platform,
            "connection_id": conn_info.id,
        },
    )
    return conn_info


@router.post(
    "/{platform}/oauth/finalize",
    response_model=OAuthCallbackResponse,
)
async def finalize_oauth(
    request: Request,
    platform: str,
    body: OAuthFinalizeRequest,
    db_session=Depends(get_db_session),
):
    """
    Finalize OAuth for platforms that require account selection.

    Called after the merchant selects an ad account from the list returned
    by the OAuth callback.  Retrieves the stored access token, builds the
    Airbyte source config with the chosen account_id, and creates the source.

    Currently used for: meta_ads

    SECURITY: Validates pending_token belongs to the current tenant.
    """
    tenant_ctx = get_tenant_context(request)

    # Retrieve and validate the pending token stored during oauth_callback
    pending_data = _pop_oauth_state(body.pending_token)
    if not pending_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired pending OAuth token. Please reconnect.",
        )

    if pending_data.get("tenant_id") != tenant_ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pending OAuth token does not match current tenant",
        )

    stored_platform = pending_data.get("platform")
    if stored_platform != platform:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform mismatch: expected {platform}, got {stored_platform}",
        )

    tokens: dict = pending_data.get("tokens", {})
    workspace_id: str = pending_data.get("workspace_id", "")
    shop_domain: Optional[str] = pending_data.get("shop_domain")

    airbyte_source_type = _resolve_airbyte_source_type(platform)
    if not airbyte_source_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No Airbyte source type for platform: {platform}",
        )

    # Build source config from stored tokens + the selected account_id.
    # For Meta, account_id may be in 'act_123456789' format — Airbyte's
    # source-facebook-marketing accepts both with and without the 'act_' prefix.
    source_config: dict = build_source_config(platform, tokens)
    source_config["account_id"] = body.account_id
    if shop_domain:
        source_config["shop"] = shop_domain

    try:
        conn_info = await _create_airbyte_connection(
            tenant_ctx=tenant_ctx,
            platform=platform,
            airbyte_source_type=airbyte_source_type,
            workspace_id=workspace_id,
            source_config=source_config,
            shop_domain=shop_domain,
            db_session=db_session,
        )

        logger.info(
            "OAuth finalized after account selection",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "account_id": body.account_id,
                "connection_id": conn_info.id,
            },
        )

        return OAuthCallbackResponse(
            success=True,
            connection_id=conn_info.id,
            message=f"Successfully connected {PLATFORM_DISPLAY_NAMES.get(platform, platform)}",
        )

    except HTTPException:
        raise
    except DuplicateConnectionError as e:
        logger.warning(
            "OAuth finalize rejected — duplicate connection",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except AirbyteError as e:
        logger.error(
            "OAuth finalize failed - Airbyte error",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create source connection via Airbyte",
        )
    except Exception as e:
        logger.error(
            "OAuth finalize failed",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "platform": platform,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete connection setup. Please try again.",
        )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_source(
    request: Request,
    source_id: str,
    db_session=Depends(get_db_session),
):
    """
    Disconnect (soft delete) a data source.

    SECURITY: Only disconnects sources belonging to the authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    try:
        service.delete_connection(source_id)
    except ConnectionNotFoundServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    logger.info(
        "Source disconnected",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "source_id": source_id,
        },
    )


@router.post(
    "/{source_id}/test",
    response_model=TestConnectionResponse,
)
async def test_connection(
    request: Request,
    source_id: str,
    db_session=Depends(get_db_session),
):
    """
    Test a data source connection by running Airbyte's check_connection.

    Uses the airbyte_source_id (not the connection ID) to validate that
    the external platform credentials are still valid and reachable.

    SECURITY: Only tests connections belonging to the authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    connection = service.get_connection(source_id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    # Resolve the Airbyte source ID for the check_connection call.
    # The connection record stores the airbyte_source_id separately from
    # the airbyte_connection_id (which is the pipeline ID).
    raw_conn = service._repository.get_by_id(source_id)
    airbyte_source_id = (
        raw_conn.airbyte_source_id if raw_conn else None
    ) or connection.airbyte_connection_id

    try:
        airbyte_client = get_airbyte_client()
        result = await airbyte_client.check_source_connection(airbyte_source_id)

        check_status = result.get("status", "unknown")
        if check_status == "succeeded":
            return TestConnectionResponse(
                success=True,
                message="Connection is healthy",
                details={
                    "source_id": airbyte_source_id,
                    "status": "active",
                },
            )
        return TestConnectionResponse(
            success=False,
            message=result.get("message", "Connection check did not succeed"),
            details={"status": check_status},
        )
    except AirbyteError:
        return TestConnectionResponse(
            success=False,
            message="Connection test failed — unable to reach source",
        )


@router.patch(
    "/{source_id}/config",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_sync_config(
    request: Request,
    source_id: str,
    body: UpdateSyncConfigRequest,
    db_session=Depends(get_db_session),
):
    """
    Update sync configuration for a data source.

    SECURITY: Only updates connections belonging to the authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    connection = service.get_connection(source_id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}",
        )

    # Update sync frequency if provided
    if body.sync_frequency:
        minutes = FREQUENCY_TO_MINUTES.get(body.sync_frequency)
        if not minutes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid frequency: {body.sync_frequency}. Valid: hourly, daily, weekly",
            )
        service.update_sync_frequency(source_id, minutes)

    logger.info(
        "Source config updated",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "source_id": source_id,
            "sync_frequency": body.sync_frequency,
        },
    )


@router.get(
    "/sync-settings",
    response_model=GlobalSyncSettingsResponse,
)
async def get_global_sync_settings(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get global sync settings for the authenticated tenant.

    SECURITY: Requires valid tenant context.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    # Try Redis cache first
    redis = _get_redis_client()
    cache_key = f"{_SYNC_SETTINGS_REDIS_PREFIX}{tenant_ctx.tenant_id}"
    if redis:
        cached = redis.get(cache_key)
        if cached:
            try:
                return GlobalSyncSettingsResponse(**json.loads(cached))
            except (json.JSONDecodeError, TypeError):
                pass

    settings = _get_sync_settings_from_db(service)

    # Cache in Redis
    if redis:
        redis.set(cache_key, json.dumps(settings), _SYNC_SETTINGS_TTL_SECONDS)

    return GlobalSyncSettingsResponse(**settings)


@router.put(
    "/sync-settings",
    response_model=GlobalSyncSettingsResponse,
)
async def update_global_sync_settings(
    request: Request,
    body: UpdateGlobalSyncSettingsRequest,
    db_session=Depends(get_db_session),
):
    """
    Update global sync settings for the authenticated tenant.

    SECURITY: Requires valid tenant context.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    current = _get_sync_settings_from_db(service)

    if body.default_frequency is not None:
        if body.default_frequency not in FREQUENCY_TO_MINUTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid frequency: {body.default_frequency}. Valid: hourly, daily, weekly",
            )
        current["default_frequency"] = body.default_frequency

    if body.pause_all_syncs is not None:
        current["pause_all_syncs"] = body.pause_all_syncs

    if body.max_concurrent_syncs is not None:
        if body.max_concurrent_syncs < 1 or body.max_concurrent_syncs > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_concurrent_syncs must be between 1 and 20",
            )
        current["max_concurrent_syncs"] = body.max_concurrent_syncs

    _save_sync_settings_to_db(service, current)

    # Invalidate Redis cache
    redis = _get_redis_client()
    if redis:
        cache_key = f"{_SYNC_SETTINGS_REDIS_PREFIX}{tenant_ctx.tenant_id}"
        redis.set(cache_key, json.dumps(current), _SYNC_SETTINGS_TTL_SECONDS)

    logger.info(
        "Global sync settings updated",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "settings": current,
        },
    )

    return GlobalSyncSettingsResponse(**current)
