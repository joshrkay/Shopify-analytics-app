"""
Unit tests for the per-platform OAuth registry.

Tests cover:
- build_auth_url: generates correct authorization URLs per platform
- exchange_code_for_tokens: makes correct token exchange HTTP requests
- build_source_config: maps token response + env vars to Airbyte source config
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse, parse_qs

import httpx
from fastapi import HTTPException

from src.integrations.airbyte.oauth_registry import (
    OAUTH_REGISTRY,
    build_auth_url,
    build_source_config,
    exchange_code_for_tokens,
)


# =============================================================================
# build_auth_url
# =============================================================================

class TestBuildAuthUrl:

    def test_meta_ads_generates_correct_url(self, monkeypatch):
        """build_auth_url for meta_ads generates the correct Facebook OAuth URL."""
        monkeypatch.setenv("META_APP_ID", "meta-client-id-123")

        url = build_auth_url("meta_ads", state="csrf-state-abc", redirect_uri="https://app.example.com/callback")

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert "facebook.com" in parsed.netloc
        assert params["client_id"] == ["meta-client-id-123"]
        assert params["state"] == ["csrf-state-abc"]
        assert params["redirect_uri"] == ["https://app.example.com/callback"]
        assert params["response_type"] == ["code"]
        assert "ads_read" in params["scope"][0]

    def test_shopify_interpolates_shop_domain(self, monkeypatch):
        """build_auth_url for shopify interpolates shop_domain into the URL."""
        monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-key-456")

        url = build_auth_url(
            "shopify",
            state="csrf-state-xyz",
            redirect_uri="https://app.example.com/callback",
            shop_domain="mystore.myshopify.com",
        )

        parsed = urlparse(url)
        assert "mystore.myshopify.com" in parsed.netloc
        assert "/admin/oauth/authorize" in parsed.path

    def test_google_ads_includes_extra_auth_params(self, monkeypatch):
        """build_auth_url for google_ads includes access_type=offline and prompt=consent."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id-789")

        url = build_auth_url(
            "google_ads",
            state="csrf-state-google",
            redirect_uri="https://app.example.com/callback",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params.get("access_type") == ["offline"]
        assert params.get("prompt") == ["consent"]
        assert "adwords" in params["scope"][0]

    def test_missing_credentials_raises_502(self, monkeypatch):
        """build_auth_url raises HTTPException(502) when client ID env var is not set."""
        monkeypatch.delenv("META_APP_ID", raising=False)

        with pytest.raises(HTTPException) as exc_info:
            build_auth_url("meta_ads", state="csrf-state", redirect_uri="https://app.example.com/callback")

        assert exc_info.value.status_code == 502
        assert "META_APP_ID" in exc_info.value.detail

    def test_unknown_platform_raises_400(self, monkeypatch):
        """build_auth_url raises HTTPException(400) for an unsupported platform."""
        with pytest.raises(HTTPException) as exc_info:
            build_auth_url("unknown_platform", state="csrf-state", redirect_uri="https://example.com")

        assert exc_info.value.status_code == 400
        assert "unknown_platform" in exc_info.value.detail

    def test_tiktok_uses_app_id_not_client_id(self, monkeypatch):
        """TikTok builds URL using app_id parameter (not client_id) and omits response_type."""
        monkeypatch.setenv("TIKTOK_APP_ID", "tiktok-app-id-999")

        url = build_auth_url(
            "tiktok_ads",
            state="csrf-state-tiktok",
            redirect_uri="https://app.example.com/callback",
        )

        params = parse_qs(urlparse(url).query)
        assert "app_id" in params
        assert params["app_id"] == ["tiktok-app-id-999"]
        assert "client_id" not in params
        assert "response_type" not in params


# =============================================================================
# exchange_code_for_tokens
# =============================================================================

class TestExchangeCodeForTokens:

    @pytest.mark.asyncio
    async def test_meta_ads_calls_correct_token_url(self, monkeypatch):
        """exchange_code_for_tokens for meta_ads makes GET to Facebook token URL."""
        monkeypatch.setenv("META_APP_ID", "meta-client-id")
        monkeypatch.setenv("META_APP_SECRET", "meta-client-secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "tok-meta-abc"}

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_http):
            result = await exchange_code_for_tokens(
                "meta_ads",
                code="auth-code-123",
                redirect_uri="https://app.example.com/callback",
            )

        assert result["access_token"] == "tok-meta-abc"
        # Meta uses GET, not POST
        mock_http.get.assert_called_once()
        mock_http.post.assert_not_called()
        call_url = mock_http.get.call_args[0][0]
        assert "graph.facebook.com" in call_url

    @pytest.mark.asyncio
    async def test_shopify_interpolates_shop_domain_in_token_url(self, monkeypatch):
        """exchange_code_for_tokens for shopify uses shop_domain in token URL."""
        monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-key")
        monkeypatch.setenv("SHOPIFY_API_SECRET", "shopify-secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "tok-shopify-xyz"}

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_http):
            result = await exchange_code_for_tokens(
                "shopify",
                code="auth-code-shopify",
                redirect_uri="https://app.example.com/callback",
                shop_domain="mystore.myshopify.com",
            )

        assert result["access_token"] == "tok-shopify-xyz"
        call_url = mock_http.post.call_args[0][0]
        assert "mystore.myshopify.com" in call_url

    @pytest.mark.asyncio
    async def test_non_200_response_raises_502(self, monkeypatch):
        """exchange_code_for_tokens raises HTTPException(502) on non-200 response."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(HTTPException) as exc_info:
                await exchange_code_for_tokens(
                    "google_ads",
                    code="bad-code",
                    redirect_uri="https://app.example.com/callback",
                )

        assert exc_info.value.status_code == 502


# =============================================================================
# build_source_config
# =============================================================================

class TestBuildSourceConfig:

    def test_meta_ads_maps_access_token(self):
        """build_source_config for meta_ads maps access_token from token response."""
        tokens = {"access_token": "meta-access-tok-abc", "token_type": "Bearer"}

        config = build_source_config("meta_ads", tokens)

        assert config["access_token"] == "meta-access-tok-abc"
        # token_type should NOT be in config (not in token_to_source_config)
        assert "token_type" not in config

    def test_google_ads_maps_tokens_and_env_credentials(self, monkeypatch):
        """build_source_config for google_ads maps tokens + developer_token + client_id/secret."""
        monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "dev-tok-google-123")
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")

        tokens = {
            "access_token": "google-access-tok",
            "refresh_token": "google-refresh-tok",
            "token_type": "Bearer",
        }

        config = build_source_config("google_ads", tokens)

        assert config["access_token"] == "google-access-tok"
        assert config["refresh_token"] == "google-refresh-tok"
        assert config["developer_token"] == "dev-tok-google-123"
        assert config["client_id"] == "google-client-id"
        assert config["client_secret"] == "google-client-secret"
