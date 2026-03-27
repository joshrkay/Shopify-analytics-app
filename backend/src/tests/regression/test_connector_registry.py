"""
Regression tests for the connector registry and platform mapping consistency.

Ensures that:
- All OAuth platforms have entries in the OAuth registry
- All platforms have Airbyte source type mappings
- Account selection platforms have discovery functions
- No duplicate Airbyte source types across platforms
- Platform constants are consistent across schemas and routes
"""

import pytest

from src.api.schemas.sources import (
    PLATFORM_AUTH_TYPE,
    PLATFORM_DISPLAY_NAMES,
    PLATFORM_DESCRIPTIONS,
    PLATFORM_CATEGORIES,
    SOURCE_TYPE_TO_PLATFORM,
)
from src.api.routes.sources import PLATFORM_TO_AIRBYTE_SOURCE_TYPE
from src.integrations.airbyte.oauth_registry import (
    OAUTH_REGISTRY,
    PLATFORMS_NEEDING_ACCOUNT_SELECTION,
    ACCOUNT_ID_CONFIG_FIELD,
)


class TestPlatformConsistency:
    """All platform constants must be consistent across modules."""

    def test_all_platforms_have_display_names(self):
        """Every platform in PLATFORM_AUTH_TYPE has a display name."""
        for platform in PLATFORM_AUTH_TYPE:
            assert platform in PLATFORM_DISPLAY_NAMES, (
                f"Platform '{platform}' in PLATFORM_AUTH_TYPE but missing from PLATFORM_DISPLAY_NAMES"
            )

    def test_all_platforms_have_descriptions(self):
        """Every platform has a description."""
        for platform in PLATFORM_DISPLAY_NAMES:
            assert platform in PLATFORM_DESCRIPTIONS, (
                f"Platform '{platform}' missing description"
            )

    def test_all_platforms_have_categories(self):
        """Every platform has a category."""
        for platform in PLATFORM_DISPLAY_NAMES:
            assert platform in PLATFORM_CATEGORIES, (
                f"Platform '{platform}' missing category"
            )

    def test_valid_categories(self):
        """All categories are valid known values."""
        valid_categories = {"ecommerce", "ads", "email", "sms", "analytics", "crm", "other"}
        for platform, category in PLATFORM_CATEGORIES.items():
            assert category in valid_categories, (
                f"Platform '{platform}' has unknown category: {category}"
            )

    def test_valid_auth_types(self):
        """All auth types are either 'oauth' or 'api_key'."""
        for platform, auth_type in PLATFORM_AUTH_TYPE.items():
            assert auth_type in ("oauth", "api_key"), (
                f"Platform '{platform}' has invalid auth_type: {auth_type}"
            )


class TestOAuthRegistryConsistency:
    """OAuth platforms must have registry entries for auth URL building."""

    def test_all_oauth_platforms_have_registry_entry(self):
        """Every platform with auth_type='oauth' has an entry in OAUTH_REGISTRY."""
        oauth_platforms = {p for p, t in PLATFORM_AUTH_TYPE.items() if t == "oauth"}
        for platform in oauth_platforms:
            # Some platforms may use a shared registry entry (e.g., shopify_email -> shopify)
            # Check if the platform itself or its base platform is in the registry
            if platform == "shopify_email":
                assert "shopify" in OAUTH_REGISTRY or platform in OAUTH_REGISTRY, (
                    f"OAuth platform '{platform}' has no OAUTH_REGISTRY entry"
                )
            else:
                assert platform in OAUTH_REGISTRY, (
                    f"OAuth platform '{platform}' has no OAUTH_REGISTRY entry"
                )

    def test_account_selection_platforms_are_oauth(self):
        """All platforms needing account selection must be OAuth."""
        for platform in PLATFORMS_NEEDING_ACCOUNT_SELECTION:
            assert PLATFORM_AUTH_TYPE.get(platform) == "oauth", (
                f"Account selection platform '{platform}' is not OAuth"
            )

    def test_account_selection_platforms_have_config_field(self):
        """All account selection platforms have an ACCOUNT_ID_CONFIG_FIELD entry."""
        for platform in PLATFORMS_NEEDING_ACCOUNT_SELECTION:
            assert platform in ACCOUNT_ID_CONFIG_FIELD, (
                f"Platform '{platform}' needs account selection but no ACCOUNT_ID_CONFIG_FIELD"
            )


class TestAirbyteSourceTypeMapping:
    """Every platform must map to a valid Airbyte source type."""

    def test_all_platforms_have_airbyte_source_type(self):
        """Every platform in PLATFORM_DISPLAY_NAMES has an Airbyte source mapping."""
        for platform in PLATFORM_DISPLAY_NAMES:
            # shopify_email shares the shopify source type
            if platform == "shopify_email":
                assert "shopify" in PLATFORM_TO_AIRBYTE_SOURCE_TYPE or \
                       platform in PLATFORM_TO_AIRBYTE_SOURCE_TYPE
            else:
                assert platform in PLATFORM_TO_AIRBYTE_SOURCE_TYPE, (
                    f"Platform '{platform}' has no Airbyte source type mapping"
                )

    def test_source_type_reverse_mapping_complete(self):
        """Every Airbyte source type in PLATFORM_TO_AIRBYTE_SOURCE_TYPE has a reverse
        mapping in SOURCE_TYPE_TO_PLATFORM."""
        for platform, source_type in PLATFORM_TO_AIRBYTE_SOURCE_TYPE.items():
            assert source_type in SOURCE_TYPE_TO_PLATFORM, (
                f"Airbyte source type '{source_type}' for platform '{platform}' "
                f"has no reverse mapping in SOURCE_TYPE_TO_PLATFORM"
            )

    def test_no_duplicate_airbyte_source_types(self):
        """No two different platforms should map to the same Airbyte source type,
        except Shopify variants which share source-shopify."""
        seen = {}
        for platform, source_type in PLATFORM_TO_AIRBYTE_SOURCE_TYPE.items():
            if source_type in seen:
                # Allow shopify + shopify_email to share source-shopify
                existing = seen[source_type]
                shopify_variants = {"shopify", "shopify_email"}
                if not ({platform, existing} <= shopify_variants):
                    pytest.fail(
                        f"Duplicate Airbyte source type '{source_type}': "
                        f"used by both '{existing}' and '{platform}'"
                    )
            seen[source_type] = platform

    def test_airbyte_source_types_follow_naming_convention(self):
        """All Airbyte source types start with 'source-'."""
        for platform, source_type in PLATFORM_TO_AIRBYTE_SOURCE_TYPE.items():
            assert source_type.startswith("source-"), (
                f"Platform '{platform}' has non-standard Airbyte source type: {source_type}"
            )


class TestPlatformCount:
    """Sanity check on platform counts to catch accidental removals."""

    def test_minimum_platform_count(self):
        """At least 12 platforms are defined (original 12 + new connectors)."""
        assert len(PLATFORM_DISPLAY_NAMES) >= 12

    def test_ad_platforms_present(self):
        """Core ad platforms are present."""
        required_ads = {"meta_ads", "google_ads", "tiktok_ads", "snapchat_ads", "pinterest_ads", "twitter_ads"}
        actual = set(PLATFORM_DISPLAY_NAMES.keys())
        missing = required_ads - actual
        assert not missing, f"Missing ad platforms: {missing}"

    def test_email_sms_platforms_present(self):
        """Email/SMS platforms are present."""
        required = {"klaviyo", "attentive"}
        actual = set(PLATFORM_DISPLAY_NAMES.keys())
        missing = required - actual
        assert not missing, f"Missing email/SMS platforms: {missing}"
