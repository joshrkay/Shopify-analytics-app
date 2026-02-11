"""
Unified Source schemas for the Data Sources API.

Normalizes Shopify and ad platform connections into a single Source model.
Maps Airbyte source_type identifiers to platform keys and auth types.

Story 2.1.1 — Unified Source domain model
"""

from typing import Optional, List

from pydantic import BaseModel

from src.services.airbyte_service import ConnectionInfo


# =============================================================================
# Platform Mapping Constants
# =============================================================================

SOURCE_TYPE_TO_PLATFORM: dict[str, str] = {
    "shopify": "shopify",
    "source-shopify": "shopify",
    "source-facebook-marketing": "meta_ads",
    "source-google-ads": "google_ads",
    "source-tiktok-marketing": "tiktok_ads",
    "source-snapchat-marketing": "snapchat_ads",
    "source-klaviyo": "klaviyo",
    "source-attentive": "attentive",
    "source-postscript": "postscript",
    "source-smsbump": "smsbump",
}

PLATFORM_AUTH_TYPE: dict[str, str] = {
    "shopify": "oauth",
    "meta_ads": "oauth",
    "google_ads": "oauth",
    "tiktok_ads": "oauth",
    "snapchat_ads": "oauth",
    "klaviyo": "api_key",
    "shopify_email": "oauth",
    "attentive": "api_key",
    "postscript": "api_key",
    "smsbump": "api_key",
}

PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    "shopify": "Shopify",
    "meta_ads": "Meta Ads",
    "google_ads": "Google Ads",
    "tiktok_ads": "TikTok Ads",
    "snapchat_ads": "Snapchat Ads",
    "klaviyo": "Klaviyo",
    "shopify_email": "Shopify Email",
    "attentive": "Attentive",
    "postscript": "Postscript",
    "smsbump": "SMSBump",
}


# =============================================================================
# Response Models
# =============================================================================

class SourceSummary(BaseModel):
    """Unified source connection summary."""

    id: str
    platform: str
    display_name: str
    auth_type: str
    status: str
    is_enabled: bool
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None


class SourceListResponse(BaseModel):
    """Response for listing all sources."""

    sources: List[SourceSummary]
    total: int


# =============================================================================
# Normalizer
# =============================================================================

def normalize_connection_to_source(conn: ConnectionInfo) -> SourceSummary:
    """
    Normalize a ConnectionInfo (from AirbyteService) into a unified SourceSummary.

    Maps the Airbyte source_type to a platform key and derives auth_type.
    Works for both Shopify and ad platform connections.

    Args:
        conn: ConnectionInfo from AirbyteService.list_connections()

    Returns:
        SourceSummary with unified fields
    """
    platform = SOURCE_TYPE_TO_PLATFORM.get(
        conn.source_type or "", conn.source_type or "unknown"
    )
    auth_type = PLATFORM_AUTH_TYPE.get(platform, "api_key")
    display_name = conn.connection_name or PLATFORM_DISPLAY_NAMES.get(platform, platform)

    return SourceSummary(
        id=conn.id,
        platform=platform,
        display_name=display_name,
        auth_type=auth_type,
        status=conn.status,
        is_enabled=conn.is_enabled,
        last_sync_at=conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        last_sync_status=conn.last_sync_status,
    )
