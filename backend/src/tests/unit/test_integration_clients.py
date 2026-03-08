"""
Comprehensive unit tests for integration clients: AirbyteClient and OpenRouterClient.

Tests cover constructor validation, HTTP error mapping, and method request construction.
All HTTP calls are mocked via unittest.mock — no real network requests are made.
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.airbyte.client import AirbyteClient
from src.integrations.airbyte.exceptions import (
    AirbyteAuthenticationError,
    AirbyteConnectionError,
    AirbyteError,
    AirbyteNotFoundError,
    AirbyteRateLimitError,
)
from src.integrations.airbyte.models import SourceCreationRequest
from src.integrations.openrouter.client import OpenRouterClient
from src.integrations.openrouter.exceptions import (
    OpenRouterAuthenticationError,
    OpenRouterConnectionError,
    OpenRouterContentFilterError,
    OpenRouterError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)
from src.integrations.openrouter.models import ChatMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mock_response(status_code=200, json_data=None, headers=None):
    """Create a mock httpx response.

    Uses MagicMock (not AsyncMock) because httpx.Response.json() is synchronous.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# AirbyteClient — Constructor
# ---------------------------------------------------------------------------


class TestAirbyteClientConstructor:
    """Tests for AirbyteClient.__init__ authentication resolution."""

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_with_api_token(self):
        client = AirbyteClient(api_token="test-token")
        auth = client._client.headers["Authorization"]
        assert auth == "Bearer test-token"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_with_basic_auth(self):
        client = AirbyteClient(username="user", password="pass")
        expected = base64.b64encode(b"user:pass").decode()
        auth = client._client.headers["Authorization"]
        assert auth == f"Basic {expected}"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_basic_auth_takes_precedence(self):
        """When both Basic and Bearer creds are provided, Basic auth wins."""
        client = AirbyteClient(
            api_token="tok", username="user", password="pass"
        )
        auth = client._client.headers["Authorization"]
        assert auth.startswith("Basic ")

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_no_auth_raises_value_error(self):
        with pytest.raises(ValueError, match="authentication is required"):
            AirbyteClient()

    @patch.dict("os.environ", {"AIRBYTE_API_TOKEN": "env-token"}, clear=True)
    def test_constructor_reads_token_from_env(self):
        client = AirbyteClient()
        assert client._client.headers["Authorization"] == "Bearer env-token"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_custom_base_url(self):
        client = AirbyteClient(
            api_token="tok", base_url="http://localhost:8006/v1/"
        )
        # Trailing slash should be stripped
        assert client.base_url == "http://localhost:8006/v1"


# ---------------------------------------------------------------------------
# AirbyteClient — _request error handling
# ---------------------------------------------------------------------------


class TestAirbyteClientRequest:
    """Tests for AirbyteClient._request HTTP error mapping."""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {}, clear=True):
            c = AirbyteClient(api_token="test-token")
        return c

    @pytest.mark.asyncio
    async def test_request_401_raises_authentication_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(401))
        with pytest.raises(AirbyteAuthenticationError):
            await client._request("GET", "/health")

    @pytest.mark.asyncio
    async def test_request_403_raises_authentication_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(403))
        with pytest.raises(AirbyteAuthenticationError) as exc_info:
            await client._request("GET", "/health")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_request_404_raises_not_found_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(404))
        with pytest.raises(AirbyteNotFoundError):
            await client._request("GET", "/sources/missing-id")

    @pytest.mark.asyncio
    async def test_request_429_raises_rate_limit_error(self, client):
        resp = mock_response(429, headers={"Retry-After": "30"})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(AirbyteRateLimitError) as exc_info:
            await client._request("GET", "/connections")
        assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_request_429_without_retry_after(self, client):
        resp = mock_response(429, headers={})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(AirbyteRateLimitError) as exc_info:
            await client._request("GET", "/connections")
        assert exc_info.value.retry_after is None

    @pytest.mark.asyncio
    async def test_request_4xx_raises_airbyte_error(self, client):
        resp = mock_response(422, json_data={"error": "bad input"})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(AirbyteError) as exc_info:
            await client._request("POST", "/sources")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_request_5xx_raises_airbyte_error(self, client):
        resp = mock_response(500, json_data={"error": "internal"})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(AirbyteError) as exc_info:
            await client._request("GET", "/health")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_request_204_returns_empty_dict(self, client):
        client._client.request = AsyncMock(return_value=mock_response(204))
        result = await client._request("DELETE", "/sources/abc")
        assert result == {}

    @pytest.mark.asyncio
    async def test_request_200_returns_json(self, client):
        data = {"available": True}
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=data)
        )
        result = await client._request("GET", "/health")
        assert result == data

    @pytest.mark.asyncio
    async def test_request_timeout_raises_connection_error(self, client):
        client._client.request = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with pytest.raises(AirbyteConnectionError, match="timeout"):
            await client._request("GET", "/health")

    @pytest.mark.asyncio
    async def test_request_connect_error_raises_connection_error(self, client):
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(AirbyteConnectionError, match="Connection error"):
            await client._request("GET", "/health")

    @pytest.mark.asyncio
    async def test_request_builds_correct_url(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={})
        )
        await client._request("GET", "/health")
        call_kwargs = client._client.request.call_args
        assert call_kwargs.kwargs["url"] == f"{client.base_url}/health"

    @pytest.mark.asyncio
    async def test_request_passes_json_and_params(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={})
        )
        await client._request(
            "POST", "/sources", json={"name": "test"}, params={"ws": "123"}
        )
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["json"] == {"name": "test"}
        assert call_kwargs["params"] == {"ws": "123"}


