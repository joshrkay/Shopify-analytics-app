"""
Redis-backed token store for tracking active JTIs and revocation.

Provides:
- Active token tracking with TTL matching token expiry
- Per-user token set for bulk revocation
- Revocation set for invalidated JTIs
- Graceful degradation on Redis failures (log warning, never crash)

Key schema:
- embed:token:{jti}              -> JSON {user_id, tenant_id, access_surface, exp}
- embed:revoked:{jti}            -> "1" (TTL matches original token expiry)
- embed:user_tokens:{user_id}:{tenant_id} -> Redis SET of active JTIs

Phase 1 - JWT Issuance System for Superset Embedding
"""

import json
import logging
import os
import time
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class EmbedTokenStore:
    """
    Redis-backed store for tracking active embed token JTIs.

    All public methods handle Redis connection failures gracefully:
    they log a warning and return a safe default rather than raising.
    """

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_token(
        self,
        jti: str,
        user_id: str,
        tenant_id: str,
        access_surface: str,
        exp: int,
    ) -> None:
        """
        Store an active JTI with TTL matching token expiry.

        Args:
            jti: Unique JWT identifier
            user_id: User who owns the token
            tenant_id: Tenant context for the token
            access_surface: Where the token is used (shopify_embed, external_app)
            exp: Token expiry as a Unix timestamp
        """
        try:
            ttl = max(int(exp - time.time()), 1)

            token_key = f"embed:token:{jti}"
            payload = json.dumps({
                "user_id": user_id,
                "tenant_id": tenant_id,
                "access_surface": access_surface,
                "exp": exp,
            })
            self._redis.setex(token_key, ttl, payload)

            # Track JTI in the user's active token set
            user_key = f"embed:user_tokens:{user_id}:{tenant_id}"
            self._redis.sadd(user_key, jti)
            # Ensure the set has a reasonable TTL so it does not linger forever
            # Use 2x the token TTL as a generous upper bound
            current_ttl = self._redis.ttl(user_key)
            if current_ttl is None or current_ttl < ttl:
                self._redis.expire(user_key, ttl * 2)

            logger.info(
                "Stored embed token JTI",
                extra={
                    "jti": jti,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "access_surface": access_surface,
                    "ttl_seconds": ttl,
                },
            )
        except Exception:
            logger.warning(
                "Failed to store embed token JTI in Redis",
                extra={"jti": jti, "user_id": user_id, "tenant_id": tenant_id},
                exc_info=True,
            )

    def is_revoked(self, jti: str) -> bool:
        """
        Check whether a JTI has been revoked.

        Returns False on Redis failures (fail-open) so that a Redis
        outage does not lock out all embedded dashboard users.
        """
        try:
            return bool(self._redis.exists(f"embed:revoked:{jti}"))
        except Exception:
            logger.warning(
                "Failed to check JTI revocation in Redis",
                extra={"jti": jti},
                exc_info=True,
            )
            return False

    def revoke_token(self, jti: str) -> None:
        """
        Add a single JTI to the revocation set.

        The revocation entry inherits the remaining TTL from the active
        token (if still present), or defaults to 24 hours.
        """
        try:
            token_key = f"embed:token:{jti}"
            revoked_key = f"embed:revoked:{jti}"

            # Determine remaining TTL from the active token
            remaining_ttl = self._redis.ttl(token_key)
            if remaining_ttl is None or remaining_ttl <= 0:
                remaining_ttl = 86400  # 24-hour fallback

            self._redis.setex(revoked_key, remaining_ttl, "1")
            self._redis.delete(token_key)

            logger.info(
                "Revoked embed token JTI",
                extra={"jti": jti, "ttl_seconds": remaining_ttl},
            )
        except Exception:
            logger.warning(
                "Failed to revoke embed token JTI in Redis",
                extra={"jti": jti},
                exc_info=True,
            )

    def revoke_all_for_user(self, user_id: str, tenant_id: str) -> int:
        """
        Revoke all active tokens for a user+tenant combination.

        Returns the number of tokens revoked (0 on Redis failure).
        """
        try:
            user_key = f"embed:user_tokens:{user_id}:{tenant_id}"
            active_jtis = self._redis.smembers(user_key)
            if not active_jtis:
                return 0

            revoked_count = 0
            for jti_bytes in active_jtis:
                jti = jti_bytes.decode("utf-8") if isinstance(jti_bytes, bytes) else str(jti_bytes)
                self.revoke_token(jti)
                revoked_count += 1

            # Clean up the user set
            self._redis.delete(user_key)

            logger.info(
                "Revoked all embed tokens for user",
                extra={
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "revoked_count": revoked_count,
                },
            )
            return revoked_count
        except Exception:
            logger.warning(
                "Failed to revoke all tokens for user in Redis",
                extra={"user_id": user_id, "tenant_id": tenant_id},
                exc_info=True,
            )
            return 0

    def get_active_token_count(self, user_id: str, tenant_id: str) -> int:
        """
        Return the number of active (non-expired, non-revoked) JTIs for a user+tenant.

        Returns 0 on Redis failure.
        """
        try:
            user_key = f"embed:user_tokens:{user_id}:{tenant_id}"
            return self._redis.scard(user_key) or 0
        except Exception:
            logger.warning(
                "Failed to get active token count from Redis",
                extra={"user_id": user_id, "tenant_id": tenant_id},
                exc_info=True,
            )
            return 0


# --------------------------------------------------------------------------
# Module-level singleton
# --------------------------------------------------------------------------

_token_store: Optional[EmbedTokenStore] = None


def get_token_store() -> EmbedTokenStore:
    """
    Factory function returning a module-level EmbedTokenStore singleton.

    Uses REDIS_URL environment variable (default: redis://redis:6379/0).
    """
    global _token_store
    if _token_store is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        try:
            client = redis.Redis.from_url(redis_url, decode_responses=False)
            # Quick connectivity check
            client.ping()
            logger.info(
                "EmbedTokenStore connected to Redis",
                extra={"redis_url": redis_url},
            )
        except Exception:
            logger.warning(
                "Redis not reachable for EmbedTokenStore; operations will be no-ops",
                extra={"redis_url": redis_url},
                exc_info=True,
            )
            # Still create the store - methods handle failures gracefully
            client = redis.Redis.from_url(redis_url, decode_responses=False)

        _token_store = EmbedTokenStore(client)

    return _token_store
