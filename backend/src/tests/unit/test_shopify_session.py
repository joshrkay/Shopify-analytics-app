"""
Unit tests for Shopify session token verifier.

Tests token verification, context extraction, and tenant derivation.
"""

import pytest
import jwt
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from src.platform.shopify_session import (
    ShopifySessionTokenVerifier,
    ShopifySessionContext,
    get_session_token_verifier,
)


@pytest.fixture
def session_verifier(monkeypatch):
    """Create session token verifier with test environment variables."""
    monkeypatch.setenv("SHOPIFY_API_KEY", "test-api-key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "test-api-secret")
    
    return ShopifySessionTokenVerifier()


def create_test_token(shop_domain: str, expires_in_minutes: int = 60) -> str:
    """Create a test session token for a shop."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_in_minutes)
    
    payload = {
        "iss": f"https://{shop_domain}/admin",
        "dest": f"https://{shop_domain}",
        "aud": "test-api-key",
        "sub": "test-user-id",
        "exp": int(exp.timestamp()),
        "nbf": int(now.timestamp()),
        "iat": int(now.timestamp()),
        "jti": "test-jti",
        "sid": "test-session-id"
    }
    
    return jwt.encode(payload, "test-api-secret", algorithm="HS256")


class TestSessionTokenVerification:
    """Test session token verification."""
    
    def test_verify_valid_token(self, session_verifier):
        """Test verifying a valid token."""
        shop_domain = "mystore.myshopify.com"
        token = create_test_token(shop_domain)
        
        context = session_verifier.verify_session_token(token)
        
        assert isinstance(context, ShopifySessionContext)
        assert context.shop_domain == shop_domain
        assert context.user_id == "test-user-id"
        assert len(context.tenant_id) == 32
    
    def test_verify_expired_token(self, session_verifier):
        """Test verifying an expired token."""
        shop_domain = "mystore.myshopify.com"
        token = create_test_token(shop_domain, expires_in_minutes=-10)  # Expired
        
        with pytest.raises(Exception):  # Should raise HTTPException
            session_verifier.verify_session_token(token)
    
    def test_verify_invalid_audience(self, session_verifier):
        """Test verifying token with invalid audience."""
        shop_domain = "mystore.myshopify.com"
        
        # Create token with wrong audience
        payload = {
            "iss": f"https://{shop_domain}/admin",
            "dest": f"https://{shop_domain}",
            "aud": "wrong-api-key",  # Wrong audience
            "sub": "test-user-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        
        token = jwt.encode(payload, "test-api-secret", algorithm="HS256")
        
        with pytest.raises(Exception):  # Should raise HTTPException
            session_verifier.verify_session_token(token)
    
    def test_verify_invalid_signature(self, session_verifier):
        """Test verifying token with invalid signature."""
        shop_domain = "mystore.myshopify.com"
        
        # Create token with wrong secret
        payload = {
            "iss": f"https://{shop_domain}/admin",
            "dest": f"https://{shop_domain}",
            "aud": "test-api-key",
            "sub": "test-user-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        
        with pytest.raises(Exception):  # Should raise HTTPException
            session_verifier.verify_session_token(token)
    
    def test_verify_missing_dest(self, session_verifier):
        """Test verifying token missing dest claim."""
        payload = {
            "iss": "https://mystore.myshopify.com/admin",
            # Missing "dest"
            "aud": "test-api-key",
            "sub": "test-user-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        
        token = jwt.encode(payload, "test-api-secret", algorithm="HS256")
        
        with pytest.raises(Exception):  # Should raise HTTPException
            session_verifier.verify_session_token(token)


class TestTenantDerivation:
    """Test tenant ID derivation from session tokens."""
    
    def test_tenant_id_derivation(self, session_verifier):
        """Test that tenant_id is derived deterministically."""
        shop_domain = "mystore.myshopify.com"
        token = create_test_token(shop_domain)
        
        context1 = session_verifier.verify_session_token(token)
        context2 = session_verifier.verify_session_token(token)
        
        # Should be deterministic
        assert context1.tenant_id == context2.tenant_id
        
        # Should match OAuth service derivation
        expected_tenant_id = hashlib.sha256(f"shopify:{shop_domain}".encode()).hexdigest()[:32]
        assert context1.tenant_id == expected_tenant_id
    
    def test_tenant_id_different_shops(self, session_verifier):
        """Test that different shops get different tenant_ids."""
        token1 = create_test_token("store1.myshopify.com")
        token2 = create_test_token("store2.myshopify.com")
        
        context1 = session_verifier.verify_session_token(token1)
        context2 = session_verifier.verify_session_token(token2)
        
        assert context1.tenant_id != context2.tenant_id


class TestSingleton:
    """Test singleton verifier instance."""
    
    def test_get_session_token_verifier(self, monkeypatch):
        """Test getting singleton verifier instance."""
        monkeypatch.setenv("SHOPIFY_API_KEY", "test-api-key")
        monkeypatch.setenv("SHOPIFY_API_SECRET", "test-api-secret")
        
        verifier1 = get_session_token_verifier()
        verifier2 = get_session_token_verifier()
        
        # Should return same instance
        assert verifier1 is verifier2
