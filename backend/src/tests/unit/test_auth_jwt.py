"""
Comprehensive unit tests for auth modules:
- src/auth/jwt.py (ClerkJWTClaims, ExtractedClaims, extract_claims, parse_clerk_claims, TokenInfo)
- src/auth/token_service.py (TokenService session/revocation management)
- src/auth/context_resolver.py (AuthContext, TenantAccess, ANONYMOUS_CONTEXT)
"""

import time
import threading
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.auth.jwt import (
    ClerkJWTClaims,
    ClerkOrgRole,
    ExtractedClaims,
    TokenInfo,
    extract_claims,
    parse_clerk_claims,
)
from src.auth.token_service import (
    RevocationReason,
    SessionInfo,
    TokenService,
)
from src.auth.context_resolver import (
    AuthContext,
    TenantAccess,
    ANONYMOUS_CONTEXT,
)
from src.constants.permissions import Permission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_ts(seconds: int = 3600) -> int:
    """Return a Unix timestamp `seconds` in the future."""
    return int((datetime.now(timezone.utc) + timedelta(seconds=seconds)).timestamp())


def _past_ts(seconds: int = 3600) -> int:
    """Return a Unix timestamp `seconds` in the past."""
    return int((datetime.now(timezone.utc) - timedelta(seconds=seconds)).timestamp())


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _base_claims(**overrides) -> dict:
    """Minimal valid JWT claims dict."""
    claims = {
        "sub": "user_abc123",
        "iss": "https://clerk.example.com",
        "exp": _future_ts(3600),
        "iat": _past_ts(60),
    }
    claims.update(overrides)
    return claims


# ===========================================================================
# 1. jwt.py — ClerkOrgRole
# ===========================================================================

class TestClerkOrgRole:
    def test_enum_values(self):
        assert ClerkOrgRole.ADMIN.value == "org:admin"
        assert ClerkOrgRole.MEMBER.value == "org:member"
        assert ClerkOrgRole.BILLING.value == "org:billing"
        assert ClerkOrgRole.OWNER.value == "org:owner"

    def test_enum_is_string(self):
        assert isinstance(ClerkOrgRole.ADMIN, str)
        assert ClerkOrgRole.ADMIN == "org:admin"


# ===========================================================================
# 2. jwt.py — ClerkJWTClaims
# ===========================================================================

