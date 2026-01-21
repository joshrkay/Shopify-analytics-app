"""
Feature flags tests for AI Growth Analytics.

CRITICAL: These tests verify that feature flags can disable functionality,
especially AI write-back features (kill switch requirement).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.testclient import TestClient

from src.platform.feature_flags import (
    FeatureFlag,
    LaunchDarklyClient,
    get_feature_flag_client,
    is_feature_enabled,
    is_kill_switch_active,
    require_feature_flag,
    require_kill_switch_inactive,
    check_feature_or_raise,
)
from src.platform.tenant_context import TenantContext, TenantContextMiddleware


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_ld_client():
    """Create a mock LaunchDarkly client."""
    client = LaunchDarklyClient()
    client._initialized = True
    client._client = Mock()
    return client


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("FRONTEGG_CLIENT_ID", "test-client-id")


@pytest.fixture
def mock_tenant_context():
    """Create a mock tenant context."""
    return TenantContext(
        tenant_id="tenant-123",
        user_id="user-456",
        roles=["admin"],
        org_id="tenant-123"
    )


# ============================================================================
# TEST SUITE: FEATURE FLAG ENUMERATION
# ============================================================================

class TestFeatureFlagEnumeration:
    """Test feature flag definitions."""

    def test_ai_write_back_flag_exists(self):
        """CRITICAL: AI write-back kill switch flag must exist."""
        assert FeatureFlag.AI_WRITE_BACK
        assert FeatureFlag.AI_WRITE_BACK.value == "ai-write-back"

    def test_all_ai_flags_defined(self):
        """All AI feature flags must be defined."""
        assert FeatureFlag.AI_INSIGHTS
        assert FeatureFlag.AI_WRITE_BACK
        assert FeatureFlag.AI_AUTOMATION

    def test_operational_flags_defined(self):
        """Operational flags for emergencies must be defined."""
        assert FeatureFlag.MAINTENANCE_MODE
        assert FeatureFlag.RATE_LIMITING_STRICT

    def test_feature_flag_values_follow_convention(self):
        """Feature flag values should be kebab-case."""
        for flag in FeatureFlag:
            # Values should be lowercase with hyphens
            assert flag.value == flag.value.lower()
            assert "_" not in flag.value  # Use hyphens, not underscores


# ============================================================================
# TEST SUITE: LAUNCHDARKLY CLIENT
# ============================================================================

class TestLaunchDarklyClient:
    """Test LaunchDarkly client wrapper."""

    def test_client_returns_default_when_not_configured(self, monkeypatch):
        """Client returns default value when LaunchDarkly not configured."""
        # Remove any SDK key
        monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

        client = LaunchDarklyClient()
        result = client.is_enabled(
            FeatureFlag.AI_WRITE_BACK,
            tenant_id="tenant-123",
            default=False
        )

        # Without configuration, should return default
        assert result is False

    def test_client_returns_default_on_error(self, mock_ld_client):
        """Client returns default value on evaluation error."""
        mock_ld_client._client.variation.side_effect = Exception("LD error")

        result = mock_ld_client.is_enabled(
            FeatureFlag.AI_WRITE_BACK,
            tenant_id="tenant-123",
            default=True
        )

        # On error, should return default
        assert result is True

    def test_client_builds_user_context_correctly(self, mock_ld_client):
        """Client builds LaunchDarkly user context with tenant and user info."""
        mock_ld_client._client.variation.return_value = True

        mock_ld_client.is_enabled(
            FeatureFlag.AI_WRITE_BACK,
            tenant_id="tenant-123",
            user_id="user-456",
        )

        # Verify variation was called with correct context
        call_args = mock_ld_client._client.variation.call_args
        user_context = call_args[0][1]  # Second positional arg is user context

        assert user_context["key"] == "tenant-123"
        assert user_context["secondary"] == "user-456"
        assert user_context["custom"]["tenant_id"] == "tenant-123"
        assert user_context["custom"]["user_id"] == "user-456"


# ============================================================================
# TEST SUITE: FEATURE FLAG FUNCTIONS
# ============================================================================

class TestFeatureFlagFunctions:
    """Test feature flag checking functions."""

    @pytest.mark.asyncio
    async def test_is_feature_enabled_returns_bool(self, monkeypatch):
        """is_feature_enabled returns boolean."""
        monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

        result = await is_feature_enabled(
            FeatureFlag.AI_WRITE_BACK,
            tenant_id="tenant-123",
            default=True
        )

        assert isinstance(result, bool)
        assert result is True  # Default value

    @pytest.mark.asyncio
    async def test_is_kill_switch_active_global_check(self, monkeypatch):
        """is_kill_switch_active checks global flag status."""
        monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

        # Without LD configured, should return False (not active, using default True)
        result = await is_kill_switch_active(FeatureFlag.AI_WRITE_BACK)

        # Kill switch active = feature disabled
        # Default is True for kill switch check, so not active
        assert result is False


# ============================================================================
# TEST SUITE: FEATURE FLAG DECORATORS
# ============================================================================

class TestFeatureFlagDecorators:
    """Test feature flag decorator functions."""

    @pytest.fixture
    def app_with_feature_flags(self):
        """Create FastAPI app with feature-flagged endpoints."""
        app = FastAPI()
        middleware = TenantContextMiddleware()
        app.middleware("http")(middleware)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/api/ai/execute")
        @require_feature_flag(FeatureFlag.AI_WRITE_BACK, default=False)
        async def execute_ai_action(request: Request):
            return {"executed": True}

        @app.post("/api/ai/write")
        @require_kill_switch_inactive(FeatureFlag.AI_WRITE_BACK)
        async def ai_write_action(request: Request):
            return {"written": True}

        @app.get("/api/insights")
        @require_feature_flag(FeatureFlag.AI_INSIGHTS, default=True)
        async def get_insights(request: Request):
            return {"insights": "data"}

        return app

    @pytest.mark.asyncio
    @patch('src.platform.tenant_context.jwt.decode')
    @patch('src.platform.tenant_context.FronteggJWKSClient.get_signing_key')
    @patch('src.platform.feature_flags.is_feature_enabled')
    async def test_require_feature_flag_blocks_when_disabled(
        self,
        mock_is_enabled,
        mock_get_signing_key,
        mock_jwt_decode,
        app_with_feature_flags
    ):
        """CRITICAL: require_feature_flag blocks access when flag is disabled."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"
        mock_get_signing_key.return_value = mock_signing_key

        mock_jwt_decode.return_value = {
            "org_id": "tenant-123",
            "sub": "user-456",
            "roles": ["admin"],
            "aud": "test-client-id",
            "iss": "https://api.frontegg.com",
            "exp": 9999999999,
        }

        # Feature is disabled
        mock_is_enabled.return_value = False

        client = TestClient(app_with_feature_flags)
        response = client.post(
            "/api/ai/execute",
            headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 503
        assert "disabled" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch('src.platform.tenant_context.jwt.decode')
    @patch('src.platform.tenant_context.FronteggJWKSClient.get_signing_key')
    @patch('src.platform.feature_flags.is_feature_enabled')
    async def test_require_feature_flag_allows_when_enabled(
        self,
        mock_is_enabled,
        mock_get_signing_key,
        mock_jwt_decode,
        app_with_feature_flags
    ):
        """require_feature_flag allows access when flag is enabled."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"
        mock_get_signing_key.return_value = mock_signing_key

        mock_jwt_decode.return_value = {
            "org_id": "tenant-123",
            "sub": "user-456",
            "roles": ["admin"],
            "aud": "test-client-id",
            "iss": "https://api.frontegg.com",
            "exp": 9999999999,
        }

        # Feature is enabled
        mock_is_enabled.return_value = True

        client = TestClient(app_with_feature_flags)
        response = client.post(
            "/api/ai/execute",
            headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch('src.platform.tenant_context.jwt.decode')
    @patch('src.platform.tenant_context.FronteggJWKSClient.get_signing_key')
    @patch('src.platform.feature_flags.is_kill_switch_active')
    async def test_require_kill_switch_inactive_blocks_when_active(
        self,
        mock_kill_switch,
        mock_get_signing_key,
        mock_jwt_decode,
        app_with_feature_flags
    ):
        """CRITICAL: Kill switch blocks all access when active."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"
        mock_get_signing_key.return_value = mock_signing_key

        mock_jwt_decode.return_value = {
            "org_id": "tenant-123",
            "sub": "user-456",
            "roles": ["admin"],
            "aud": "test-client-id",
            "iss": "https://api.frontegg.com",
            "exp": 9999999999,
        }

        # Kill switch is ACTIVE (feature should be blocked)
        mock_kill_switch.return_value = True

        client = TestClient(app_with_feature_flags)
        response = client.post(
            "/api/ai/write",
            headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 503


# ============================================================================
# TEST SUITE: PROGRAMMATIC CHECKS
# ============================================================================

class TestProgrammaticFeatureChecks:
    """Test programmatic feature flag checking."""

    @pytest.mark.asyncio
    @patch('src.platform.feature_flags.is_feature_enabled')
    async def test_check_feature_or_raise_passes(self, mock_is_enabled):
        """check_feature_or_raise passes when feature is enabled."""
        mock_is_enabled.return_value = True

        # Should not raise
        await check_feature_or_raise(
            FeatureFlag.AI_INSIGHTS,
            tenant_id="tenant-123",
            user_id="user-456"
        )

    @pytest.mark.asyncio
    @patch('src.platform.feature_flags.is_feature_enabled')
    async def test_check_feature_or_raise_raises(self, mock_is_enabled):
        """check_feature_or_raise raises when feature is disabled."""
        mock_is_enabled.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await check_feature_or_raise(
                FeatureFlag.AI_INSIGHTS,
                tenant_id="tenant-123",
                user_id="user-456"
            )

        assert exc_info.value.status_code == 503


# ============================================================================
# TEST SUITE: KILL SWITCH REQUIREMENTS
# ============================================================================

class TestKillSwitchRequirements:
    """Test kill switch specific requirements."""

    def test_ai_write_back_has_kill_switch(self):
        """CRITICAL: AI write-back must have a kill switch flag."""
        # The flag exists
        assert FeatureFlag.AI_WRITE_BACK is not None

        # It's a distinct flag that can be toggled
        assert FeatureFlag.AI_WRITE_BACK.value != ""

    def test_kill_switch_flag_names_are_clear(self):
        """Kill switch flags should have clear names."""
        # AI write-back is clearly named
        assert "write" in FeatureFlag.AI_WRITE_BACK.value.lower()

    @pytest.mark.asyncio
    @patch('src.platform.feature_flags._client')
    async def test_kill_switch_uses_global_context(self, mock_client):
        """Kill switch check should use global tenant context."""
        mock_client.is_enabled.return_value = False

        await is_kill_switch_active(FeatureFlag.AI_WRITE_BACK)

        # Verify it was called with __global__ tenant
        mock_client.is_enabled.assert_called_once()
        call_args = mock_client.is_enabled.call_args
        assert call_args[1]["tenant_id"] == "__global__"


# ============================================================================
# TEST SUITE: DEFAULT VALUES
# ============================================================================

class TestFeatureFlagDefaults:
    """Test feature flag default value behavior."""

    @pytest.mark.asyncio
    async def test_default_false_blocks_access(self, monkeypatch):
        """When default is False and LD unavailable, feature is disabled."""
        monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

        result = await is_feature_enabled(
            FeatureFlag.AI_WRITE_BACK,
            tenant_id="tenant-123",
            default=False
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_default_true_allows_access(self, monkeypatch):
        """When default is True and LD unavailable, feature is enabled."""
        monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)

        result = await is_feature_enabled(
            FeatureFlag.AI_INSIGHTS,
            tenant_id="tenant-123",
            default=True
        )

        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