# ---------------------------------------------------------------------------
# AirbyteClient — High-level methods
# ---------------------------------------------------------------------------


class TestAirbyteClientMethods:
    """Tests for AirbyteClient high-level API methods."""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {}, clear=True):
            c = AirbyteClient(
                api_token="test-token", workspace_id="ws-123"
            )
        return c

    @pytest.mark.asyncio
    async def test_check_health(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(
                200, json_data={"available": True, "db": True}
            )
        )
        health = await client.check_health()
        assert health.available is True
        assert health.db is True
        # Verify it called GET /health
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert "/health" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_list_connections_passes_workspace_params(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={"data": []})
        )
        await client.list_connections()
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["params"]["workspaceIds"] == "ws-123"

    @pytest.mark.asyncio
    async def test_list_connections_override_workspace(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={"data": []})
        )
        await client.list_connections(workspace_id="ws-override")
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["params"]["workspaceIds"] == "ws-override"

    @pytest.mark.asyncio
    async def test_list_connections_include_deleted(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={"data": []})
        )
        await client.list_connections(include_deleted=True)
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["params"]["includeDeleted"] == "true"

    @pytest.mark.asyncio
    async def test_list_connections_parses_results(self, client):
        conn_data = {
            "data": [
                {
                    "connectionId": "conn-1",
                    "name": "Test Connection",
                    "sourceId": "src-1",
                    "destinationId": "dst-1",
                    "status": "active",
                }
            ]
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=conn_data)
        )
        connections = await client.list_connections()
        assert len(connections) == 1
        assert connections[0].connection_id == "conn-1"
        assert connections[0].name == "Test Connection"

    @pytest.mark.asyncio
    async def test_trigger_sync_sends_correct_body(self, client):
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data={"jobId": "job-42"})
        )
        job_id = await client.trigger_sync("conn-abc")
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "/jobs" in call_kwargs["url"]
        assert call_kwargs["json"] == {
            "connectionId": "conn-abc",
            "jobType": "sync",
        }
        assert job_id == "job-42"

    @pytest.mark.asyncio
    async def test_get_job_calls_correct_endpoint(self, client):
        job_response = {
            "id": "job-42",
            "configType": "sync",
            "configId": "conn-abc",
            "status": "succeeded",
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=job_response)
        )
        job = await client.get_job("job-42")
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert "/jobs/job-42" in call_kwargs["url"]
        assert job.job_id == "job-42"
        assert job.status.value == "succeeded"

    @pytest.mark.asyncio
    async def test_create_source_sends_post(self, client):
        source_response = {
            "sourceId": "src-new",
            "name": "My Source",
            "sourceType": "source-shopify",
            "workspaceId": "ws-123",
            "configuration": {},
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=source_response)
        )
        req = SourceCreationRequest(
            name="My Source",
            source_type="source-shopify",
            configuration={"api_key": "secret"},
        )
        source = await client.create_source(req)
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "/sources" in call_kwargs["url"]
        body = call_kwargs["json"]
        assert body["name"] == "My Source"
        assert body["workspaceId"] == "ws-123"
        assert source.source_id == "src-new"

    @pytest.mark.asyncio
    async def test_create_source_with_workspace_override(self, client):
        source_response = {
            "sourceId": "src-new",
            "name": "Src",
            "sourceType": "source-shopify",
            "workspaceId": "ws-other",
            "configuration": {},
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=source_response)
        )
        req = SourceCreationRequest(
            name="Src",
            source_type="source-shopify",
            configuration={},
        )
        await client.create_source(req, workspace_id="ws-other")
        body = client._client.request.call_args.kwargs["json"]
        assert body["workspaceId"] == "ws-other"

    @pytest.mark.asyncio
    async def test_delete_source_calls_delete(self, client):
        client._client.request = AsyncMock(return_value=mock_response(204))
        await client.delete_source("src-del")
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "DELETE"
        assert "/sources/src-del" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_create_workspace_sends_post(self, client):
        ws_response = {
            "workspaceId": "ws-new",
            "name": "Acme Store",
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=ws_response)
        )
        workspace = await client.create_workspace("Acme Store")
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "/workspaces" in call_kwargs["url"]
        assert call_kwargs["json"] == {"name": "Acme Store"}
        assert workspace.workspace_id == "ws-new"
        assert workspace.name == "Acme Store"

    @pytest.mark.asyncio
    async def test_create_workspace_with_org_id(self, client):
        ws_response = {
            "workspaceId": "ws-new",
            "name": "Acme",
            "organizationId": "org-1",
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=ws_response)
        )
        workspace = await client.create_workspace(
            "Acme", organization_id="org-1"
        )
        body = client._client.request.call_args.kwargs["json"]
        assert body["organizationId"] == "org-1"
        assert workspace.organization_id == "org-1"


