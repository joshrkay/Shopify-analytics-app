"""
Unit tests for OAuth service.

Tests shop validation, state management, HMAC verification, and tenant derivation.
"""

import pytest
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.oauth_service import (
    OAuthService,
    OAuthError,
    InvalidShopDomainError,
    InvalidStateError,
    HMACVerificationError,
    TokenExchangeError,
)
from src.models.oauth_state import OAuthState
from src.models.store import ShopifyStore, StoreStatus


@pytest.fixture
def oauth_service(monkeypatch):
    """Create OAuth service with test environment variables."""
    monkeypatch.setenv("SHOPIFY_API_KEY", "test-api-key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "test-api-secret")
    monkeypatch.setenv("SHOPIFY_APP_HANDLE", "test-app")
    monkeypatch.setenv("APP_URL", "https://test.example.com")
    monkeypatch.setenv("SHOPIFY_SCOPES", "read_products,write_products")
    
    return OAuthService()


@pytest.fixture
def db_session():
    """Mock database session."""
    return MagicMock()


class TestShopDomainValidation:
    """Test shop domain validation."""
    
    def test_valid_shop_domain(self, oauth_service):
        """Test valid shop domain formats."""
        assert oauth_service.validate_shop_domain("mystore.myshopify.com") is True
        assert oauth_service.validate_shop_domain("test-shop.myshopify.com") is True
        assert oauth_service.validate_shop_domain("123shop.myshopify.com") is True
    
    def test_invalid_shop_domain(self, oauth_service):
        """Test invalid shop domain formats."""
        assert oauth_service.validate_shop_domain("invalid") is False
        assert oauth_service.validate_shop_domain("mystore.com") is False
        assert oauth_service.validate_shop_domain(".myshopify.com") is False
        assert oauth_service.validate_shop_domain("") is False
        assert oauth_service.validate_shop_domain("MYSTORE.myshopify.com") is False  # Should be lowercase
    
    def test_shop_domain_normalization(self, oauth_service):
        """Test shop domain normalization (removes protocol and trailing slash)."""
        assert oauth_service.validate_shop_domain("https://mystore.myshopify.com") is True
        assert oauth_service.validate_shop_domain("http://mystore.myshopify.com") is True
        assert oauth_service.validate_shop_domain("mystore.myshopify.com/") is True


class TestTenantDerivation:
    """Test tenant ID derivation."""
    
    def test_tenant_id_derivation(self, oauth_service):
        """Test that tenant_id is derived deterministically."""
        shop_domain = "mystore.myshopify.com"
        tenant_id = oauth_service._derive_tenant_id(shop_domain)
        
        # Should be 32 characters (hex)
        assert len(tenant_id) == 32
        assert all(c in '0123456789abcdef' for c in tenant_id)
        
        # Should be deterministic
        assert oauth_service._derive_tenant_id(shop_domain) == tenant_id
        assert oauth_service._derive_tenant_id(shop_domain) == tenant_id
    
    def test_tenant_id_different_shops(self, oauth_service):
        """Test that different shops get different tenant_ids."""
        tenant_id_1 = oauth_service._derive_tenant_id("store1.myshopify.com")
        tenant_id_2 = oauth_service._derive_tenant_id("store2.myshopify.com")
        
        assert tenant_id_1 != tenant_id_2
    
    def test_tenant_id_normalization(self, oauth_service):
        """Test that normalized shop domains get same tenant_id."""
        tenant_id_1 = oauth_service._derive_tenant_id("mystore.myshopify.com")
        tenant_id_2 = oauth_service._derive_tenant_id("https://mystore.myshopify.com")
        tenant_id_3 = oauth_service._derive_tenant_id("http://mystore.myshopify.com/")
        
        assert tenant_id_1 == tenant_id_2 == tenant_id_3


class TestHMACVerification:
    """Test HMAC verification."""
    
    def test_valid_hmac(self, oauth_service):
        """Test valid HMAC signature."""
        import hmac
        import base64
        
        params = {
            "code": "test-code",
            "shop": "mystore.myshopify.com",
            "state": "test-state",
            "timestamp": "1234567890"
        }
        
        # Compute HMAC
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        computed_hmac = hmac.new(
            "test-api-secret".encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        )
        hmac_value = base64.b64encode(computed_hmac.digest()).decode("utf-8")
        
        params["hmac"] = hmac_value
        
        assert oauth_service.verify_callback_hmac(params) is True
    
    def test_invalid_hmac(self, oauth_service):
        """Test invalid HMAC signature."""
        params = {
            "code": "test-code",
            "shop": "mystore.myshopify.com",
            "hmac": "invalid-hmac"
        }
        
        assert oauth_service.verify_callback_hmac(params) is False
    
    def test_missing_hmac(self, oauth_service):
        """Test missing HMAC parameter."""
        params = {
            "code": "test-code",
            "shop": "mystore.myshopify.com"
        }
        
        assert oauth_service.verify_callback_hmac(params) is False


class TestStateManagement:
    """Test OAuth state management."""
    
    def test_create_authorization_url(self, oauth_service, db_session):
        """Test creating authorization URL with state."""
        shop = "mystore.myshopify.com"
        
        # Mock database operations
        mock_state = OAuthState(
            id="test-id",
            shop_domain=shop,
            state="test-state",
            nonce="test-nonce",
            scopes="read_products",
            redirect_uri="https://test.example.com/api/auth/callback",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        db_session.add = MagicMock()
        db_session.commit = MagicMock()
        
        url = oauth_service.create_authorization_url(shop, db_session)
        
        assert "mystore.myshopify.com" in url
        assert "admin/oauth/authorize" in url
        assert "client_id=test-api-key" in url
        assert "state=" in url
        db_session.add.assert_called_once()
        db_session.commit.assert_called_once()
    
    def test_validate_state_valid(self, oauth_service, db_session):
        """Test validating a valid state."""
        shop = "mystore.myshopify.com"
        state = "test-state"
        
        mock_state = OAuthState(
            id="test-id",
            shop_domain=shop,
            state=state,
            nonce="test-nonce",
            scopes="read_products",
            redirect_uri="https://test.example.com/api/auth/callback",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        
        db_session.query.return_value.filter.return_value.first.return_value = mock_state
        
        result = oauth_service.validate_state(state, shop, db_session)
        
        assert result == mock_state
    
    def test_validate_state_not_found(self, oauth_service, db_session):
        """Test validating a non-existent state."""
        shop = "mystore.myshopify.com"
        state = "non-existent-state"
        
        db_session.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(InvalidStateError, match="not found"):
            oauth_service.validate_state(state, shop, db_session)
    
    def test_validate_state_expired(self, oauth_service, db_session):
        """Test validating an expired state."""
        shop = "mystore.myshopify.com"
        state = "expired-state"
        
        mock_state = OAuthState(
            id="test-id",
            shop_domain=shop,
            state=state,
            nonce="test-nonce",
            scopes="read_products",
            redirect_uri="https://test.example.com/api/auth/callback",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)  # Expired
        )
        
        db_session.query.return_value.filter.return_value.first.return_value = mock_state
        
        with pytest.raises(InvalidStateError, match="expired"):
            oauth_service.validate_state(state, shop, db_session)
    
    def test_validate_state_used(self, oauth_service, db_session):
        """Test validating an already-used state."""
        shop = "mystore.myshopify.com"
        state = "used-state"
        
        mock_state = OAuthState(
            id="test-id",
            shop_domain=shop,
            state=state,
            nonce="test-nonce",
            scopes="read_products",
            redirect_uri="https://test.example.com/api/auth/callback",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            used_at=datetime.now(timezone.utc)  # Already used
        )
        
        db_session.query.return_value.filter.return_value.first.return_value = mock_state
        
        with pytest.raises(InvalidStateError, match="already been used"):
            oauth_service.validate_state(state, shop, db_session)


class TestTokenExchange:
    """Test token exchange with Shopify."""
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, oauth_service):
        """Test successful token exchange."""
        shop = "mystore.myshopify.com"
        code = "test-code"
        
        mock_response = {
            "access_token": "test-access-token",
            "scope": "read_products,write_products"
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock()
            mock_post.raise_for_status = AsyncMock()
            mock_post.json.return_value = mock_response
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_post)
            
            result = await oauth_service.exchange_code_for_token(shop, code)
            
            assert result["access_token"] == "test-access-token"
            assert result["scope"] == "read_products,write_products"
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self, oauth_service):
        """Test failed token exchange."""
        shop = "mystore.myshopify.com"
        code = "invalid-code"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock()
            mock_post.raise_for_status.side_effect = Exception("401 Unauthorized")
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_post)
            
            with pytest.raises(TokenExchangeError):
                await oauth_service.exchange_code_for_token(shop, code)
