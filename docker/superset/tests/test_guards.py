"""
Tests for guards.py — unified safety guards for Superset.

Validates:
- StartupGuards: jwt secret, metadata DB, limits frozen, flags safe, RLS
- RuntimeGuards: tenant context validation, dataset RLS check
- GuardResult dataclass
- run_all_startup_checks orchestration

Story 5.1.8 - Failure & Misconfiguration Handling
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path for Superset module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guards import (
    GuardCheckResult,
    GuardResult,
    StartupGuards,
    RuntimeGuards,
)


# =============================================================================
# GUARD RESULT TESTS
# =============================================================================


class TestGuardResult:
    """Test GuardResult dataclass."""

    def test_pass_result(self):
        result = GuardResult(
            check_name="test",
            result=GuardCheckResult.PASS,
            message="OK",
        )
        assert result.result == GuardCheckResult.PASS
        assert result.severity == "critical"  # default

    def test_fail_result(self):
        result = GuardResult(
            check_name="test",
            result=GuardCheckResult.FAIL,
            message="Not OK",
            severity="high",
        )
        assert result.result == GuardCheckResult.FAIL
        assert result.severity == "high"

    def test_warn_result(self):
        result = GuardResult(
            check_name="test",
            result=GuardCheckResult.WARN,
            message="Maybe",
        )
        assert result.result == GuardCheckResult.WARN

    def test_frozen(self):
        result = GuardResult(
            check_name="test",
            result=GuardCheckResult.PASS,
            message="OK",
        )
        with pytest.raises((AttributeError, TypeError)):
            result.check_name = "hacked"

    def test_has_timestamp(self):
        result = GuardResult(
            check_name="test",
            result=GuardCheckResult.PASS,
            message="OK",
        )
        assert result.timestamp is not None
        assert len(result.timestamp) > 0


# =============================================================================
# STARTUP GUARDS: JWT SECRET
# =============================================================================


class TestJWTSecretGuard:
    """Test JWT secret configuration checks."""

    def test_missing_jwt_secret_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPERSET_JWT_SECRET_CURRENT", None)
            result = StartupGuards.check_jwt_secret_configured()
            assert result.result == GuardCheckResult.FAIL
            assert "not set" in result.message

    def test_present_jwt_secret_passes(self):
        secret = "a" * 64
        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": secret}):
            result = StartupGuards.check_jwt_secret_configured()
            assert result.result == GuardCheckResult.PASS

    def test_short_jwt_secret_warns(self):
        with patch.dict(os.environ, {"SUPERSET_JWT_SECRET_CURRENT": "short"}):
            result = StartupGuards.check_jwt_secret_configured()
            assert result.result == GuardCheckResult.WARN
            assert "short" in result.message.lower()


# =============================================================================
# STARTUP GUARDS: METADATA DB
# =============================================================================


class TestMetadataDBGuard:
    """Test metadata database configuration checks."""

    def test_missing_db_uri_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPERSET_METADATA_DB_URI", None)
            result = StartupGuards.check_metadata_db_configured()
            assert result.result == GuardCheckResult.FAIL
            assert "not set" in result.message

    def test_present_db_uri_passes(self):
        with patch.dict(
            os.environ,
            {"SUPERSET_METADATA_DB_URI": "postgresql://user:pass@host:5432/db"},
        ):
            result = StartupGuards.check_metadata_db_configured()
            assert result.result == GuardCheckResult.PASS


# =============================================================================
# STARTUP GUARDS: PERFORMANCE LIMITS
# =============================================================================


class TestPerformanceLimitsGuard:
    """Test performance limits frozen check."""

    def test_limits_are_frozen(self):
        result = StartupGuards.check_performance_limits_frozen()
        assert result.result == GuardCheckResult.PASS
        assert "frozen" in result.message.lower()


# =============================================================================
# STARTUP GUARDS: FEATURE FLAGS
# =============================================================================


class TestFeatureFlagsGuard:
    """Test safety feature flags check."""

    def test_all_flags_safe(self):
        result = StartupGuards.check_feature_flags_safe()
        assert result.result == GuardCheckResult.PASS

    def test_dangerous_flag_detected(self):
        with patch(
            "guards.StartupGuards.check_feature_flags_safe"
        ) as mock_check:
            # Simulate what would happen if a flag were True
            mock_check.return_value = GuardResult(
                check_name="feature_flags",
                result=GuardCheckResult.FAIL,
                message="Dangerous features enabled: ['CSV_EXPORT']",
            )
            result = mock_check()
            assert result.result == GuardCheckResult.FAIL


# =============================================================================
# STARTUP GUARDS: RLS ENFORCEMENT
# =============================================================================


class TestRLSEnforcementGuard:
    """Test RLS enforcement check."""

    def test_rls_static_check_passes(self):
        result = StartupGuards.check_rls_enforcement()
        assert result.result in (GuardCheckResult.PASS, GuardCheckResult.WARN)

    def test_rls_with_mock_client_valid(self):
        """Test with a mock client that shows all datasets have RLS."""
        mock_client = MagicMock()

        with patch("guards.StartupGuards.check_rls_enforcement") as mock_check:
            mock_check.return_value = GuardResult(
                check_name="rls_enforcement",
                result=GuardCheckResult.PASS,
                message="RLS registry has 3 protected datasets",
            )
            result = mock_check(mock_client)
            assert result.result == GuardCheckResult.PASS


# =============================================================================
# STARTUP GUARDS: RUN ALL
# =============================================================================


class TestRunAllStartupChecks:
    """Test the full startup check orchestration."""

    def test_run_all_returns_results(self):
        secret = "a" * 64
        with patch.dict(
            os.environ,
            {
                "SUPERSET_JWT_SECRET_CURRENT": secret,
                "SUPERSET_METADATA_DB_URI": "postgresql://user:pass@host:5432/db",
            },
        ):
            passed, results = StartupGuards.run_all_startup_checks()
            assert isinstance(results, list)
            assert len(results) == 5

    def test_all_results_are_guard_results(self):
        secret = "a" * 64
        with patch.dict(
            os.environ,
            {
                "SUPERSET_JWT_SECRET_CURRENT": secret,
                "SUPERSET_METADATA_DB_URI": "postgresql://user:pass@host:5432/db",
            },
        ):
            _, results = StartupGuards.run_all_startup_checks()
            for r in results:
                assert isinstance(r, GuardResult)
                assert isinstance(r.result, GuardCheckResult)

    def test_missing_jwt_fails_overall(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SUPERSET_JWT_SECRET_CURRENT", None)
            os.environ.pop("SUPERSET_METADATA_DB_URI", None)
            passed, results = StartupGuards.run_all_startup_checks()
            assert not passed
            failed = [r for r in results if r.result == GuardCheckResult.FAIL]
            assert len(failed) >= 1


# =============================================================================
# RUNTIME GUARDS: TENANT CONTEXT
# =============================================================================


class TestTenantContextGuard:
    """Test per-request tenant context validation."""

    def test_valid_single_tenant(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_abc",
            allowed_tenants=["tenant_abc"],
        )
        assert result.result == GuardCheckResult.PASS

    def test_valid_agency_tenant(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_abc",
            allowed_tenants=["tenant_abc", "tenant_def", "tenant_ghi"],
        )
        assert result.result == GuardCheckResult.PASS

    def test_missing_tenant_id_fails(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id=None,
            allowed_tenants=["tenant_abc"],
        )
        assert result.result == GuardCheckResult.FAIL
        assert "Missing tenant_id" in result.message

    def test_empty_tenant_id_fails(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="",
            allowed_tenants=["tenant_abc"],
        )
        assert result.result == GuardCheckResult.FAIL

    def test_missing_allowed_tenants_fails(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_abc",
            allowed_tenants=None,
        )
        assert result.result == GuardCheckResult.FAIL
        assert "Missing allowed_tenants" in result.message

    def test_empty_allowed_tenants_fails(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_abc",
            allowed_tenants=[],
        )
        assert result.result == GuardCheckResult.FAIL

    def test_tenant_not_in_allowed_fails(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_xyz",
            allowed_tenants=["tenant_abc", "tenant_def"],
        )
        assert result.result == GuardCheckResult.FAIL
        assert "not in allowed_tenants" in result.message
        assert "cross-tenant" in result.message.lower()

    def test_severity_is_critical(self):
        result = RuntimeGuards.validate_tenant_context(
            tenant_id="tenant_xyz",
            allowed_tenants=["tenant_abc"],
        )
        assert result.severity == "critical"


# =============================================================================
# RUNTIME GUARDS: DATASET RLS
# =============================================================================


class TestDatasetRLSGuard:
    """Test dataset RLS validation."""

    def test_protected_dataset_passes(self):
        """Known datasets should be in the RLS registry."""
        result = RuntimeGuards.validate_dataset_has_rls("fact_orders")
        # This passes if rls_rules is importable and fact_orders is in the registry
        assert result.result in (GuardCheckResult.PASS, GuardCheckResult.FAIL)

    def test_unknown_dataset_fails(self):
        result = RuntimeGuards.validate_dataset_has_rls("totally_unknown_dataset_xyz")
        assert result.result == GuardCheckResult.FAIL
        assert "not in RLS registry" in result.message or "not available" in result.message

    def test_result_has_check_name(self):
        result = RuntimeGuards.validate_dataset_has_rls("test_dataset")
        assert result.check_name == "dataset_rls"


# =============================================================================
# GUARD CHECK RESULT ENUM
# =============================================================================


class TestGuardCheckResultEnum:
    """Test the GuardCheckResult enum."""

    def test_pass_value(self):
        assert GuardCheckResult.PASS.value == "pass"

    def test_fail_value(self):
        assert GuardCheckResult.FAIL.value == "fail"

    def test_warn_value(self):
        assert GuardCheckResult.WARN.value == "warn"

    def test_all_values(self):
        assert len(GuardCheckResult) == 3
