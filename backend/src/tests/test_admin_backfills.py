"""
Tests for Story 3.4 - Admin Backfill Request API.

Tests:
- Idempotency key computation
- Backfill validator (tenant, date range, overlap, idempotency)
- Pydantic schema validation
- Source system enum
- Security: super admin authorization

Run with: pytest src/tests/test_admin_backfills.py -v
"""

import hashlib
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from src.api.schemas.backfill_request import (
    CreateBackfillRequest,
    SourceSystem,
    BackfillRequestResponse,
    BackfillRequestCreatedResponse,
)
from src.services.backfill_validator import (
    BackfillValidator,
    compute_idempotency_key,
    TenantNotFoundError,
    TenantNotActiveError,
    DateRangeExceededError,
    OverlappingBackfillError,
    TIER_MAX_BACKFILL_DAYS,
    DEFAULT_MAX_BACKFILL_DAYS,
)
from src.models.historical_backfill import (
    HistoricalBackfillRequest,
    HistoricalBackfillStatus,
    ACTIVE_BACKFILL_STATUSES,
)


# =============================================================================
# Idempotency Key Tests
# =============================================================================


class TestIdempotencyKey:
    """Tests for compute_idempotency_key."""

    def test_same_inputs_produce_same_key(self):
        key1 = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        key2 = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        assert key1 == key2

    def test_different_tenant_produces_different_key(self):
        key1 = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        key2 = compute_idempotency_key("t2", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        assert key1 != key2

    def test_different_source_produces_different_key(self):
        key1 = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        key2 = compute_idempotency_key("t1", "facebook", date(2024, 1, 1), date(2024, 3, 31))
        assert key1 != key2

    def test_different_dates_produce_different_key(self):
        key1 = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        key2 = compute_idempotency_key("t1", "shopify", date(2024, 1, 2), date(2024, 3, 31))
        assert key1 != key2

    def test_key_is_sha256_hex(self):
        key = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        assert len(key) == 64  # SHA-256 hex digest length
        int(key, 16)  # Should parse as hex

    def test_key_matches_expected_hash(self):
        canonical = "t1|shopify|2024-01-01|2024-03-31"
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        actual = compute_idempotency_key("t1", "shopify", date(2024, 1, 1), date(2024, 3, 31))
        assert actual == expected


# =============================================================================
# Source System Enum Tests
# =============================================================================


class TestSourceSystemEnum:
    """Tests for SourceSystem enum."""

    def test_all_expected_sources_exist(self):
        expected = {
            "shopify", "facebook", "google", "tiktok",
            "pinterest", "snapchat", "amazon", "klaviyo",
            "recharge", "ga4",
        }
        actual = {s.value for s in SourceSystem}
        assert actual == expected

    def test_values_are_lowercase(self):
        for source in SourceSystem:
            assert source.value == source.value.lower()


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestCreateBackfillRequestSchema:
    """Tests for Pydantic schema validation."""

    def test_valid_request_accepted(self):
        req = CreateBackfillRequest(
            tenant_id="tenant_123",
            source_system=SourceSystem.SHOPIFY,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            reason="Data gap after connector migration on 2024-01-15",
        )
        assert req.tenant_id == "tenant_123"
        assert req.source_system == SourceSystem.SHOPIFY
        assert req.start_date == date(2024, 1, 1)
        assert req.end_date == date(2024, 3, 31)

    def test_start_after_end_rejected(self):
        with pytest.raises(ValueError, match="start_date.*must be before"):
            CreateBackfillRequest(
                tenant_id="tenant_123",
                source_system=SourceSystem.SHOPIFY,
                start_date=date(2024, 3, 31),
                end_date=date(2024, 1, 1),
                reason="This should fail because dates are reversed",
            )

    def test_future_end_date_rejected(self):
        future = date.today() + timedelta(days=30)
        with pytest.raises(ValueError, match="end_date cannot be in the future"):
            CreateBackfillRequest(
                tenant_id="tenant_123",
                source_system=SourceSystem.SHOPIFY,
                start_date=date(2024, 1, 1),
                end_date=future,
                reason="This should fail because end date is in the future",
            )

    def test_reason_too_short_rejected(self):
        with pytest.raises(ValueError):
            CreateBackfillRequest(
                tenant_id="tenant_123",
                source_system=SourceSystem.SHOPIFY,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
                reason="Short",  # min_length=10
            )

    def test_empty_tenant_id_rejected(self):
        with pytest.raises(ValueError):
            CreateBackfillRequest(
                tenant_id="",
                source_system=SourceSystem.SHOPIFY,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
                reason="Valid reason for backfill request",
            )

    def test_invalid_source_system_rejected(self):
        with pytest.raises(ValueError):
            CreateBackfillRequest(
                tenant_id="tenant_123",
                source_system="invalid_source",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
                reason="Valid reason for backfill request",
            )

    def test_same_start_and_end_date_accepted(self):
        """Single-day backfill is valid."""
        req = CreateBackfillRequest(
            tenant_id="tenant_123",
            source_system=SourceSystem.SHOPIFY,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            reason="Single day reprocess after bug fix",
        )
        assert req.start_date == req.end_date


# =============================================================================
# Backfill Validator - Tenant Tests
# =============================================================================


def _mock_tenant(tenant_id="tenant_123", status="active", billing_tier="free"):
    """Create a mock tenant object."""
    from src.models.tenant import TenantStatus
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.status = TenantStatus(status)
    tenant.billing_tier = billing_tier
    return tenant


class TestBackfillValidatorTenant:
    """Tests for tenant validation."""

    def test_valid_active_tenant_passes(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            _mock_tenant()
        )

        validator = BackfillValidator(mock_db)
        tenant = validator.validate_tenant("tenant_123")
        assert tenant.id == "tenant_123"

    def test_nonexistent_tenant_raises_not_found(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        validator = BackfillValidator(mock_db)
        with pytest.raises(TenantNotFoundError, match="not found"):
            validator.validate_tenant("nonexistent")

    def test_suspended_tenant_raises_not_active(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            _mock_tenant(status="suspended")
        )

        validator = BackfillValidator(mock_db)
        with pytest.raises(TenantNotActiveError, match="not active"):
            validator.validate_tenant("tenant_123")

    def test_deactivated_tenant_raises_not_active(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            _mock_tenant(status="deactivated")
        )

        validator = BackfillValidator(mock_db)
        with pytest.raises(TenantNotActiveError, match="not active"):
            validator.validate_tenant("tenant_123")


# =============================================================================
# Backfill Validator - Date Range Tests
# =============================================================================


class TestBackfillValidatorDateRange:
    """Tests for date range validation against billing tier limits."""

    def test_free_tier_90_day_limit_passes(self):
        validator = BackfillValidator(MagicMock())
        days = validator.validate_date_range(
            date(2024, 1, 1), date(2024, 3, 30), "free"  # 90 days
        )
        assert days == 90

    def test_free_tier_91_day_limit_fails(self):
        validator = BackfillValidator(MagicMock())
        with pytest.raises(DateRangeExceededError, match="91 days.*90 days.*free"):
            validator.validate_date_range(
                date(2024, 1, 1), date(2024, 3, 31), "free"  # 91 days
            )

    def test_growth_tier_90_day_limit_passes(self):
        validator = BackfillValidator(MagicMock())
        days = validator.validate_date_range(
            date(2024, 1, 1), date(2024, 3, 30), "growth"
        )
        assert days == 90

    def test_growth_tier_91_day_limit_fails(self):
        validator = BackfillValidator(MagicMock())
        with pytest.raises(DateRangeExceededError, match="growth"):
            validator.validate_date_range(
                date(2024, 1, 1), date(2024, 3, 31), "growth"
            )

    def test_enterprise_tier_365_days_passes(self):
        validator = BackfillValidator(MagicMock())
        # 365 days: Jan 1 to Dec 30 (non-leap year logic)
        days = validator.validate_date_range(
            date(2023, 1, 1), date(2023, 12, 31), "enterprise"  # 365 days exactly
        )
        assert days == 365

    def test_enterprise_tier_366_day_fails(self):
        validator = BackfillValidator(MagicMock())
        with pytest.raises(DateRangeExceededError, match="enterprise"):
            # 366 days in 2024 (leap year)
            validator.validate_date_range(
                date(2024, 1, 1), date(2024, 12, 31), "enterprise"
            )

    def test_unknown_tier_uses_default_90_days(self):
        validator = BackfillValidator(MagicMock())
        with pytest.raises(DateRangeExceededError, match="91 days.*90 days"):
            validator.validate_date_range(
                date(2024, 1, 1), date(2024, 3, 31), "unknown_tier"
            )

    def test_single_day_backfill_passes(self):
        validator = BackfillValidator(MagicMock())
        days = validator.validate_date_range(
            date(2024, 1, 1), date(2024, 1, 1), "free"
        )
        assert days == 1

    def test_tier_constants_are_correct(self):
        assert TIER_MAX_BACKFILL_DAYS["free"] == 90
        assert TIER_MAX_BACKFILL_DAYS["growth"] == 90
        assert TIER_MAX_BACKFILL_DAYS["enterprise"] == 365
        assert DEFAULT_MAX_BACKFILL_DAYS == 90


# =============================================================================
# Backfill Validator - Overlap Tests
# =============================================================================


class TestBackfillValidatorOverlap:
    """Tests for overlapping backfill detection."""

    def test_no_active_backfills_passes(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        validator = BackfillValidator(mock_db)
        # Should not raise
        validator.check_overlapping_backfills(
            "tenant_123", "shopify", date(2024, 1, 1), date(2024, 3, 31)
        )

    def test_overlapping_active_backfill_raises(self):
        existing = MagicMock()
        existing.id = "existing_backfill_id"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        validator = BackfillValidator(mock_db)
        with pytest.raises(OverlappingBackfillError, match="existing_backfill_id"):
            validator.check_overlapping_backfills(
                "tenant_123", "shopify", date(2024, 1, 1), date(2024, 3, 31)
            )


# =============================================================================
# Backfill Validator - Full Pipeline Tests
# =============================================================================


class TestBackfillValidatorPipeline:
    """Tests for the full validate_and_prepare pipeline."""

    def test_first_request_returns_none_and_true(self):
        mock_db = MagicMock()
        # find_idempotent_match returns None (no existing)
        # validate_tenant returns active tenant
        # check_overlapping returns None

        mock_tenant = _mock_tenant(billing_tier="free")

        # Setup chain: idempotent check returns None, tenant check returns tenant, overlap returns None
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,           # find_idempotent_match
            mock_tenant,    # validate_tenant
            None,           # check_overlapping_backfills
        ]

        validator = BackfillValidator(mock_db)
        existing, is_new = validator.validate_and_prepare(
            "tenant_123", "shopify", date(2024, 1, 1), date(2024, 3, 30)
        )
        assert existing is None
        assert is_new is True

    def test_idempotent_match_returns_existing_and_false(self):
        existing_request = MagicMock()
        existing_request.id = "existing_id"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            existing_request
        )

        validator = BackfillValidator(mock_db)
        result, is_new = validator.validate_and_prepare(
            "tenant_123", "shopify", date(2024, 1, 1), date(2024, 3, 31)
        )
        assert result is existing_request
        assert is_new is False


# =============================================================================
# Model Tests
# =============================================================================


class TestHistoricalBackfillModel:
    """Tests for the HistoricalBackfillRequest model."""

    def test_status_enum_values(self):
        expected = {"pending", "approved", "running", "completed", "failed", "cancelled", "rejected"}
        actual = {s.value for s in HistoricalBackfillStatus}
        assert actual == expected

    def test_active_statuses_are_correct(self):
        active_values = {s.value for s in ACTIVE_BACKFILL_STATUSES}
        assert active_values == {"pending", "approved", "running"}

    def test_model_defaults(self):
        record = HistoricalBackfillRequest(
            tenant_id="tenant_123",
            source_system="shopify",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            reason="Test backfill",
            requested_by="admin_user",
            idempotency_key="test_key",
        )
        assert record.tenant_id == "tenant_123"
        assert record.source_system == "shopify"
        assert record.started_at is None
        assert record.completed_at is None
        assert record.error_message is None

    def test_model_repr(self):
        record = HistoricalBackfillRequest(
            id="test_id",
            tenant_id="tenant_123",
            source_system="shopify",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            status=HistoricalBackfillStatus.PENDING,
            reason="Test",
            requested_by="admin",
            idempotency_key="key",
        )
        repr_str = repr(record)
        assert "test_id" in repr_str
        assert "tenant_123" in repr_str
        assert "shopify" in repr_str


# =============================================================================
# Response Schema Tests
# =============================================================================


class TestBackfillResponseSchemas:
    """Tests for response Pydantic models."""

    def test_backfill_request_response(self):
        resp = BackfillRequestResponse(
            id="bf_123",
            tenant_id="tenant_123",
            source_system="shopify",
            start_date="2024-01-01",
            end_date="2024-03-31",
            status="pending",
            reason="Test reason for backfill",
            requested_by="admin_user",
            idempotency_key="abc123",
        )
        assert resp.id == "bf_123"
        assert resp.status == "pending"

    def test_backfill_created_response(self):
        inner = BackfillRequestResponse(
            id="bf_123",
            tenant_id="tenant_123",
            source_system="shopify",
            start_date="2024-01-01",
            end_date="2024-03-31",
            status="pending",
            reason="Test reason for backfill",
            requested_by="admin_user",
            idempotency_key="abc123",
        )
        resp = BackfillRequestCreatedResponse(
            backfill_request=inner,
            created=True,
            message="Backfill request created successfully",
        )
        assert resp.created is True
        assert resp.backfill_request.id == "bf_123"


# =============================================================================
# Security Tests
# =============================================================================


class TestSecurityConstraints:
    """Tests for security properties of the backfill system."""

    def test_validator_requires_active_tenant(self):
        """Backfills should be rejected for suspended tenants."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            _mock_tenant(status="suspended")
        )
        validator = BackfillValidator(mock_db)
        with pytest.raises(TenantNotActiveError):
            validator.validate_tenant("tenant_123")

    def test_tier_limits_enforced(self):
        """Free tier should not allow > 90 days."""
        validator = BackfillValidator(MagicMock())
        with pytest.raises(DateRangeExceededError):
            validator.validate_date_range(
                date(2024, 1, 1), date(2024, 12, 31), "free"
            )

    def test_no_secrets_in_model(self):
        """Model should not expose sensitive fields."""
        record = HistoricalBackfillRequest(
            tenant_id="t", source_system="shopify",
            start_date=date(2024, 1, 1), end_date=date(2024, 1, 1),
            reason="test", requested_by="admin", idempotency_key="key",
        )
        assert not hasattr(record, "access_token")
        assert not hasattr(record, "api_key")
        assert not hasattr(record, "secret")

    def test_active_statuses_exclude_terminal_states(self):
        """Terminal states should not block new backfills."""
        terminal = {
            HistoricalBackfillStatus.COMPLETED,
            HistoricalBackfillStatus.FAILED,
            HistoricalBackfillStatus.CANCELLED,
            HistoricalBackfillStatus.REJECTED,
        }
        active_set = set(ACTIVE_BACKFILL_STATUSES)
        assert active_set.isdisjoint(terminal)


# =============================================================================
# Backfill Planner Tests
# =============================================================================


from src.services.backfill_planner import (
    BackfillPlanner,
    MODEL_REGISTRY,
    SOURCE_TO_STAGING,
    SOURCE_INGESTION_TABLES,
    ModelLayer,
    _DEPENDENTS,
)


class TestBackfillPlannerDependencyGraph:
    """Tests for the dependency graph resolution."""

    def test_shopify_resolves_full_downstream(self):
        planner = BackfillPlanner()
        affected = planner._resolve_downstream(["stg_shopify_orders"])
        # Must include the seed
        assert "stg_shopify_orders" in affected
        # Must include direct canonical dependents
        assert "orders" in affected
        assert "fact_orders_v1" in affected
        # Must include transitive dependents
        assert "fct_revenue" in affected
        assert "sem_orders_v1" in affected
        assert "fact_orders_current" in affected
        assert "last_click" in affected
        assert "fct_roas" in affected
        assert "mart_revenue_metrics" in affected

    def test_facebook_resolves_ads_downstream(self):
        planner = BackfillPlanner()
        affected = planner._resolve_downstream(["stg_facebook_ads_performance"])
        assert "marketing_spend" in affected
        assert "campaign_performance" in affected
        assert "sem_marketing_spend_v1" in affected
        assert "dim_ad_accounts" in affected
        assert "dim_campaigns" in affected
        # Should NOT include shopify-only models
        assert "stg_shopify_orders" not in affected

    def test_unknown_model_ignored(self):
        planner = BackfillPlanner()
        affected = planner._resolve_downstream(["nonexistent_model"])
        assert len(affected) == 0

    def test_empty_seeds_returns_empty(self):
        planner = BackfillPlanner()
        affected = planner._resolve_downstream([])
        assert len(affected) == 0

    def test_tiktok_only_affects_marketing_spend(self):
        """TikTok should affect marketing_spend but NOT campaign_performance."""
        planner = BackfillPlanner()
        affected = planner._resolve_downstream(["stg_tiktok_ads_performance"])
        assert "marketing_spend" in affected
        assert "fact_marketing_spend_v1" in affected
        # campaign_performance only depends on facebook + google
        assert "campaign_performance" not in affected


class TestBackfillPlannerPlan:
    """Tests for the full plan() method."""

    def test_shopify_plan_has_all_fields(self):
        planner = BackfillPlanner()
        plan = planner.plan(
            tenant_id="tenant_123",
            source_system="shopify",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert plan.tenant_id == "tenant_123"
        assert plan.source_system == "shopify"
        assert plan.start_date == date(2024, 1, 1)
        assert plan.end_date == date(2024, 1, 31)
        assert len(plan.ingestion_tables) > 0
        assert len(plan.affected_models) > 0
        assert len(plan.execution_steps) > 0
        assert plan.cost_estimate.date_range_days == 31
        assert plan.cost_estimate.estimated_raw_rows > 0
        assert plan.is_partial is True  # Shopify doesn't affect all models
        assert "dbt run" in plan.dbt_run_command
        assert "tenant_123" in plan.dbt_run_command

    def test_execution_steps_are_ordered_by_layer(self):
        planner = BackfillPlanner()
        plan = planner.plan(
            tenant_id="t1",
            source_system="shopify",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 7),
        )
        layer_orders = []
        for step in plan.execution_steps:
            layer = ModelLayer(step.layer)
            layer_orders.append(layer.order)
        # Must be monotonically non-decreasing
        assert layer_orders == sorted(layer_orders)

    def test_ingestion_tables_for_shopify(self):
        planner = BackfillPlanner()
        plan = planner.plan("t1", "shopify", date(2024, 1, 1), date(2024, 1, 7))
        assert "_airbyte_raw_shopify_orders" in plan.ingestion_tables
        assert "_airbyte_raw_shopify_customers" in plan.ingestion_tables

    def test_ingestion_tables_for_facebook(self):
        planner = BackfillPlanner()
        plan = planner.plan("t1", "facebook", date(2024, 1, 1), date(2024, 1, 7))
        assert "_airbyte_raw_meta_ads" in plan.ingestion_tables

    def test_unknown_source_returns_empty_plan(self):
        planner = BackfillPlanner()
        plan = planner.plan("t1", "nonexistent", date(2024, 1, 1), date(2024, 1, 7))
        assert plan.affected_models == []
        assert plan.ingestion_tables == []
        assert plan.execution_steps == []


class TestBackfillPlannerCostEstimate:
    """Tests for cost estimation."""

    def test_longer_range_costs_more(self):
        planner = BackfillPlanner()
        plan_7d = planner.plan("t1", "shopify", date(2024, 1, 1), date(2024, 1, 7))
        plan_30d = planner.plan("t1", "shopify", date(2024, 1, 1), date(2024, 1, 30))
        assert plan_30d.cost_estimate.estimated_raw_rows > plan_7d.cost_estimate.estimated_raw_rows
        assert plan_30d.cost_estimate.estimated_seconds > plan_7d.cost_estimate.estimated_seconds

    def test_single_day_cost(self):
        planner = BackfillPlanner()
        plan = planner.plan("t1", "shopify", date(2024, 1, 1), date(2024, 1, 1))
        assert plan.cost_estimate.date_range_days == 1
        assert plan.cost_estimate.estimated_raw_rows == 500  # shopify rows_per_day

    def test_cost_estimate_fields_positive(self):
        planner = BackfillPlanner()
        plan = planner.plan("t1", "facebook", date(2024, 1, 1), date(2024, 1, 31))
        assert plan.cost_estimate.estimated_raw_rows > 0
        assert plan.cost_estimate.estimated_total_rows >= plan.cost_estimate.estimated_raw_rows
        assert plan.cost_estimate.estimated_seconds >= 0


class TestBackfillPlannerRegistry:
    """Tests for the model registry and source mappings."""

    def test_all_source_systems_have_staging_mapping(self):
        """Every source in SourceSystem enum should have a staging mapping."""
        from src.api.schemas.backfill_request import SourceSystem
        for source in SourceSystem:
            assert source.value in SOURCE_TO_STAGING, (
                f"Missing SOURCE_TO_STAGING entry for {source.value}"
            )

    def test_all_source_systems_have_ingestion_mapping(self):
        from src.api.schemas.backfill_request import SourceSystem
        for source in SourceSystem:
            assert source.value in SOURCE_INGESTION_TABLES, (
                f"Missing SOURCE_INGESTION_TABLES entry for {source.value}"
            )

    def test_all_staging_models_exist_in_registry(self):
        """Every model referenced in SOURCE_TO_STAGING must be in MODEL_REGISTRY."""
        for source, models in SOURCE_TO_STAGING.items():
            for model_name in models:
                assert model_name in MODEL_REGISTRY, (
                    f"Staging model '{model_name}' for source '{source}' "
                    f"not found in MODEL_REGISTRY"
                )

    def test_all_depends_on_exist_in_registry(self):
        """Every dependency reference must point to an existing model."""
        for name, model in MODEL_REGISTRY.items():
            for dep in model.depends_on:
                assert dep in MODEL_REGISTRY, (
                    f"Model '{name}' depends on '{dep}' which is not in MODEL_REGISTRY"
                )

    def test_dependents_index_is_consistent(self):
        """The reverse index must be consistent with depends_on."""
        for name, model in MODEL_REGISTRY.items():
            for dep in model.depends_on:
                assert name in _DEPENDENTS.get(dep, set()), (
                    f"'{name}' depends on '{dep}' but is not in _DEPENDENTS['{dep}']"
                )

    def test_staging_models_have_no_internal_deps(self):
        """Staging models (except aggregations) should have no depends_on."""
        # stg_email_campaigns depends on stg_klaviyo_events — that's the exception
        exceptions = {"stg_email_campaigns", "dim_ad_accounts", "dim_campaigns"}
        for name, model in MODEL_REGISTRY.items():
            if model.layer == ModelLayer.STAGING and name not in exceptions:
                assert model.depends_on == (), (
                    f"Staging model '{name}' has unexpected deps: {model.depends_on}"
                )
