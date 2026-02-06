"""
Tests for performance_config.py — centralized performance limits.

Validates:
- Frozen dataclass (immutable)
- Exact default values
- Derived constants match
- Safety feature flags
- Cache TTL property

Story 5.1.6 - Performance & Safety Defaults
"""

import sys
import os
import pytest

# Add parent directory to path for Superset module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from performance_config import (
    PerformanceLimits,
    PERFORMANCE_LIMITS,
    SQL_MAX_ROW,
    ROW_LIMIT,
    SAMPLES_ROW_LIMIT,
    SQLLAB_TIMEOUT,
    SQLLAB_ASYNC_TIME_LIMIT_SEC,
    SUPERSET_WEBSERVER_TIMEOUT,
    CACHE_DEFAULT_TIMEOUT,
    EXPLORE_CACHE_TTL,
    SAFETY_FEATURE_FLAGS,
)


# =============================================================================
# FROZEN DATACLASS TESTS
# =============================================================================


class TestPerformanceLimitsFrozen:
    """Performance limits must be immutable."""

    def test_cannot_modify_row_limit(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.row_limit = 999_999

    def test_cannot_modify_query_timeout(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.query_timeout_seconds = 300

    def test_cannot_modify_max_date_range(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.max_date_range_days = 365

    def test_cannot_modify_cache_ttl(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.cache_ttl_seconds = 86400

    def test_cannot_modify_export_flag(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.allow_file_export = True

    def test_cannot_add_new_attribute(self):
        with pytest.raises((AttributeError, TypeError)):
            PERFORMANCE_LIMITS.new_attr = "hacked"


# =============================================================================
# EXACT VALUE TESTS
# =============================================================================


class TestPerformanceLimitsValues:
    """Verify exact production values."""

    def test_query_timeout_20s(self):
        assert PERFORMANCE_LIMITS.query_timeout_seconds == 20

    def test_row_limit_50k(self):
        assert PERFORMANCE_LIMITS.row_limit == 50_000

    def test_samples_row_limit_1k(self):
        assert PERFORMANCE_LIMITS.samples_row_limit == 1_000

    def test_max_date_range_90_days(self):
        assert PERFORMANCE_LIMITS.max_date_range_days == 90

    def test_max_group_by_2(self):
        assert PERFORMANCE_LIMITS.max_group_by_dimensions == 2

    def test_max_filters_10(self):
        assert PERFORMANCE_LIMITS.max_filters == 10

    def test_max_metrics_per_query_5(self):
        assert PERFORMANCE_LIMITS.max_metrics_per_query == 5

    def test_cache_ttl_1800s(self):
        assert PERFORMANCE_LIMITS.cache_ttl_seconds == 1800

    def test_cache_key_prefix(self):
        assert PERFORMANCE_LIMITS.cache_key_prefix == "explore_data_"

    def test_webserver_timeout_30s(self):
        assert PERFORMANCE_LIMITS.webserver_timeout_seconds == 30

    def test_webserver_timeout_exceeds_query_timeout(self):
        assert (
            PERFORMANCE_LIMITS.webserver_timeout_seconds
            > PERFORMANCE_LIMITS.query_timeout_seconds
        )

    def test_exports_disabled(self):
        assert PERFORMANCE_LIMITS.allow_file_export is False
        assert PERFORMANCE_LIMITS.allow_csv_export is False
        assert PERFORMANCE_LIMITS.allow_pivot_export is False


# =============================================================================
# DERIVED CONSTANTS TESTS
# =============================================================================


class TestDerivedConstants:
    """Derived constants must match PERFORMANCE_LIMITS."""

    def test_sql_max_row(self):
        assert SQL_MAX_ROW == PERFORMANCE_LIMITS.row_limit

    def test_row_limit(self):
        assert ROW_LIMIT == PERFORMANCE_LIMITS.row_limit

    def test_samples_row_limit(self):
        assert SAMPLES_ROW_LIMIT == PERFORMANCE_LIMITS.samples_row_limit

    def test_sqllab_timeout(self):
        assert SQLLAB_TIMEOUT == PERFORMANCE_LIMITS.query_timeout_seconds

    def test_sqllab_async_time_limit(self):
        assert SQLLAB_ASYNC_TIME_LIMIT_SEC == PERFORMANCE_LIMITS.query_timeout_seconds

    def test_webserver_timeout(self):
        assert SUPERSET_WEBSERVER_TIMEOUT == PERFORMANCE_LIMITS.webserver_timeout_seconds

    def test_cache_default_timeout(self):
        assert CACHE_DEFAULT_TIMEOUT == PERFORMANCE_LIMITS.cache_ttl_seconds

    def test_explore_cache_ttl(self):
        assert EXPLORE_CACHE_TTL == PERFORMANCE_LIMITS.cache_ttl_seconds


# =============================================================================
# CACHE TTL PROPERTY
# =============================================================================


class TestCacheTTLProperty:
    """Test the cache_ttl_minutes derived property."""

    def test_cache_ttl_minutes(self):
        assert PERFORMANCE_LIMITS.cache_ttl_minutes == 30

    def test_cache_ttl_minutes_matches_seconds(self):
        assert PERFORMANCE_LIMITS.cache_ttl_minutes == PERFORMANCE_LIMITS.cache_ttl_seconds // 60


# =============================================================================
# SAFETY FEATURE FLAGS
# =============================================================================


class TestSafetyFeatureFlags:
    """All dangerous features must be disabled."""

    def test_custom_metrics_disabled(self):
        assert SAFETY_FEATURE_FLAGS["ENABLE_CUSTOM_METRICS"] is False

    def test_sql_queries_disabled(self):
        assert SAFETY_FEATURE_FLAGS["SQL_QUERIES_ALLOWED"] is False

    def test_csv_export_disabled(self):
        assert SAFETY_FEATURE_FLAGS["CSV_EXPORT"] is False

    def test_sqllab_persistence_disabled(self):
        assert SAFETY_FEATURE_FLAGS["SQLLAB_BACKEND_PERSISTENCE"] is False

    def test_subquery_disabled(self):
        assert SAFETY_FEATURE_FLAGS["EXPLORE_ALLOW_SUBQUERY"] is False
        assert SAFETY_FEATURE_FLAGS["ALLOW_ADHOC_SUBQUERY"] is False

    def test_template_processing_disabled(self):
        assert SAFETY_FEATURE_FLAGS["ENABLE_TEMPLATE_PROCESSING"] is False

    def test_pivot_export_disabled(self):
        assert SAFETY_FEATURE_FLAGS["ENABLE_PIVOT_TABLE_DATA_EXPORT"] is False

    def test_all_safety_flags_are_false(self):
        """Every flag in SAFETY_FEATURE_FLAGS must be False."""
        for flag, value in SAFETY_FEATURE_FLAGS.items():
            assert value is False, f"Safety flag '{flag}' should be False but is {value}"

    def test_no_empty_flags(self):
        """Safety flags dict must not be empty."""
        assert len(SAFETY_FEATURE_FLAGS) > 0


# =============================================================================
# INSTANTIATION
# =============================================================================


class TestInstantiation:
    """Test creating custom instances (for testing only)."""

    def test_default_instance(self):
        limits = PerformanceLimits()
        assert limits.row_limit == 50_000

    def test_custom_values(self):
        limits = PerformanceLimits(row_limit=100, query_timeout_seconds=5)
        assert limits.row_limit == 100
        assert limits.query_timeout_seconds == 5

    def test_singleton_is_default(self):
        """PERFORMANCE_LIMITS must use all default values."""
        fresh = PerformanceLimits()
        assert PERFORMANCE_LIMITS.row_limit == fresh.row_limit
        assert PERFORMANCE_LIMITS.query_timeout_seconds == fresh.query_timeout_seconds
        assert PERFORMANCE_LIMITS.cache_ttl_seconds == fresh.cache_ttl_seconds
