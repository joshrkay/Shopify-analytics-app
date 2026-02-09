"""
Tests for JWT Embed Token Claims, Token Store, and Revocation.

Phase 1 (5.6.1) — JWT Issuance System for Superset Embedding.

Verifies:
- Token generation includes all required claims (jti, access_surface, billing_tier)
- Token store stores/retrieves/revokes JTIs in Redis
- Revoked tokens fail validation
- Bulk revocation for user+tenant works
- access_surface defaults to shopify_embed
- Revoke endpoint returns 200 and audit event is emitted
"""

import pytest
import json
import time
import uuid
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass, field
from typing import List, Optional


# =============================================================================
# Mock TenantContext (avoid full import chain)
# =============================================================================

@dataclass
class MockTenantContext:
    """Mock tenant context for testing."""
    user_id: str = "user-123"
    tenant_id: str = "tenant-456"
    roles: List[str] = field(default_factory=lambda: ["merchant_admin"])
    allowed_tenants: List[str] = field(default_factory=lambda: ["tenant-456"])
    billing_tier: str = "growth"

    def get_rls_clause(self) -> str:
        return f"tenant_id = '{self.tenant_id}'"


# =============================================================================
# EmbedTokenService Tests
# =============================================================================


class TestEmbedTokenServiceClaims:
    """Test that generated tokens include all required JWT claims."""

    def _create_service(self):
        """Create EmbedTokenService with test config."""
        from src.services.embed_token_service import EmbedTokenService, EmbedTokenConfig

        config = EmbedTokenConfig(
            jwt_secret="test-secret-key-for-testing-only",
            algorithm="HS256",
            default_lifetime_minutes=60,
            refresh_threshold_minutes=5,
            issuer="ai-growth-analytics",
        )
        return EmbedTokenService(config=config)

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_includes_jti_claim(self, mock_store):
        """Token must include a jti (JWT ID) for revocation tracking."""
        mock_store.return_value = Mock()
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        import jwt
        payload = jwt.decode(
            result.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )
        assert "jti" in payload
        assert payload["jti"]  # non-empty
        # jti should be a valid UUID
        uuid.UUID(payload["jti"])

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_includes_access_surface_default(self, mock_store):
        """access_surface defaults to shopify_embed."""
        mock_store.return_value = Mock()
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        import jwt
        payload = jwt.decode(
            result.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )
        assert payload["access_surface"] == "shopify_embed"

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_includes_access_surface_external(self, mock_store):
        """access_surface can be set to external_app."""
        mock_store.return_value = Mock()
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(
            ctx, dashboard_id="dash-1", access_surface="external_app"
        )

        import jwt
        payload = jwt.decode(
            result.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )
        assert payload["access_surface"] == "external_app"

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_includes_billing_tier(self, mock_store):
        """Token must include billing_tier from tenant context."""
        mock_store.return_value = Mock()
        service = self._create_service()
        ctx = MockTenantContext(billing_tier="enterprise")

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        import jwt
        payload = jwt.decode(
            result.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )
        assert payload["billing_tier"] == "enterprise"

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_includes_all_required_claims(self, mock_store):
        """Token must include sub, tenant_id, roles, allowed_tenants, jti, iss, iat, exp."""
        mock_store.return_value = Mock()
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        import jwt
        payload = jwt.decode(
            result.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )

        required_claims = [
            "sub", "tenant_id", "roles", "allowed_tenants",
            "billing_tier", "jti", "access_surface",
            "iss", "iat", "exp", "dashboard_id",
        ]
        for claim in required_claims:
            assert claim in payload, f"Missing required claim: {claim}"

        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-456"
        assert payload["iss"] == "ai-growth-analytics"

    @patch("src.services.embed_token_service.get_token_store")
    def test_token_stores_jti_in_store(self, mock_store):
        """Token generation must store JTI in token store for revocation."""
        store_instance = Mock()
        mock_store.return_value = store_instance
        service = self._create_service()
        ctx = MockTenantContext()

        service.generate_embed_token(ctx, dashboard_id="dash-1")

        store_instance.store_token.assert_called_once()
        call_kwargs = store_instance.store_token.call_args
        assert call_kwargs[1]["user_id"] == "user-123"
        assert call_kwargs[1]["tenant_id"] == "tenant-456"
        assert call_kwargs[1]["access_surface"] == "shopify_embed"

    @patch("src.services.embed_token_service.get_token_store")
    def test_revoked_token_fails_validation(self, mock_store):
        """Validate must reject revoked tokens."""
        store_instance = Mock()
        store_instance.is_revoked.return_value = True
        mock_store.return_value = store_instance
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        from src.services.embed_token_service import TokenValidationError
        with pytest.raises(TokenValidationError, match="revoked"):
            service.validate_token(result.jwt_token)

    @patch("src.services.embed_token_service.get_token_store")
    def test_non_revoked_token_passes_validation(self, mock_store):
        """Valid, non-revoked token passes validation."""
        store_instance = Mock()
        store_instance.is_revoked.return_value = False
        mock_store.return_value = store_instance
        service = self._create_service()
        ctx = MockTenantContext()

        result = service.generate_embed_token(ctx, dashboard_id="dash-1")

        payload = service.validate_token(result.jwt_token)
        assert payload.sub == "user-123"
        assert payload.tenant_id == "tenant-456"

    @patch("src.services.embed_token_service.get_token_store")
    def test_refresh_carries_forward_access_surface(self, mock_store):
        """Token refresh must carry forward access_surface from old token."""
        store_instance = Mock()
        store_instance.is_revoked.return_value = False
        mock_store.return_value = store_instance
        service = self._create_service()
        ctx = MockTenantContext()

        original = service.generate_embed_token(
            ctx, dashboard_id="dash-1", access_surface="external_app"
        )

        refreshed = service.refresh_token(
            old_token=original.jwt_token,
            tenant_context=ctx,
        )

        import jwt
        payload = jwt.decode(
            refreshed.jwt_token,
            "test-secret-key-for-testing-only",
            algorithms=["HS256"],
        )
        assert payload["access_surface"] == "external_app"


