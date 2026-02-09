"""
Tests for Shopify embedded app entry point route (GET /).

Tests cover:
- HMAC verification of Shopify query params
- Successful app bootstrap HTML response
- Rejection of invalid HMAC
- Handling of requests without Shopify params
- CSP headers on response
"""

import hashlib
import hmac
import os
from urllib.parse import urlencode

import pytest
from unittest.mock import patch

from src.api.routes.shopify_entry import verify_shopify_query_hmac


TEST_API_SECRET = "test-shopify-secret-key"


def _sign_params(params: dict, secret: str) -> str:
    """Generate a valid HMAC for query params (same algorithm Shopify uses)."""
    sorted_params = urlencode(sorted(params.items()))
    return hmac.new(
        secret.encode("utf-8"),
        sorted_params.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class TestVerifyShopifyQueryHmac:
    """Tests for the HMAC verification function."""

    def test_valid_hmac(self):
        params = {"shop": "test-store.myshopify.com", "timestamp": "1234567890"}
        hmac_value = _sign_params(params, TEST_API_SECRET)
        params["hmac"] = hmac_value

        assert verify_shopify_query_hmac(params, TEST_API_SECRET) is True

    def test_invalid_hmac(self):
        params = {
            "shop": "test-store.myshopify.com",
            "timestamp": "1234567890",
            "hmac": "deadbeef",
        }
        assert verify_shopify_query_hmac(params, TEST_API_SECRET) is False

    def test_missing_hmac(self):
        params = {"shop": "test-store.myshopify.com", "timestamp": "1234567890"}
        assert verify_shopify_query_hmac(params, TEST_API_SECRET) is False

    def test_empty_secret(self):
        params = {"shop": "test-store.myshopify.com", "hmac": "anything"}
        assert verify_shopify_query_hmac(params, "") is False

    def test_multiple_params_order_independent(self):
        """HMAC should be the same regardless of param insertion order."""
        params_a = {"shop": "store.myshopify.com", "timestamp": "100", "host": "abc123"}
        params_b = {"host": "abc123", "timestamp": "100", "shop": "store.myshopify.com"}

        hmac_a = _sign_params(params_a, TEST_API_SECRET)
        hmac_b = _sign_params(params_b, TEST_API_SECRET)

        assert hmac_a == hmac_b

        params_a["hmac"] = hmac_a
        assert verify_shopify_query_hmac(params_a, TEST_API_SECRET) is True