# ---------------------------------------------------------------------------
# OpenRouterClient — Constructor
# ---------------------------------------------------------------------------


class TestOpenRouterClientConstructor:
    """Tests for OpenRouterClient.__init__ validation."""

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_with_api_key(self):
        client = OpenRouterClient(api_key="sk-test-key")
        auth = client._client.headers["Authorization"]
        assert auth == "Bearer sk-test-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_without_api_key_raises_value_error(self):
        with pytest.raises(ValueError, match="API key is required"):
            OpenRouterClient()

    @patch.dict(
        "os.environ", {"OPENROUTER_API_KEY": "sk-env-key"}, clear=True
    )
    def test_constructor_reads_key_from_env(self):
        client = OpenRouterClient()
        assert client.api_key == "sk-env-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_sets_app_headers(self):
        client = OpenRouterClient(
            api_key="sk-test",
            app_name="TestApp",
            site_url="https://test.com",
        )
        assert client._client.headers["X-Title"] == "TestApp"
        assert client._client.headers["HTTP-Referer"] == "https://test.com"

    @patch.dict("os.environ", {}, clear=True)
    def test_constructor_custom_base_url(self):
        client = OpenRouterClient(
            api_key="sk-test", base_url="http://localhost:9000/v1/"
        )
        assert client.base_url == "http://localhost:9000/v1"


# ---------------------------------------------------------------------------
# OpenRouterClient — _request error handling
# ---------------------------------------------------------------------------


class TestOpenRouterClientRequest:
    """Tests for OpenRouterClient._request HTTP error mapping."""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {}, clear=True):
            c = OpenRouterClient(api_key="sk-test-key")
        return c

    @pytest.mark.asyncio
    async def test_request_401_raises_authentication_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(401))
        with pytest.raises(OpenRouterAuthenticationError):
            await client._request("GET", "/models")

    @pytest.mark.asyncio
    async def test_request_403_raises_authentication_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(403))
        with pytest.raises(OpenRouterAuthenticationError) as exc_info:
            await client._request("GET", "/models")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_request_429_raises_rate_limit_error(self, client):
        resp = mock_response(429, headers={"Retry-After": "60"})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(OpenRouterRateLimitError) as exc_info:
            await client._request("POST", "/chat/completions")
        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_request_429_without_retry_after(self, client):
        resp = mock_response(429, headers={})
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(OpenRouterRateLimitError) as exc_info:
            await client._request("POST", "/chat/completions")
        assert exc_info.value.retry_after is None

    @pytest.mark.asyncio
    async def test_request_content_filter_error_by_code(self, client):
        error_body = {
            "error": {
                "message": "Blocked by safety filter",
                "code": "content_filter",
            }
        }
        resp = mock_response(400, json_data=error_body)
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(OpenRouterContentFilterError):
            await client._request("POST", "/chat/completions")

    @pytest.mark.asyncio
    async def test_request_content_filter_error_by_message(self, client):
        error_body = {
            "error": {
                "message": "Content policy violation",
                "code": "bad_request",
            }
        }
        resp = mock_response(400, json_data=error_body)
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(OpenRouterContentFilterError):
            await client._request("POST", "/chat/completions")

    @pytest.mark.asyncio
    async def test_request_generic_4xx_raises_openrouter_error(self, client):
        error_body = {
            "error": {"message": "Invalid model", "code": "invalid_model"}
        }
        resp = mock_response(400, json_data=error_body)
        client._client.request = AsyncMock(return_value=resp)
        with pytest.raises(OpenRouterError) as exc_info:
            await client._request("POST", "/chat/completions")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_timeout_raises_timeout_error(self, client):
        client._client.request = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with pytest.raises(OpenRouterTimeoutError, match="timeout"):
            await client._request("POST", "/chat/completions")

    @pytest.mark.asyncio
    async def test_request_connection_error_raises_connection_error(
        self, client
    ):
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(OpenRouterConnectionError, match="Connection error"):
            await client._request("GET", "/models")

    @pytest.mark.asyncio
    async def test_request_200_returns_json(self, client):
        data = {"data": [{"id": "model-1"}]}
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=data)
        )
        result = await client._request("GET", "/models")
        assert result == data

    @pytest.mark.asyncio
    async def test_request_204_returns_empty_dict(self, client):
        client._client.request = AsyncMock(return_value=mock_response(204))
        result = await client._request("DELETE", "/some-resource")
        assert result == {}