class TestClerkJWTClaims:
    def test_valid_minimal_claims(self):
        claims = ClerkJWTClaims(**_base_claims())
        assert claims.sub == "user_abc123"
        assert claims.clerk_user_id == "user_abc123"
        assert claims.iss == "https://clerk.example.com"
        assert claims.org_id is None
        assert claims.sid is None

    def test_full_claims_with_org(self):
        claims = ClerkJWTClaims(**_base_claims(
            sid="sess_xyz",
            azp="client_123",
            org_id="org_2abc",
            org_role="org:admin",
            org_slug="my-org",
            org_permissions=["read", "write"],
        ))
        assert claims.session_id == "sess_xyz"
        assert claims.org_id == "org_2abc"
        assert claims.org_role == "org:admin"
        assert claims.org_slug == "my-org"
        assert claims.org_permissions == ["read", "write"]

    def test_missing_required_sub_raises(self):
        with pytest.raises(Exception):
            ClerkJWTClaims(iss="https://x.com", exp=_future_ts(), iat=_now_ts())

    def test_missing_required_exp_raises(self):
        with pytest.raises(Exception):
            ClerkJWTClaims(sub="u", iss="https://x.com", iat=_now_ts())

    def test_missing_required_iat_raises(self):
        with pytest.raises(Exception):
            ClerkJWTClaims(sub="u", iss="https://x.com", exp=_future_ts())

    def test_missing_required_iss_raises(self):
        with pytest.raises(Exception):
            ClerkJWTClaims(sub="u", exp=_future_ts(), iat=_now_ts())

    def test_extra_claims_allowed(self):
        """model_config extra='allow' means unknown fields are accepted."""
        claims = ClerkJWTClaims(**_base_claims(custom_field="hello", another=42))
        assert claims.custom_field == "hello"
        assert claims.another == 42

    def test_expiration_datetime(self):
        ts = _future_ts(7200)
        claims = ClerkJWTClaims(**_base_claims(exp=ts))
        assert claims.expiration_datetime == datetime.fromtimestamp(ts, tz=timezone.utc)

    def test_issued_at_datetime(self):
        ts = _past_ts(120)
        claims = ClerkJWTClaims(**_base_claims(iat=ts))
        assert claims.issued_at_datetime == datetime.fromtimestamp(ts, tz=timezone.utc)

    def test_is_expired_false_for_future(self):
        claims = ClerkJWTClaims(**_base_claims(exp=_future_ts(9999)))
        assert claims.is_expired is False

    def test_is_expired_true_for_past(self):
        claims = ClerkJWTClaims(**_base_claims(exp=_past_ts(10)))
        assert claims.is_expired is True

    def test_has_org_context_true(self):
        claims = ClerkJWTClaims(**_base_claims(org_id="org_2abc"))
        assert claims.has_org_context is True

    def test_has_org_context_false(self):
        claims = ClerkJWTClaims(**_base_claims())
        assert claims.has_org_context is False

    def test_is_org_admin_admin_role(self):
        claims = ClerkJWTClaims(**_base_claims(org_role=ClerkOrgRole.ADMIN.value))
        assert claims.is_org_admin is True

    def test_is_org_admin_owner_role(self):
        claims = ClerkJWTClaims(**_base_claims(org_role=ClerkOrgRole.OWNER.value))
        assert claims.is_org_admin is True

    def test_is_org_admin_member_role(self):
        claims = ClerkJWTClaims(**_base_claims(org_role=ClerkOrgRole.MEMBER.value))
        assert claims.is_org_admin is False

    def test_is_org_admin_no_role(self):
        claims = ClerkJWTClaims(**_base_claims())
        assert claims.is_org_admin is False

    def test_get_org_context_with_org(self):
        claims = ClerkJWTClaims(**_base_claims(
            org_id="org_2abc",
            org_role="org:admin",
            org_slug="slug",
            org_permissions=["perm1"],
        ))
        ctx = claims.get_org_context()
        assert ctx == {
            "org_id": "org_2abc",
            "org_role": "org:admin",
            "org_slug": "slug",
            "org_permissions": ["perm1"],
        }

    def test_get_org_context_without_org(self):
        claims = ClerkJWTClaims(**_base_claims())
        assert claims.get_org_context() is None


# ===========================================================================
# 3. jwt.py — extract_claims
# ===========================================================================

class TestExtractClaims:
    def test_valid_extraction(self):
        raw = _base_claims(sid="sess_1", org_id="org_x", org_role="org:member", azp="cli")
        ec = extract_claims(raw)
        assert isinstance(ec, ExtractedClaims)
        assert ec.clerk_user_id == "user_abc123"
        assert ec.session_id == "sess_1"
        assert ec.org_id == "org_x"
        assert ec.org_role == "org:member"
        assert ec.azp == "cli"

    def test_missing_sub_raises_value_error(self):
        raw = {"exp": _future_ts(), "iat": _now_ts()}
        with pytest.raises(ValueError, match="sub"):
            extract_claims(raw)

    def test_missing_exp_raises_value_error(self):
        raw = {"sub": "u", "iat": _now_ts()}
        with pytest.raises(ValueError, match="exp"):
            extract_claims(raw)

    def test_missing_iat_raises_value_error(self):
        raw = {"sub": "u", "exp": _future_ts()}
        with pytest.raises(ValueError, match="iat"):
            extract_claims(raw)

    def test_invalid_timestamp_raises_value_error(self):
        raw = {"sub": "u", "exp": "not-a-number", "iat": _now_ts()}
        with pytest.raises(ValueError, match="Invalid timestamp"):
            extract_claims(raw)

    def test_invalid_iat_timestamp_raises_value_error(self):
        raw = {"sub": "u", "exp": _future_ts(), "iat": "bad"}
        with pytest.raises(ValueError, match="Invalid timestamp"):
            extract_claims(raw)

    def test_metadata_defaults_to_empty_dict(self):
        ec = extract_claims(_base_claims())
        assert ec.metadata == {}

    def test_metadata_passed_through(self):
        ec = extract_claims(_base_claims(metadata={"key": "val"}))
        assert ec.metadata == {"key": "val"}