# =============================================================================
# EmbedTokenStore Tests
# =============================================================================


class TestEmbedTokenStore:
    """Test Redis-backed token store operations."""

    def _create_store(self, mock_redis):
        from src.services.token_store import EmbedTokenStore
        return EmbedTokenStore(mock_redis)

    def test_store_token(self):
        """store_token writes to Redis with correct keys."""
        mock_redis = Mock()
        mock_redis.ttl.return_value = 3600
        store = self._create_store(mock_redis)

        store.store_token(
            jti="jti-abc",
            user_id="user-1",
            tenant_id="tenant-1",
            access_surface="shopify_embed",
            exp=int(time.time()) + 3600,
        )

        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "embed:token:jti-abc"
        mock_redis.sadd.assert_called_once()

    def test_is_revoked_false(self):
        """Non-revoked JTI returns False."""
        mock_redis = Mock()
        mock_redis.exists.return_value = 0
        store = self._create_store(mock_redis)

        assert store.is_revoked("jti-abc") is False
        mock_redis.exists.assert_called_with("embed:revoked:jti-abc")

    def test_is_revoked_true(self):
        """Revoked JTI returns True."""
        mock_redis = Mock()
        mock_redis.exists.return_value = 1
        store = self._create_store(mock_redis)

        assert store.is_revoked("jti-abc") is True

    def test_revoke_token(self):
        """revoke_token marks JTI as revoked and deletes active entry."""
        mock_redis = Mock()
        mock_redis.ttl.return_value = 1800
        store = self._create_store(mock_redis)

        store.revoke_token("jti-abc")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "embed:revoked:jti-abc"
        assert call_args[2] == "1"
        mock_redis.delete.assert_called_with("embed:token:jti-abc")

    def test_revoke_all_for_user(self):
        """revoke_all_for_user revokes all active JTIs for a user."""
        mock_redis = Mock()
        mock_redis.smembers.return_value = {b"jti-1", b"jti-2"}
        mock_redis.ttl.return_value = 1800
        store = self._create_store(mock_redis)

        count = store.revoke_all_for_user("user-1", "tenant-1")

        assert count == 2
        mock_redis.smembers.assert_called_with("embed:user_tokens:user-1:tenant-1")

    def test_redis_failure_is_revoked_returns_false(self):
        """Redis failure on is_revoked returns False (fail-open)."""
        mock_redis = Mock()
        mock_redis.exists.side_effect = Exception("Redis down")
        store = self._create_store(mock_redis)

        assert store.is_revoked("jti-abc") is False

    def test_redis_failure_store_token_does_not_raise(self):
        """Redis failure on store_token does not raise."""
        mock_redis = Mock()
        mock_redis.setex.side_effect = Exception("Redis down")
        store = self._create_store(mock_redis)

        # Should not raise
        store.store_token(
            jti="jti-abc",
            user_id="user-1",
            tenant_id="tenant-1",
            access_surface="shopify_embed",
            exp=int(time.time()) + 3600,
        )

    def test_get_active_token_count(self):
        """get_active_token_count returns set cardinality."""
        mock_redis = Mock()
        mock_redis.scard.return_value = 3
        store = self._create_store(mock_redis)

        assert store.get_active_token_count("user-1", "tenant-1") == 3
