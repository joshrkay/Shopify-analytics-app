"""
Tests for Rate Limiting Middleware.

Phase 6 (5.6.6) — Redis sliding window rate limiting.

Verifies:
- Rate limiter allows requests under limit
- Rate limiter blocks requests over limit
- Retry-After header present in 429 response
- Kill switch disables rate limiting
- Redis failure degrades gracefully (allows request)
- Custom limits and windows work
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from src.middleware.rate_limit import RateLimiter, RateLimitResult


class TestRateLimiter:
    """Test the RateLimiter class directly."""

    def _create_limiter(self, mock_redis=None):
        """Create a RateLimiter with a mock Redis."""
        limiter = RateLimiter(
            redis_url="redis://localhost:6379/0",
            default_limit=5,
            window_seconds=60,
        )
        if mock_redis is not None:
            limiter._redis = mock_redis
        return limiter

    def test_allows_request_under_limit(self):
        """Requests under the limit are allowed."""
        mock_redis = Mock()
        pipe = Mock()
        pipe.execute.return_value = [0, 2]  # zremrangebyscore, zcard
        mock_redis.pipeline.return_value = pipe

        pipe2 = Mock()
        pipe2.execute.return_value = [1, True]
        # Second pipeline call for zadd + expire
        mock_redis.pipeline.side_effect = [pipe, pipe2]

        limiter = self._create_limiter(mock_redis)
        result = limiter.check_rate_limit("user-1", "tenant-1", "embed_token")

        assert result.allowed is True
        assert result.remaining == 2  # 5 - 2 - 1 = 2
        assert result.retry_after == 0

    def test_blocks_request_over_limit(self):
        """Requests over the limit are blocked."""
        mock_redis = Mock()
        pipe = Mock()
        pipe.execute.return_value = [0, 5]  # zremrangebyscore, zcard = limit
        mock_redis.pipeline.return_value = pipe

        limiter = self._create_limiter(mock_redis)
        result = limiter.check_rate_limit("user-1", "tenant-1", "embed_token")

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after >= 1

    def test_redis_failure_allows_request(self):
        """Redis failure results in graceful degradation (allow request)."""
        import redis as redis_lib
        mock_redis = Mock()
        pipe = Mock()
        pipe.execute.side_effect = redis_lib.ConnectionError("Redis down")
        mock_redis.pipeline.return_value = pipe

        limiter = self._create_limiter(mock_redis)
        result = limiter.check_rate_limit("user-1", "tenant-1", "embed_token")

        assert result.allowed is True
        assert result.remaining == 5  # default limit

    def test_custom_limit_override(self):
        """Custom limit parameter overrides default."""
        mock_redis = Mock()
        pipe = Mock()
        pipe.execute.return_value = [0, 10]  # count = 10
        mock_redis.pipeline.return_value = pipe

        limiter = self._create_limiter(mock_redis)
        # Default limit is 5, but override to 15
        result = limiter.check_rate_limit(
            "user-1", "tenant-1", "embed_token", limit=15
        )

        assert result.allowed is True  # 10 < 15
        assert result.limit == 15

    def test_redis_key_format(self):
        """Redis key follows ratelimit:{endpoint}:{tenant_id}:{user_id} pattern."""
        mock_redis = Mock()
        pipe = Mock()
        pipe.execute.return_value = [0, 0]
        mock_redis.pipeline.return_value = pipe

        pipe2 = Mock()
        pipe2.execute.return_value = [1, True]
        mock_redis.pipeline.side_effect = [pipe, pipe2]

        limiter = self._create_limiter(mock_redis)
        limiter.check_rate_limit("user-1", "tenant-1", "embed_token")

        # Verify zadd was called with correct key pattern
        pipe2.zadd.assert_called_once()
        key = pipe2.zadd.call_args[0][0]
        assert key == "ratelimit:embed_token:tenant-1:user-1"


class TestRateLimitDependency:
    """Test the FastAPI dependency function."""

    @patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "false"})
    @pytest.mark.asyncio
    async def test_kill_switch_disables_rate_limiting(self):
        """When RATE_LIMIT_ENABLED=false, rate limiting is skipped."""
        from src.middleware.rate_limit import rate_limit_dependency

        dep_fn = rate_limit_dependency("embed_token")
        mock_request = Mock()

        result = await dep_fn(mock_request)
        assert result.allowed is True

    @patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "true"})
    @patch("src.middleware.rate_limit.get_rate_limiter")
    @patch("src.middleware.rate_limit.get_tenant_context")
    @pytest.mark.asyncio
    async def test_429_on_exceeded(self, mock_ctx, mock_limiter_fn):
        """429 raised when rate limit exceeded."""
        from fastapi import HTTPException
        from src.middleware.rate_limit import rate_limit_dependency

        mock_ctx.return_value = Mock(user_id="user-1", tenant_id="tenant-1")
        limiter = Mock()
        limiter.check_rate_limit.return_value = RateLimitResult(
            allowed=False, remaining=0, limit=30,
            reset_at=time.time() + 60, retry_after=45,
        )
        limiter.window_seconds = 60
        mock_limiter_fn.return_value = limiter

        dep_fn = rate_limit_dependency("embed_token")
        mock_request = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await dep_fn(mock_request)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "45"