# ===========================================================================
# 4. jwt.py — ExtractedClaims properties
# ===========================================================================

class TestExtractedClaims:
    def test_has_org_context(self):
        ec = extract_claims(_base_claims(org_id="org_1"))
        assert ec.has_org_context is True

    def test_no_org_context(self):
        ec = extract_claims(_base_claims())
        assert ec.has_org_context is False

    def test_is_expired_false(self):
        ec = extract_claims(_base_claims(exp=_future_ts(9999)))
        assert ec.is_expired is False

    def test_is_expired_true(self):
        ec = extract_claims(_base_claims(exp=_past_ts(10)))
        assert ec.is_expired is True

    def test_time_until_expiry_positive(self):
        ec = extract_claims(_base_claims(exp=_future_ts(600)))
        assert ec.time_until_expiry > 0

    def test_time_until_expiry_negative_when_expired(self):
        ec = extract_claims(_base_claims(exp=_past_ts(600)))
        assert ec.time_until_expiry < 0

    def test_frozen_dataclass(self):
        ec = extract_claims(_base_claims())
        with pytest.raises(AttributeError):
            ec.clerk_user_id = "other"


# ===========================================================================
# 5. jwt.py — parse_clerk_claims
# ===========================================================================

class TestParseClerkClaims:
    def test_valid_parse(self):
        raw = _base_claims(org_id="org_1")
        result = parse_clerk_claims(raw)
        assert isinstance(result, ClerkJWTClaims)
        assert result.org_id == "org_1"

    def test_invalid_claims_raises_value_error(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_clerk_claims({"bad": "data"})


# ===========================================================================
# 6. jwt.py — TokenInfo
# ===========================================================================

class TestTokenInfo:
    def test_from_claims(self):
        ec = extract_claims(_base_claims(
            sid="sess_abc",
            org_id="org_x",
        ))
        info = TokenInfo.from_claims(ec)
        assert info.clerk_user_id == "user_abc123"
        assert info.session_id == "sess_abc"
        assert info.org_id == "org_x"
        assert info.issued_at == ec.issued_at
        assert info.expires_at == ec.expires_at
        assert isinstance(info.is_expired, bool)
        assert isinstance(info.time_until_expiry_seconds, float)

    def test_to_log_dict_short_ids(self):
        ec = extract_claims(_base_claims(sid="short"))
        info = TokenInfo.from_claims(ec)
        d = info.to_log_dict()
        assert d["clerk_user_id"] == "user_abc123"
        assert d["session_id"] == "short"
        assert "is_expired" in d
        assert "expires_in_seconds" in d

    def test_to_log_dict_truncates_long_user_id(self):
        long_id = "a" * 30
        ec = extract_claims(_base_claims(sub=long_id))
        info = TokenInfo.from_claims(ec)
        d = info.to_log_dict()
        assert d["clerk_user_id"] == long_id[:20] + "..."

    def test_to_log_dict_truncates_long_session_id(self):
        long_sid = "s" * 20
        ec = extract_claims(_base_claims(sid=long_sid))
        info = TokenInfo.from_claims(ec)
        d = info.to_log_dict()
        assert d["session_id"] == long_sid[:10] + "..."

    def test_to_log_dict_none_session(self):
        ec = extract_claims(_base_claims())
        info = TokenInfo.from_claims(ec)
        d = info.to_log_dict()
        assert d["session_id"] is None


# ===========================================================================
# 7. token_service.py — TokenService
# ===========================================================================

class TestTokenServiceRevocation:
    def setup_method(self):
        self.svc = TokenService(revocation_ttl=86400, use_redis=False)

    def test_revoke_session_marks_as_revoked(self):
        self.svc.revoke_session("sess_1", reason=RevocationReason.LOGOUT)
        assert self.svc.is_revoked(session_id="sess_1") is True

    def test_is_revoked_false_for_unknown_session(self):
        assert self.svc.is_revoked(session_id="unknown") is False

    def test_revoke_session_removes_from_active(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        self.svc.record_activity("sess_1", "user_1", expires)
        assert self.svc.get_session_info("sess_1") is not None
        self.svc.revoke_session("sess_1")
        assert self.svc.get_session_info("sess_1") is None

    def test_revoke_all_user_sessions(self):
        """revoke_all_user_sessions always sets revoke_tokens_before, so
        is_revoked needs a token_issued_at that falls before that cutoff."""
        self.svc.revoke_all_user_sessions("user_1", reason=RevocationReason.SECURITY_EVENT)
        # Token issued in the past (before the revoke_tokens_before cutoff)
        old_token = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert self.svc.is_revoked(clerk_user_id="user_1", token_issued_at=old_token) is True

    def test_revoke_all_removes_active_sessions(self):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        self.svc.record_activity("sess_a", "user_1", expires)
        self.svc.record_activity("sess_b", "user_1", expires)
        self.svc.revoke_all_user_sessions("user_1")
        assert self.svc.get_active_sessions("user_1") == []

    def test_is_revoked_with_token_issued_before_revoke(self):
        """Token issued before revocation time should be revoked."""
        revoke_time = datetime.now(timezone.utc)
        token_issued = revoke_time - timedelta(minutes=5)
        self.svc.revoke_all_user_sessions(
            "user_1",
            revoke_tokens_before=revoke_time,
        )
        assert self.svc.is_revoked(
            clerk_user_id="user_1",
            token_issued_at=token_issued,
        ) is True

    def test_is_revoked_with_token_issued_after_revoke(self):
        """Token issued after revocation time should NOT be revoked."""
        revoke_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        token_issued = datetime.now(timezone.utc)
        self.svc.revoke_all_user_sessions(
            "user_1",
            revoke_tokens_before=revoke_time,
        )
        assert self.svc.is_revoked(
            clerk_user_id="user_1",
            token_issued_at=token_issued,
        ) is False

    def test_is_revoked_user_without_token_time(self):
        """User-level revoke without revoke_tokens_before revokes everything
        when no token_issued_at is provided."""
        self.svc._revoked_users["user_1"] = MagicMock(
            revoke_tokens_before=None,
        )
        assert self.svc.is_revoked(clerk_user_id="user_1") is True

    def test_clear_revocation_list(self):
        self.svc.revoke_session("s1")
        self.svc.revoke_all_user_sessions("u1")
        self.svc.clear_revocation_list()
        assert self.svc.is_revoked(session_id="s1") is False
        assert self.svc.is_revoked(clerk_user_id="u1") is False


class TestTokenServiceActivity:
    def setup_method(self):
        self.svc = TokenService(revocation_ttl=86400, use_redis=False)
        self.expires = datetime.now(timezone.utc) + timedelta(hours=1)

    def test_record_activity_creates_session(self):
        self.svc.record_activity("sess_1", "user_1", self.expires, ip_address="1.2.3.4")
        info = self.svc.get_session_info("sess_1")
        assert info is not None
        assert info.clerk_user_id == "user_1"
        assert info.ip_address == "1.2.3.4"

    def test_record_activity_updates_existing(self):
        self.svc.record_activity("sess_1", "user_1", self.expires, ip_address="1.1.1.1")
        first_seen = self.svc.get_session_info("sess_1").last_seen_at
        self.svc.record_activity("sess_1", "user_1", self.expires, ip_address="2.2.2.2")
        info = self.svc.get_session_info("sess_1")
        assert info.ip_address == "2.2.2.2"
        assert info.last_seen_at >= first_seen

    def test_get_active_sessions_filters_by_user(self):
        self.svc.record_activity("s1", "user_1", self.expires)
        self.svc.record_activity("s2", "user_2", self.expires)
        self.svc.record_activity("s3", "user_1", self.expires)
        sessions = self.svc.get_active_sessions("user_1")
        assert len(sessions) == 2
        assert all(s.clerk_user_id == "user_1" for s in sessions)

    def test_get_active_sessions_excludes_expired(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        self.svc.record_activity("s_expired", "user_1", past)
        self.svc.record_activity("s_active", "user_1", self.expires)
        sessions = self.svc.get_active_sessions("user_1")
        assert len(sessions) == 1
        assert sessions[0].session_id == "s_active"

    def test_get_session_info_returns_none_for_missing(self):
        assert self.svc.get_session_info("nonexistent") is None


class TestTokenServiceCleanup:
    def test_cleanup_removes_expired_revocations(self):
        svc = TokenService(revocation_ttl=1, use_redis=False)
        # Add a revocation entry with a very old revoked_at
        from src.auth.token_service import RevocationEntry
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        svc._revoked_sessions["old_sess"] = RevocationEntry(
            identifier="old_sess",
            identifier_type="session",
            revoked_at=old_time,
            reason=RevocationReason.LOGOUT,
        )
        svc._revoked_users["old_user"] = RevocationEntry(
            identifier="old_user",
            identifier_type="user",
            revoked_at=old_time,
            reason=RevocationReason.ALL_SESSIONS,
        )
        # Add an expired active session
        svc._active_sessions["expired_sess"] = SessionInfo(
            session_id="expired_sess",
            clerk_user_id="u1",
            created_at=old_time,
            last_seen_at=old_time,
            expires_at=old_time,
        )

        # Force cleanup by setting _last_cleanup far in the past
        svc._last_cleanup = 0
        svc._maybe_cleanup()

        assert "old_sess" not in svc._revoked_sessions
        assert "old_user" not in svc._revoked_users
        assert "expired_sess" not in svc._active_sessions

    def test_cleanup_skips_when_interval_not_reached(self):
        svc = TokenService(revocation_ttl=86400, use_redis=False)
        svc._last_cleanup = time.time()  # just cleaned up
        from src.auth.token_service import RevocationEntry
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        svc._revoked_sessions["old"] = RevocationEntry(
            identifier="old",
            identifier_type="session",
            revoked_at=old_time,
            reason=RevocationReason.LOGOUT,
        )
        svc._maybe_cleanup()
        # Should NOT have cleaned up because interval not reached
        assert "old" in svc._revoked_sessions


class TestTokenServiceThreadSafety:
    def test_concurrent_revocations(self):
        """Basic thread safety: concurrent revocations should not raise."""
        svc = TokenService(revocation_ttl=86400, use_redis=False)
        errors = []

        def revoke_range(start, end):
            try:
                for i in range(start, end):
                    svc.revoke_session(f"sess_{i}")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=revoke_range, args=(0, 50))
        t2 = threading.Thread(target=revoke_range, args=(50, 100))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
        # All 100 sessions should be revoked
        for i in range(100):
            assert svc.is_revoked(session_id=f"sess_{i}") is True


# ===========================================================================
# 8. context_resolver.py — TenantAccess
# ===========================================================================

class TestTenantAccess:
    def _make_access(self, **overrides):
        defaults = dict(
            tenant_id="t-1",
            tenant_name="Test Tenant",
            roles=frozenset(["admin"]),
            permissions=frozenset([Permission.ANALYTICS_VIEW, Permission.BILLING_VIEW]),
            billing_tier="growth",
            is_active=True,
        )
        defaults.update(overrides)
        return TenantAccess(**defaults)

    def test_has_permission_true(self):
        ta = self._make_access()
        assert ta.has_permission(Permission.ANALYTICS_VIEW) is True

    def test_has_permission_false(self):
        ta = self._make_access()
        assert ta.has_permission(Permission.TEAM_MANAGE) is False

    def test_has_role_true_case_insensitive(self):
        ta = self._make_access(roles=frozenset(["Admin"]))
        assert ta.has_role("admin") is True
        assert ta.has_role("ADMIN") is True

    def test_has_role_false(self):
        ta = self._make_access(roles=frozenset(["viewer"]))
        assert ta.has_role("admin") is False


# ===========================================================================
# 9. context_resolver.py — AuthContext
# ===========================================================================

class TestAuthContext:
    def _make_user(self, user_id="uid-1", is_super=False):
        user = MagicMock()
        user.id = user_id
        user.is_super_admin = is_super
        return user

    def _make_tenant_access(self, tenant_id="t-1", is_active=True, roles=None, perms=None):
        return TenantAccess(
            tenant_id=tenant_id,
            tenant_name=f"Tenant {tenant_id}",
            roles=frozenset(roles or ["admin"]),
            permissions=frozenset(perms or [Permission.ANALYTICS_VIEW]),
            billing_tier="free",
            is_active=is_active,
        )

    def test_is_authenticated_with_user(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="clerk_1",
            session_id="s1",
        )
        assert ctx.is_authenticated is True

    def test_is_authenticated_without_user(self):
        ctx = AuthContext(
            user=None,
            clerk_user_id="clerk_1",
            session_id="s1",
        )
        assert ctx.is_authenticated is False

    def test_is_authenticated_empty_clerk_user_id(self):
        """Empty clerk_user_id with None user is not authenticated (ANONYMOUS)."""
        ctx = AuthContext(user=None, clerk_user_id="", session_id=None)
        assert ctx.is_authenticated is False

    def test_is_super_admin_true(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            _is_super_admin=True,
        )
        assert ctx.is_super_admin is True

    def test_is_super_admin_false(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            _is_super_admin=False,
        )
        assert ctx.is_super_admin is False

    def test_allowed_tenant_ids_filters_active(self):
        ta1 = self._make_tenant_access("t-1", is_active=True)
        ta2 = self._make_tenant_access("t-2", is_active=False)
        ta3 = self._make_tenant_access("t-3", is_active=True)
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta1, "t-2": ta2, "t-3": ta3},
        )
        allowed = ctx.allowed_tenant_ids
        assert "t-1" in allowed
        assert "t-3" in allowed
        assert "t-2" not in allowed

    def test_current_roles_with_tenant(self):
        ta = self._make_tenant_access("t-1", roles=["admin", "editor"])
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta},
            current_tenant_id="t-1",
        )
        assert ctx.current_roles == frozenset(["admin", "editor"])

    def test_current_roles_without_tenant(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
        )
        assert ctx.current_roles == frozenset()

    def test_current_permissions_with_tenant(self):
        ta = self._make_tenant_access("t-1", perms=[Permission.BILLING_MANAGE])
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta},
            current_tenant_id="t-1",
        )
        assert Permission.BILLING_MANAGE in ctx.current_permissions

    def test_current_permissions_without_tenant(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
        )
        assert ctx.current_permissions == frozenset()

    def test_has_access_to_tenant_true(self):
        ta = self._make_tenant_access("t-1")
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta},
        )
        assert ctx.has_access_to_tenant("t-1") is True

    def test_has_access_to_tenant_false(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={},
        )
        assert ctx.has_access_to_tenant("t-1") is False

    def test_has_access_to_tenant_inactive(self):
        ta = self._make_tenant_access("t-1", is_active=False)
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta},
        )
        assert ctx.has_access_to_tenant("t-1") is False

    def test_has_access_to_tenant_super_admin_bypass(self):
        """Super admins have access to ANY tenant, even if not in tenant_access."""
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={},
            _is_super_admin=True,
        )
        assert ctx.has_access_to_tenant("any-tenant") is True

    def test_switch_tenant_success(self):
        ta = self._make_tenant_access("t-1")
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={"t-1": ta},
        )
        assert ctx.switch_tenant("t-1") is True
        assert ctx.current_tenant_id == "t-1"

    def test_switch_tenant_fails_no_access(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={},
        )
        assert ctx.switch_tenant("t-1") is False
        assert ctx.current_tenant_id is None

    def test_switch_tenant_super_admin_succeeds(self):
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c1",
            session_id=None,
            tenant_access={},
            _is_super_admin=True,
        )
        assert ctx.switch_tenant("any-tenant") is True
        assert ctx.current_tenant_id == "any-tenant"

    def test_to_dict_serialization(self):
        ta = self._make_tenant_access("t-1")
        ctx = AuthContext(
            user=self._make_user("uid-42"),
            clerk_user_id="clerk_42",
            session_id="sess_42",
            tenant_access={"t-1": ta},
            current_tenant_id="t-1",
            org_id="org_x",
            org_role="org:admin",
            _is_super_admin=False,
        )
        d = ctx.to_dict()
        assert d["user_id"] == "uid-42"
        assert d["clerk_user_id"] == "clerk_42"
        assert d["session_id"] == "sess_42"
        assert d["current_tenant_id"] == "t-1"
        assert "t-1" in d["allowed_tenant_ids"]
        assert d["org_id"] == "org_x"
        assert d["org_role"] == "org:admin"
        assert d["is_authenticated"] is True
        assert d["is_super_admin"] is False

    def test_to_dict_unauthenticated(self):
        d = ANONYMOUS_CONTEXT.to_dict()
        assert d["is_authenticated"] is False
        assert d["user_id"] is None
        assert d["is_super_admin"] is False

    def test_user_id_property(self):
        ctx = AuthContext(user=self._make_user("u-99"), clerk_user_id="c", session_id=None)
        assert ctx.user_id == "u-99"

    def test_user_id_none_when_no_user(self):
        ctx = AuthContext(user=None, clerk_user_id="c", session_id=None)
        assert ctx.user_id is None

    def test_has_multi_tenant_access(self):
        ta1 = self._make_tenant_access("t-1")
        ta2 = self._make_tenant_access("t-2")
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c",
            session_id=None,
            tenant_access={"t-1": ta1, "t-2": ta2},
        )
        assert ctx.has_multi_tenant_access is True

    def test_single_tenant_not_multi(self):
        ta = self._make_tenant_access("t-1")
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c",
            session_id=None,
            tenant_access={"t-1": ta},
        )
        assert ctx.has_multi_tenant_access is False

    def test_has_permission(self):
        ta = self._make_tenant_access("t-1", perms=[Permission.ANALYTICS_VIEW])
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c",
            session_id=None,
            tenant_access={"t-1": ta},
            current_tenant_id="t-1",
        )
        assert ctx.has_permission(Permission.ANALYTICS_VIEW) is True
        assert ctx.has_permission(Permission.TEAM_MANAGE) is False

    def test_has_permission_for_tenant(self):
        ta = self._make_tenant_access("t-1", perms=[Permission.BILLING_VIEW])
        ctx = AuthContext(
            user=self._make_user(),
            clerk_user_id="c",
            session_id=None,
            tenant_access={"t-1": ta},
        )
        assert ctx.has_permission_for_tenant(Permission.BILLING_VIEW, "t-1") is True
        assert ctx.has_permission_for_tenant(Permission.BILLING_VIEW, "t-2") is False


# ===========================================================================
# 10. context_resolver.py — ANONYMOUS_CONTEXT
# ===========================================================================

class TestAnonymousContext:
    def test_is_unauthenticated(self):
        assert ANONYMOUS_CONTEXT.is_authenticated is False

    def test_user_is_none(self):
        assert ANONYMOUS_CONTEXT.user is None

    def test_clerk_user_id_is_empty(self):
        assert ANONYMOUS_CONTEXT.clerk_user_id == ""

    def test_no_tenant_access(self):
        assert ANONYMOUS_CONTEXT.tenant_access == {}
        assert ANONYMOUS_CONTEXT.allowed_tenant_ids == []

    def test_not_super_admin(self):
        assert ANONYMOUS_CONTEXT.is_super_admin is False

    def test_current_tenant_is_none(self):
        assert ANONYMOUS_CONTEXT.current_tenant_id is None