# ---------------------------------------------------------------------------
# OpenRouterClient — High-level methods
# ---------------------------------------------------------------------------


class TestOpenRouterClientMethods:
    """Tests for OpenRouterClient high-level API methods."""

    @pytest.fixture
    def client(self):
        with patch.dict("os.environ", {}, clear=True):
            c = OpenRouterClient(api_key="sk-test-key")
        return c

    @pytest.mark.asyncio
    async def test_chat_completion_constructs_correct_body(self, client):
        completion_response = {
            "id": "gen-123",
            "model": "openai/gpt-4-turbo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "created": 1700000000,
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=completion_response)
        )

        messages = [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="Say hello"),
        ]
        response = await client.chat_completion(
            messages=messages,
            model="openai/gpt-4-turbo",
            max_tokens=100,
            temperature=0.5,
            top_p=0.9,
            stop=["END"],
        )

        call_kwargs = client._client.request.call_args.kwargs
        body = call_kwargs["json"]
        assert body["model"] == "openai/gpt-4-turbo"
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100
        assert body["top_p"] == 0.9
        assert body["stop"] == ["END"]
        assert len(body["messages"]) == 2
        assert body["messages"][0] == {
            "role": "system",
            "content": "You are helpful.",
        }
        assert body["messages"][1] == {
            "role": "user",
            "content": "Say hello",
        }

        # Verify response parsing
        assert response.id == "gen-123"
        assert response.model == "openai/gpt-4-turbo"
        assert response.content == "Hello!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    @pytest.mark.asyncio
    async def test_chat_completion_optional_params_omitted(self, client):
        """When optional params are not provided, they should not appear in body."""
        completion_response = {
            "id": "gen-456",
            "model": "openai/gpt-3.5-turbo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi"},
                }
            ],
            "usage": {},
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=completion_response)
        )

        messages = [ChatMessage(role="user", content="Hi")]
        await client.chat_completion(
            messages=messages,
            model="openai/gpt-3.5-turbo",
        )

        body = client._client.request.call_args.kwargs["json"]
        assert "max_tokens" not in body
        assert "top_p" not in body
        assert "stop" not in body
        assert body["temperature"] == 0.7  # default

    @pytest.mark.asyncio
    async def test_list_models_calls_get_models(self, client):
        models_response = {
            "data": [
                {
                    "id": "openai/gpt-4",
                    "name": "GPT-4",
                    "context_length": 8192,
                    "pricing": {"prompt": 0.03, "completion": 0.06},
                },
                {
                    "id": "anthropic/claude-3",
                    "name": "Claude 3",
                    "context_length": 200000,
                    "pricing": {"prompt": 0.01, "completion": 0.02},
                },
            ]
        }
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=models_response)
        )

        models = await client.list_models()
        call_kwargs = client._client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert "/models" in call_kwargs["url"]
        assert len(models) == 2
        assert models[0].id == "openai/gpt-4"
        assert models[1].id == "anthropic/claude-3"
        assert models[0].context_length == 8192

    @pytest.mark.asyncio
    async def test_check_health_returns_true_on_success(self, client):
        models_response = {"data": [{"id": "m1", "name": "M1"}]}
        client._client.request = AsyncMock(
            return_value=mock_response(200, json_data=models_response)
        )
        result = await client.check_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_returns_false_on_error(self, client):
        client._client.request = AsyncMock(return_value=mock_response(401))
        result = await client.check_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_returns_false_on_connection_error(self, client):
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        # OpenRouterConnectionError is a subclass of OpenRouterError
        result = await client.check_health()
        assert result is False
