"""
Shared freshness SLA config loader and connector-to-source mapping.

Single source of truth for config/data_freshness_sla.yml. Used by
DataAvailabilityService, DQ service, and any API that needs per-tier thresholds.

SECURITY: Callers must enforce tenant scope; this module only reads config.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from src.governance.base import load_yaml_config

logger = logging.getLogger(__name__)

_SLA_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "data_freshness_sla.yml"
_sla_cache: Optional[dict] = None

# Default when source/tier missing: 24 h (warn and error equal)
_DEFAULT_WARN_MINUTES = 1440
_DEFAULT_ERROR_MINUTES = 1440


def load_sla_config() -> dict:
    """Load and cache SLA config. Raises FileNotFoundError if missing."""
    global _sla_cache
    if _sla_cache is None:
        _sla_cache = load_yaml_config(_SLA_CONFIG_PATH, logger=logger)
    return _sla_cache


def get_sla_thresholds(
    source_name: str,
    tier: str = "free",
) -> Tuple[int, int]:
    """
    Return (warn_after_minutes, error_after_minutes) for a source and tier.

    Falls back to the free tier, then to defaults (1440, 1440).
    """
    config = load_sla_config()
    default_tier = config.get("default_tier", "free")
    effective_tier = tier or default_tier

    sources = config.get("sources", {})
    source_cfg = sources.get(source_name, {})
    tier_cfg = source_cfg.get(effective_tier) or source_cfg.get("free") or {}

    warn = tier_cfg.get("warn_after_minutes", _DEFAULT_WARN_MINUTES)
    error = tier_cfg.get("error_after_minutes", _DEFAULT_ERROR_MINUTES)
    return warn, error


CONNECTOR_SOURCE_TO_SLA_KEY: Dict[str, str] = {
    "shopify": "shopify_orders",
    "facebook": "facebook_ads",
    "meta": "facebook_ads",
    "google": "google_ads",
    "tiktok": "tiktok_ads",
    "snapchat": "snapchat_ads",
    "klaviyo": "email",
    "shopify_email": "email",
    "attentive": "sms",
    "postscript": "sms",
    "smsbump": "sms",
}


def resolve_sla_key(connection_source_type: Optional[str]) -> Optional[str]:
    """Map a TenantAirbyteConnection.source_type to an SLA config key."""
    if not connection_source_type:
        return None
    return CONNECTOR_SOURCE_TO_SLA_KEY.get(connection_source_type.lower())
