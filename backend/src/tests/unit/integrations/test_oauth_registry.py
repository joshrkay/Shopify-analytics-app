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

from fastapi import HTTPException

from src.integrations.airbyte.oauth_registry import (
    build_auth_url,
    build_source_config,
    exchange_code_for_tokens,
    validate_shop_domain,
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


# =============================================================================
# validate_shop_domain — SSRF / Open Redirect regression tests
# =============================================================================

class TestValidateShopDomain:
    """Regression tests for shop_domain validation (SSRF prevention)."""

    def test_valid_domain_passes(self):
        """Valid myshopify.com domain is accepted and returned normalized."""
        assert validate_shop_domain("mystore.myshopify.com") == "mystore.myshopify.com"

    def test_valid_domain_with_hyphens_and_numbers(self):
        """Domain with hyphens and numbers is accepted."""
        assert validate_shop_domain("my-store-123.myshopify.com") == "my-store-123.myshopify.com"

    def test_normalizes_uppercase(self):
        """Uppercase input is normalized to lowercase."""
        assert validate_shop_domain("MYSTORE.myshopify.com") == "mystore.myshopify.com"

    def test_normalizes_protocol_prefix(self):
        """https:// prefix is stripped during normalization."""
        assert validate_shop_domain("https://mystore.myshopify.com") == "mystore.myshopify.com"

    def test_normalizes_http_prefix(self):
        """http:// prefix is stripped during normalization."""
        assert validate_shop_domain("http://mystore.myshopify.com") == "mystore.myshopify.com"

    def test_normalizes_trailing_slash(self):
        """Trailing slash is stripped during normalization."""
        assert validate_shop_domain("mystore.myshopify.com/") == "mystore.myshopify.com"

    def test_normalizes_combined(self):
        """Combined protocol + uppercase + trailing slash is normalized."""
        assert validate_shop_domain("HTTPS://MyStore.myshopify.com/") == "mystore.myshopify.com"

    def test_rejects_attacker_domain(self):
        """SSRF regression: rejects non-myshopify.com domain."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain("attacker.com")
        assert exc_info.value.status_code == 400
        assert "myshopify.com" in exc_info.value.detail

    def test_rejects_subdomain_bypass_attempt(self):
        """Rejects domain where myshopify.com is a subdomain of attacker."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain("store.myshopify.com.attacker.com")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_string(self):
        """Rejects empty shop domain."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain("")
        assert exc_info.value.status_code == 400

    def test_rejects_path_traversal(self):
        """Rejects domain with path traversal after valid domain."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain("mystore.myshopify.com/../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_rejects_bare_myshopify_com(self):
        """Rejects bare myshopify.com without a subdomain."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain(".myshopify.com")
        assert exc_info.value.status_code == 400

    def test_rejects_non_shopify_tld(self):
        """Rejects domains that look like shopify but aren't."""
        with pytest.raises(HTTPException) as exc_info:
            validate_shop_domain("store.notshopify.com")
        assert exc_info.value.status_code == 400

    def test_build_auth_url_rejects_invalid_domain(self, monkeypatch):
        """build_auth_url rejects invalid shop_domain (defense in depth)."""
        monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-key")
        with pytest.raises(HTTPException) as exc_info:
            build_auth_url(
                "shopify",
                state="csrf",
                redirect_uri="https://app.example.com/callback",
                shop_domain="attacker.com",
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_exchange_code_rejects_invalid_domain(self, monkeypatch):
        """exchange_code_for_tokens rejects invalid shop_domain (defense in depth)."""
        monkeypatch.setenv("SHOPIFY_API_KEY", "shopify-key")
        monkeypatch.setenv("SHOPIFY_API_SECRET", "shopify-secret")
        with pytest.raises(HTTPException) as exc_info:
            await exchange_code_for_tokens(
                "shopify",
                code="auth-code",
                redirect_uri="https://app.example.com/callback",
                shop_domain="attacker.com",
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# discover_accounts — per-platform account discovery
# =============================================================================

class TestDiscoverAccounts:
    """
    Tests for discover_accounts() and its per-platform helpers.
    Each test mocks the httpx.AsyncClient to avoid real network calls.
    """

    # -------------------------------------------------------------------------
    # Meta Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_meta_returns_accounts(self, monkeypatch):
        """discover_accounts for meta_ads returns id+name list from Graph API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "act_111", "name": "Acme Ads", "account_status": 1},
                {"id": "act_222", "name": "Acme Retargeting", "account_status": 1},
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("meta_ads", {"access_token": "tok-abc"})

        assert len(accounts) == 2
        assert accounts[0] == {"id": "act_111", "name": "Acme Ads"}
        assert accounts[1] == {"id": "act_222", "name": "Acme Retargeting"}

    @pytest.mark.asyncio
    async def test_meta_empty_token_returns_empty(self):
        """discover_accounts for meta_ads returns [] when access_token is missing."""
        from src.integrations.airbyte.oauth_registry import discover_accounts
        accounts = await discover_accounts("meta_ads", {})
        assert accounts == []

    @pytest.mark.asyncio
    async def test_meta_api_error_raises_502(self):
        """discover_accounts for meta_ads raises 502 on non-200 Graph API response."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "bad request"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("meta_ads", {"access_token": "tok-abc"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # Google Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_google_returns_customer_ids(self, monkeypatch):
        """discover_accounts for google_ads parses resourceNames into customer IDs."""
        monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "dev-tok-123")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resourceNames": ["customers/1234567890", "customers/9876543210"]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("google_ads", {"access_token": "goog-tok"})

        assert len(accounts) == 2
        assert accounts[0]["id"] == "1234567890"
        assert accounts[1]["id"] == "9876543210"
        # Names contain the customer_id (best effort without extra API call)
        assert "1234567890" in accounts[0]["name"]

    @pytest.mark.asyncio
    async def test_google_sends_developer_token_header(self, monkeypatch):
        """discover_accounts for google_ads includes developer-token in request headers."""
        monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "my-dev-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"resourceNames": []}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            await discover_accounts("google_ads", {"access_token": "goog-tok"})

        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["headers"]["developer-token"] == "my-dev-token"
        assert "Bearer goog-tok" in call_kwargs["headers"]["Authorization"]

    @pytest.mark.asyncio
    async def test_google_empty_token_returns_empty(self):
        """discover_accounts for google_ads returns [] when access_token is missing."""
        from src.integrations.airbyte.oauth_registry import discover_accounts
        accounts = await discover_accounts("google_ads", {})
        assert accounts == []

    @pytest.mark.asyncio
    async def test_google_api_error_raises_502(self):
        """discover_accounts for google_ads raises 502 on API error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "unauthorized"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("google_ads", {"access_token": "goog-tok"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # TikTok Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tiktok_returns_advertisers(self, monkeypatch):
        """discover_accounts for tiktok_ads parses advertiser list from Business API."""
        monkeypatch.setenv("TIKTOK_APP_ID", "tik-app-id")
        monkeypatch.setenv("TIKTOK_APP_SECRET", "tik-secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "list": [
                    {"advertiser_id": 111222, "advertiser_name": "Brand A"},
                    {"advertiser_id": 333444, "advertiser_name": "Brand B"},
                ]
            }
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("tiktok_ads", {"data": {"access_token": "tik-tok"}})

        assert len(accounts) == 2
        assert accounts[0] == {"id": "111222", "name": "Brand A"}
        assert accounts[1] == {"id": "333444", "name": "Brand B"}

    @pytest.mark.asyncio
    async def test_tiktok_reads_nested_access_token(self, monkeypatch):
        """discover_accounts for tiktok_ads extracts access_token from data.access_token."""
        monkeypatch.setenv("TIKTOK_APP_ID", "app-id")
        monkeypatch.setenv("TIKTOK_APP_SECRET", "secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"list": []}}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            # access_token nested under "data" (TikTok token response format)
            accounts = await discover_accounts("tiktok_ads", {"data": {"access_token": "nested-tok"}})

        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["params"]["access_token"] == "nested-tok"

    @pytest.mark.asyncio
    async def test_tiktok_api_error_raises_502(self):
        """discover_accounts for tiktok_ads raises 502 on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "server error"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("tiktok_ads", {"access_token": "tok"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # Snapchat Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_snapchat_returns_compound_ids(self):
        """discover_accounts for snapchat_ads encodes '{org_id}:{account_id}' in id."""
        orgs_response = MagicMock()
        orgs_response.status_code = 200
        orgs_response.json.return_value = {
            "organizations": [{"organization": {"id": "org-aaa", "name": "Acme Corp"}}]
        }
        accounts_response = MagicMock()
        accounts_response.status_code = 200
        accounts_response.json.return_value = {
            "adaccounts": [{"adaccount": {"id": "acc-bbb", "name": "Acme Snap Ads"}}]
        }

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "organizations" in url and "adaccounts" not in url:
                return orgs_response
            return accounts_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = mock_get

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("snapchat_ads", {"access_token": "snap-tok"})

        assert len(accounts) == 1
        assert accounts[0]["id"] == "org-aaa:acc-bbb"
        assert "Acme Snap Ads" in accounts[0]["name"]
        assert "Acme Corp" in accounts[0]["name"]

    @pytest.mark.asyncio
    async def test_snapchat_skips_org_on_adaccount_error(self):
        """discover_accounts for snapchat_ads skips an org if adaccount fetch fails."""
        orgs_response = MagicMock()
        orgs_response.status_code = 200
        orgs_response.json.return_value = {
            "organizations": [{"organization": {"id": "org-fail", "name": "BadOrg"}}]
        }
        accounts_response = MagicMock()
        accounts_response.status_code = 403
        accounts_response.json.return_value = {}

        async def mock_get(url, **kwargs):
            if "adaccounts" in url:
                return accounts_response
            return orgs_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = mock_get

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("snapchat_ads", {"access_token": "snap-tok"})

        assert accounts == []

    @pytest.mark.asyncio
    async def test_snapchat_org_fetch_error_raises_502(self):
        """discover_accounts for snapchat_ads raises 502 if organizations fetch fails."""
        orgs_response = MagicMock()
        orgs_response.status_code = 401
        orgs_response.text = "unauthorized"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=orgs_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("snapchat_ads", {"access_token": "snap-tok"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # Pinterest Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_pinterest_returns_ad_accounts(self):
        """discover_accounts for pinterest_ads returns id+name from Pinterest API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {"id": "pin-acct-001", "name": "Acme Pinterest"},
                {"id": "pin-acct-002", "name": "Acme Retargeting"},
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("pinterest_ads", {"access_token": "pin-tok"})

        assert len(accounts) == 2
        assert accounts[0] == {"id": "pin-acct-001", "name": "Acme Pinterest"}

    @pytest.mark.asyncio
    async def test_pinterest_api_error_raises_502(self):
        """discover_accounts for pinterest_ads raises 502 on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "forbidden"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("pinterest_ads", {"access_token": "pin-tok"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # Twitter Ads
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_twitter_returns_accounts(self):
        """discover_accounts for twitter_ads returns id+name from Twitter Ads API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "twt-001", "name": "Acme Twitter"},
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            accounts = await discover_accounts("twitter_ads", {"access_token": "twt-tok"})

        assert len(accounts) == 1
        assert accounts[0] == {"id": "twt-001", "name": "Acme Twitter"}

    @pytest.mark.asyncio
    async def test_twitter_api_error_raises_502(self):
        """discover_accounts for twitter_ads raises 502 on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "unauthorized"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("twitter_ads", {"access_token": "twt-tok"})
        assert exc_info.value.status_code == 502

    # -------------------------------------------------------------------------
    # Unknown platform
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unknown_platform_returns_empty(self):
        """discover_accounts returns [] for any platform not in the registry."""
        from src.integrations.airbyte.oauth_registry import discover_accounts
        accounts = await discover_accounts("unknown_platform", {"access_token": "tok"})
        assert accounts == []

    # -------------------------------------------------------------------------
    # Network errors
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_network_error_raises_502(self):
        """discover_accounts wraps httpx.RequestError as 502."""
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

        with patch("src.integrations.airbyte.oauth_registry.httpx.AsyncClient", return_value=mock_client):
            from src.integrations.airbyte.oauth_registry import discover_accounts
            with pytest.raises(Exception) as exc_info:
                await discover_accounts("pinterest_ads", {"access_token": "tok"})
        assert exc_info.value.status_code == 502


# =============================================================================
# ACCOUNT_ID_CONFIG_FIELD — per-platform field name mapping
# =============================================================================

class TestAccountIdConfigField:
    """Verifies the ACCOUNT_ID_CONFIG_FIELD mapping is correct for all platforms."""

    def test_meta_uses_account_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["meta_ads"] == "account_id"

    def test_google_uses_customer_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["google_ads"] == "customer_id"

    def test_tiktok_uses_advertiser_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["tiktok_ads"] == "advertiser_id"

    def test_snapchat_uses_account_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["snapchat_ads"] == "account_id"

    def test_pinterest_uses_ad_account_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["pinterest_ads"] == "ad_account_id"

    def test_twitter_uses_account_id(self):
        from src.integrations.airbyte.oauth_registry import ACCOUNT_ID_CONFIG_FIELD
        assert ACCOUNT_ID_CONFIG_FIELD["twitter_ads"] == "account_id"

    def test_all_oauth_platforms_in_selection_set_have_field_mapping(self):
        """Every platform in PLATFORMS_NEEDING_ACCOUNT_SELECTION has a config field entry."""
        from src.integrations.airbyte.oauth_registry import (
            ACCOUNT_ID_CONFIG_FIELD,
            PLATFORMS_NEEDING_ACCOUNT_SELECTION,
        )
        for platform in PLATFORMS_NEEDING_ACCOUNT_SELECTION:
            assert platform in ACCOUNT_ID_CONFIG_FIELD, (
                f"{platform} is in PLATFORMS_NEEDING_ACCOUNT_SELECTION "
                f"but missing from ACCOUNT_ID_CONFIG_FIELD"
            )
