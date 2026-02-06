"""
Row-Level Security (RLS) Isolation Tests.

CRITICAL: These tests verify that tenant data isolation cannot be bypassed.
All tests must pass before deploying to production.

Test categories:
A. Positive — Verify authorized access works
B. Negative — Verify cross-tenant access is blocked
C. Deny-by-default — Verify datasets without RLS return zero rows
D. Clause generation — Verify RLS SQL is correct per role
E. Table coverage — Verify every dataset has RLS rules
F. JWT integration — Verify JWT claims map correctly to RLS
"""

import sys
import os
import time
import pytest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports (matches test_explore_guardrails.py pattern)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rls_rules import (
    UserRoleType,
    DENY_BY_DEFAULT_CLAUSE,
    RLS_CLAUSE_TEMPLATES,
    RLS_PROTECTED_TABLES,
    RLS_RULES,
    RLS_RULES_BY_ROLE,
    ALL_DATASETS_REQUIRING_RLS,
    get_rls_clause_for_role,
    get_rls_clause_for_user,
    create_superset_rls_rule_payload,
    validate_all_datasets_have_rls,
    enforce_deny_by_default,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def merchant_context():
    """Single-tenant merchant user context."""
    return {
        "user_id": "user_merchant_001",
        "tenant_id": "tenant_abc",
        "roles": ["merchant_admin"],
        "allowed_tenants": ["tenant_abc"],
        "billing_tier": "growth",
        "is_agency_user": False,
        "is_super_admin": False,
    }


@pytest.fixture
def agency_context():
    """Multi-tenant agency user context."""
    return {
        "user_id": "user_agency_001",
        "tenant_id": "tenant_abc",
        "roles": ["agency_admin"],
        "allowed_tenants": ["tenant_abc", "tenant_def", "tenant_ghi"],
        "billing_tier": "enterprise",
        "is_agency_user": True,
        "is_super_admin": False,
    }


@pytest.fixture
def super_admin_context():
    """Super admin user context."""
    return {
        "user_id": "user_admin_001",
        "tenant_id": "tenant_abc",
        "roles": ["super_admin"],
        "allowed_tenants": [],
        "billing_tier": "enterprise",
        "is_agency_user": False,
        "is_super_admin": True,
    }


@pytest.fixture
def mock_superset_client():
    """Mock Superset API client with configurable responses."""
    client = MagicMock()

    # Default: return some datasets and RLS rules
    datasets_response = MagicMock()
    datasets_response.json.return_value = {
        "result": [
            {"table_name": "fact_orders"},
            {"table_name": "fact_marketing_spend"},
            {"table_name": "fact_campaign_performance"},
        ]
    }

    rls_response = MagicMock()
    rls_response.json.return_value = {
        "result": [
            {
                "tables": [
                    {"table_name": "fact_orders"},
                    {"table_name": "fact_marketing_spend"},
                    {"table_name": "fact_campaign_performance"},
                ],
                "clause": "tenant_id = '{{ current_user.tenant_id }}'",
            }
        ]
    }

    def get_side_effect(url, **kwargs):
        if "dataset" in url:
            return datasets_response
        if "rowlevelsecurity" in url:
            return rls_response
        return MagicMock()

    client.get.side_effect = get_side_effect

    # Default POST returns 201 with an ID
    post_response = MagicMock()
    post_response.status_code = 201
    post_response.json.return_value = {"id": 1}
    client.post.return_value = post_response

    return client


# =============================================================================
# A. POSITIVE TESTS — Authorized access works
# =============================================================================

class TestPositiveAccess:
    """Verify that authorized users get correct RLS clauses."""

    def test_merchant_sees_own_tenant_data(self, merchant_context):
        """CRITICAL: Merchant user gets single-tenant RLS clause."""
        clause = get_rls_clause_for_user(
            is_agency_user=merchant_context["is_agency_user"],
            is_super_admin=merchant_context["is_super_admin"],
        )
        assert clause == "tenant_id = '{{ current_user.tenant_id }}'"
        assert "IN" not in clause

    def test_agency_sees_assigned_tenants(self, agency_context):
        """CRITICAL: Agency user gets multi-tenant IN clause."""
        clause = get_rls_clause_for_user(
            is_agency_user=agency_context["is_agency_user"],
            is_super_admin=agency_context["is_super_admin"],
        )
        assert clause == "tenant_id IN ({{ current_user.allowed_tenants | tojson }})"
        assert "IN" in clause

    def test_super_admin_sees_all_data(self, super_admin_context):
        """Super admin gets unrestricted access clause."""
        clause = get_rls_clause_for_user(
            is_agency_user=super_admin_context["is_agency_user"],
            is_super_admin=super_admin_context["is_super_admin"],
        )
        assert clause == "1=1"

    def test_merchant_admin_role_clause(self):
        """merchant_admin role returns merchant clause."""
        clause = get_rls_clause_for_role("merchant_admin")
        assert clause == RLS_CLAUSE_TEMPLATES[UserRoleType.MERCHANT]

    def test_agency_admin_role_clause(self):
        """agency_admin role returns agency clause."""
        clause = get_rls_clause_for_role("agency_admin")
        assert clause == RLS_CLAUSE_TEMPLATES[UserRoleType.AGENCY]

    def test_super_admin_role_clause(self):
        """super_admin role returns unrestricted clause."""
        clause = get_rls_clause_for_role("super_admin")
        assert clause == RLS_CLAUSE_TEMPLATES[UserRoleType.SUPER_ADMIN]


# =============================================================================
# B. NEGATIVE TESTS — Cross-tenant access blocked
# =============================================================================

class TestNegativeAccess:
    """Verify that unauthorized cross-tenant access is blocked."""

    def test_merchant_cannot_see_other_tenant(self):
        """CRITICAL: Merchant clause restricts to single tenant_id only."""
        clause = get_rls_clause_for_user(is_agency_user=False, is_super_admin=False)
        # Clause uses template variable, not wildcard
        assert "{{ current_user.tenant_id }}" in clause
        assert "1=1" not in clause
        assert "IN" not in clause

    def test_agency_cannot_see_unassigned_tenant(self):
        """CRITICAL: Agency clause uses explicit allowed_tenants list, not wildcard."""
        clause = get_rls_clause_for_user(is_agency_user=True, is_super_admin=False)
        assert "allowed_tenants" in clause
        assert "1=1" not in clause
        # Must use IN clause with specific list, not open access
        assert "IN" in clause

    def test_invalid_context_returns_deny_default(self):
        """CRITICAL: No valid context = deny all (1=0)."""
        clause = get_rls_clause_for_user(
            is_agency_user=False,
            is_super_admin=False,
            has_valid_context=False,
        )
        assert clause == DENY_BY_DEFAULT_CLAUSE
        assert clause == "1=0"

    def test_unknown_role_defaults_to_merchant(self):
        """Unknown roles get strictest (merchant) isolation, not open access."""
        clause = get_rls_clause_for_role("unknown_role_xyz")
        assert clause == RLS_CLAUSE_TEMPLATES[UserRoleType.MERCHANT]
        assert "1=1" not in clause

    def test_empty_role_defaults_to_merchant(self):
        """Empty role string defaults to merchant isolation."""
        clause = get_rls_clause_for_role("")
        assert clause == RLS_CLAUSE_TEMPLATES[UserRoleType.MERCHANT]

    def test_super_admin_flag_never_from_role_name(self):
        """Super admin access only via is_super_admin flag, not role lookup alone.

        This ensures that even if someone crafts a JWT with role='super_admin',
        the get_rls_clause_for_user function needs the explicit is_super_admin flag.
        """
        # Just being an agency user doesn't grant super admin
        clause = get_rls_clause_for_user(is_agency_user=True, is_super_admin=False)
        assert clause != "1=1"

        # Only explicit super admin flag grants full access
        clause = get_rls_clause_for_user(is_agency_user=False, is_super_admin=True)
        assert clause == "1=1"


# =============================================================================
# C. DENY-BY-DEFAULT TESTS
# =============================================================================

class TestDenyByDefault:
    """Verify deny-by-default behavior for datasets and contexts."""

    def test_deny_by_default_clause_value(self):
        """DENY_BY_DEFAULT_CLAUSE must be '1=0' (returns zero rows)."""
        assert DENY_BY_DEFAULT_CLAUSE == "1=0"

    def test_no_valid_context_returns_deny(self):
        """Without valid context, clause must deny all rows."""
        for is_agency in [True, False]:
            clause = get_rls_clause_for_user(
                is_agency_user=is_agency,
                is_super_admin=False,
                has_valid_context=False,
            )
            assert clause == "1=0", (
                f"Expected deny-by-default for is_agency={is_agency}"
            )

    def test_validate_identifies_unprotected_datasets(self):
        """validate_all_datasets_have_rls detects unprotected datasets."""
        client = MagicMock()

        # Dataset response includes one unprotected dataset
        datasets_resp = MagicMock()
        datasets_resp.json.return_value = {
            "result": [
                {"table_name": "fact_orders"},
                {"table_name": "unprotected_table"},
            ]
        }

        rls_resp = MagicMock()
        rls_resp.json.return_value = {
            "result": [
                {
                    "tables": [{"table_name": "fact_orders"}],
                    "clause": "tenant_id = '{{ current_user.tenant_id }}'",
                }
            ]
        }

        def get_side_effect(url, **kwargs):
            if "dataset" in url:
                return datasets_resp
            return rls_resp

        client.get.side_effect = get_side_effect

        is_valid, unprotected = validate_all_datasets_have_rls(client)
        assert not is_valid
        assert "unprotected_table" in unprotected
        assert "fact_orders" not in unprotected

    def test_validate_all_protected_returns_valid(self, mock_superset_client):
        """When all datasets have RLS, validation passes."""
        is_valid, unprotected = validate_all_datasets_have_rls(mock_superset_client)
        assert is_valid
        assert len(unprotected) == 0

    def test_enforce_applies_deny_rule_to_unprotected(self):
        """enforce_deny_by_default applies 1=0 rule to unprotected datasets."""
        client = MagicMock()

        # One unprotected dataset
        datasets_resp = MagicMock()
        datasets_resp.json.return_value = {
            "result": [
                {"table_name": "fact_orders"},
                {"table_name": "new_unprotected_table"},
            ]
        }

        rls_resp = MagicMock()
        rls_resp.json.return_value = {
            "result": [
                {
                    "tables": [{"table_name": "fact_orders"}],
                    "clause": "tenant_id = '{{ current_user.tenant_id }}'",
                }
            ]
        }

        def get_side_effect(url, **kwargs):
            if "dataset" in url:
                return datasets_resp
            return rls_resp

        client.get.side_effect = get_side_effect

        post_resp = MagicMock()
        post_resp.status_code = 201
        post_resp.json.return_value = {"id": 99}
        client.post.return_value = post_resp

        enforce_deny_by_default(client)

        # Verify POST was called with deny-by-default payload
        client.post.assert_called_once()
        call_args = client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["clause"] == "1=0"
        assert payload["group_key"] == "deny_by_default"
        assert "new_unprotected_table" in payload["tables"]

    def test_enforce_skips_when_all_protected(self, mock_superset_client):
        """enforce_deny_by_default does nothing when all datasets are protected."""
        enforce_deny_by_default(mock_superset_client)
        mock_superset_client.post.assert_not_called()


# =============================================================================
# D. CLAUSE GENERATION TESTS
# =============================================================================

class TestClauseGeneration:
    """Verify RLS clause generation for all roles and user types."""

    @pytest.mark.parametrize("role,expected_type", [
        ("merchant_admin", UserRoleType.MERCHANT),
        ("merchant_viewer", UserRoleType.MERCHANT),
        ("agency_admin", UserRoleType.AGENCY),
        ("agency_viewer", UserRoleType.AGENCY),
        ("super_admin", UserRoleType.SUPER_ADMIN),
    ])
    def test_all_roles_return_correct_clause_type(self, role, expected_type):
        """Each defined role returns the clause for its UserRoleType."""
        clause = get_rls_clause_for_role(role)
        assert clause == RLS_CLAUSE_TEMPLATES[expected_type]

    def test_case_insensitive_role_lookup(self):
        """Role lookup is case-insensitive."""
        assert get_rls_clause_for_role("MERCHANT_ADMIN") == get_rls_clause_for_role("merchant_admin")
        assert get_rls_clause_for_role("Agency_Admin") == get_rls_clause_for_role("agency_admin")

    def test_merchant_clause_structure(self):
        """Merchant clause uses exact equality on tenant_id."""
        clause = RLS_CLAUSE_TEMPLATES[UserRoleType.MERCHANT]
        assert clause.startswith("tenant_id = ")
        assert "{{ current_user.tenant_id }}" in clause

    def test_agency_clause_structure(self):
        """Agency clause uses IN with allowed_tenants list."""
        clause = RLS_CLAUSE_TEMPLATES[UserRoleType.AGENCY]
        assert "tenant_id IN" in clause
        assert "allowed_tenants" in clause

    def test_super_admin_clause_structure(self):
        """Super admin clause is unconditionally true."""
        clause = RLS_CLAUSE_TEMPLATES[UserRoleType.SUPER_ADMIN]
        assert clause == "1=1"

    def test_rls_payload_for_known_role(self):
        """create_superset_rls_rule_payload generates valid API payload."""
        payload = create_superset_rls_rule_payload("merchant_admin")
        assert payload["name"] == "merchant_admin_tenant_isolation"
        assert payload["filter_type"] == "Regular"
        assert payload["tables"] == RLS_PROTECTED_TABLES
        assert "tenant_id" in payload["clause"]

    def test_rls_payload_with_dataset_id(self):
        """Payload includes dataset_id when provided."""
        payload = create_superset_rls_rule_payload("merchant_admin", dataset_id=42)
        assert payload["dataset_id"] == 42

    def test_rls_payload_for_unknown_role_raises(self):
        """create_superset_rls_rule_payload raises ValueError for unknown roles."""
        with pytest.raises(ValueError, match="Unknown role"):
            create_superset_rls_rule_payload("nonexistent_role")


# =============================================================================
# E. TABLE COVERAGE TESTS
# =============================================================================

class TestTableCoverage:
    """Verify every dataset has RLS rules and registries are complete."""

    def test_all_protected_tables_covered_by_role_rules(self):
        """Every table in RLS_PROTECTED_TABLES appears in every role's rule."""
        for role, config in RLS_RULES_BY_ROLE.items():
            for table in RLS_PROTECTED_TABLES:
                assert table in config["tables"], (
                    f"Role '{role}' missing RLS for table '{table}'"
                )

    def test_all_legacy_rule_tables_exist(self):
        """Every table in RLS_RULES has a valid rule config."""
        for table_name, config in RLS_RULES.items():
            assert "clause" in config, f"Missing clause for {table_name}"
            assert "tables" in config, f"Missing tables for {table_name}"
            assert table_name in config["tables"], (
                f"Table {table_name} not in its own rule's tables list"
            )

    def test_unified_registry_contains_all_tables(self):
        """ALL_DATASETS_REQUIRING_RLS is the union of both registries."""
        expected = sorted(set(RLS_PROTECTED_TABLES) | set(RLS_RULES.keys()))
        assert ALL_DATASETS_REQUIRING_RLS == expected

    def test_unified_registry_not_empty(self):
        """Unified registry must contain datasets."""
        assert len(ALL_DATASETS_REQUIRING_RLS) > 0

    def test_no_duplicate_tables_in_protected_list(self):
        """RLS_PROTECTED_TABLES has no duplicates."""
        assert len(RLS_PROTECTED_TABLES) == len(set(RLS_PROTECTED_TABLES))

    def test_all_role_types_defined(self):
        """All UserRoleType values have corresponding entries."""
        role_types_in_rules = {
            config["role_type"] for config in RLS_RULES_BY_ROLE.values()
        }
        for role_type in UserRoleType:
            assert role_type in role_types_in_rules, (
                f"UserRoleType.{role_type.name} has no rules in RLS_RULES_BY_ROLE"
            )

    def test_protected_tables_include_core_fact_tables(self):
        """Core fact tables must always be protected."""
        required_tables = ["fact_orders", "fact_marketing_spend", "fact_campaign_performance"]
        for table in required_tables:
            assert table in RLS_PROTECTED_TABLES, (
                f"Core table '{table}' missing from RLS_PROTECTED_TABLES"
            )

    def test_protected_tables_include_dimension_tables(self):
        """Dimension tables with PII must be protected."""
        assert "dim_customers" in RLS_PROTECTED_TABLES
        assert "dim_products" in RLS_PROTECTED_TABLES


# =============================================================================
# F. JWT INTEGRATION TESTS
# =============================================================================

class TestJWTIntegration:
    """Verify JWT authentication module works correctly with RLS."""

    def test_jwt_auth_module_importable(self):
        """security.jwt_auth module is importable."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import (
            EmbedUser,
            verify_embed_jwt,
            extract_token_from_request,
            authenticate_embed_request,
            MAX_TOKEN_LIFETIME_SECONDS,
        )
        assert MAX_TOKEN_LIFETIME_SECONDS == 3600

    def test_embed_user_single_tenant(self):
        """EmbedUser for merchant has is_agency_user=False."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import EmbedUser

        user = EmbedUser(
            user_id="user_001",
            tenant_id="tenant_abc",
            roles=["merchant_admin"],
            allowed_tenants=["tenant_abc"],
            billing_tier="growth",
        )
        assert user.tenant_id == "tenant_abc"
        assert user.allowed_tenants == ["tenant_abc"]
        assert not user.is_agency_user
        assert user.is_authenticated
        assert not user.is_anonymous
        assert user.get_id() == "user_001"
        assert user.billing_tier == "growth"

    def test_embed_user_multi_tenant(self):
        """EmbedUser for agency has is_agency_user=True."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import EmbedUser

        user = EmbedUser(
            user_id="user_agency_001",
            tenant_id="tenant_abc",
            roles=["agency_admin"],
            allowed_tenants=["tenant_abc", "tenant_def", "tenant_ghi"],
            billing_tier="enterprise",
        )
        assert user.is_agency_user
        assert len(user.allowed_tenants) == 3
        assert user.billing_tier == "enterprise"

    def test_embed_user_default_allowed_tenants(self):
        """EmbedUser with empty allowed_tenants defaults to [tenant_id]."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import EmbedUser

        user = EmbedUser(
            user_id="user_001",
            tenant_id="tenant_abc",
            roles=["merchant_admin"],
            allowed_tenants=[],
        )
        assert user.allowed_tenants == ["tenant_abc"]
        assert not user.is_agency_user

    def test_verify_jwt_with_valid_token(self):
        """verify_embed_jwt decodes a valid HS256 token."""
        import jwt as pyjwt

        secret = "test-secret-key-for-verification"
        now = int(time.time())
        payload = {
            "sub": "user_001",
            "tenant_id": "tenant_abc",
            "roles": ["merchant_admin"],
            "allowed_tenants": ["tenant_abc"],
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": secret}):
            result = verify_embed_jwt(token)

        assert result is not None
        assert result["sub"] == "user_001"
        assert result["tenant_id"] == "tenant_abc"

    def test_verify_jwt_with_expired_token(self):
        """verify_embed_jwt returns None for expired tokens."""
        import jwt as pyjwt

        secret = "test-secret-key"
        now = int(time.time())
        payload = {
            "sub": "user_001",
            "tenant_id": "tenant_abc",
            "roles": ["merchant_admin"],
            "iat": now - 7200,
            "exp": now - 3600,  # Expired 1 hour ago
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": secret}):
            result = verify_embed_jwt(token)

        assert result is None

    def test_verify_jwt_with_wrong_secret(self):
        """verify_embed_jwt returns None for tokens signed with wrong secret."""
        import jwt as pyjwt

        now = int(time.time())
        payload = {
            "sub": "user_001",
            "tenant_id": "tenant_abc",
            "roles": ["merchant_admin"],
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": "correct-secret"}):
            result = verify_embed_jwt(token)

        assert result is None

    def test_verify_jwt_with_key_rotation(self):
        """verify_embed_jwt succeeds when token signed with previous secret."""
        import jwt as pyjwt

        previous_secret = "old-secret-key"
        current_secret = "new-secret-key"
        now = int(time.time())
        payload = {
            "sub": "user_001",
            "tenant_id": "tenant_abc",
            "roles": ["merchant_admin"],
            "iat": now,
            "exp": now + 3600,
        }
        # Sign with OLD secret
        token = pyjwt.encode(payload, previous_secret, algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {
            "SUPERSET_JWT_SECRET_CURRENT": current_secret,
            "SUPERSET_JWT_SECRET_PREVIOUS": previous_secret,
        }):
            result = verify_embed_jwt(token)

        assert result is not None
        assert result["sub"] == "user_001"

    def test_verify_jwt_rejects_excessive_lifetime(self):
        """verify_embed_jwt rejects tokens with lifetime > 60 minutes."""
        import jwt as pyjwt

        secret = "test-secret-key"
        now = int(time.time())
        payload = {
            "sub": "user_001",
            "tenant_id": "tenant_abc",
            "roles": ["merchant_admin"],
            "iat": now,
            "exp": now + 7200,  # 2 hours — exceeds MAX_TOKEN_LIFETIME_SECONDS
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": secret}):
            result = verify_embed_jwt(token)

        assert result is None

    def test_verify_jwt_missing_required_claims(self):
        """verify_embed_jwt rejects tokens missing required claims."""
        import jwt as pyjwt

        secret = "test-secret-key"
        now = int(time.time())
        # Missing tenant_id and roles
        payload = {
            "sub": "user_001",
            "iat": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from security.jwt_auth import verify_embed_jwt

        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": secret}):
            result = verify_embed_jwt(token)

        assert result is None


# =============================================================================
# SECURITY INVARIANT TESTS
# =============================================================================

class TestSecurityInvariants:
    """Critical security invariants that must always hold."""

    def test_no_role_grants_wider_access_than_super_admin(self):
        """No clause template should be more permissive than super admin's '1=1'."""
        for role_type, clause in RLS_CLAUSE_TEMPLATES.items():
            if role_type != UserRoleType.SUPER_ADMIN:
                assert clause != "1=1", (
                    f"Non-super-admin role type {role_type} has unrestricted access"
                )

    def test_deny_default_is_most_restrictive(self):
        """DENY_BY_DEFAULT_CLAUSE must return zero rows."""
        assert DENY_BY_DEFAULT_CLAUSE == "1=0"
        # Verify it's not accidentally set to something permissive
        assert DENY_BY_DEFAULT_CLAUSE != "1=1"
        assert "OR" not in DENY_BY_DEFAULT_CLAUSE

    def test_all_clauses_reference_tenant_id(self):
        """Every non-admin RLS clause must filter on tenant_id."""
        for role_type, clause in RLS_CLAUSE_TEMPLATES.items():
            if role_type != UserRoleType.SUPER_ADMIN:
                assert "tenant_id" in clause, (
                    f"{role_type} clause does not reference tenant_id"
                )

    def test_merchant_clause_uses_equality_not_in(self):
        """Merchant clause must use = (single tenant), never IN (which could be multi-tenant)."""
        clause = RLS_CLAUSE_TEMPLATES[UserRoleType.MERCHANT]
        assert "=" in clause
        assert "IN" not in clause

    def test_agency_clause_uses_in_not_equality(self):
        """Agency clause must use IN (multi-tenant), not = (single tenant)."""
        clause = RLS_CLAUSE_TEMPLATES[UserRoleType.AGENCY]
        assert "IN" in clause
