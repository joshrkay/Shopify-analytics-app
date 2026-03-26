"""
Regression tests for billing entitlements consistency.

Ensures that:
- BILLING_TIER_FEATURES contains all expected feature keys
- Export features are gated correctly by tier
- Tier hierarchy is consistent (free < growth < pro < enterprise)
- New features (WAREHOUSE_EXPORT, SHEETS_EXPORT, SCHEDULED_EXPORTS) are present
- Seed script BILLING_PLANS matches BILLING_TIER_FEATURES (GL-3)
"""

import json
import pytest

from src.services.billing_entitlements import (
    BILLING_TIER_FEATURES,
    BillingFeature,
)
from scripts.seed_billing_plans import BILLING_PLANS, ALL_FEATURE_KEYS, PLAN_METADATA


class TestBillingTierCompleteness:
    """All tiers must have all billing features defined."""

    EXPECTED_TIERS = ["free", "growth", "pro", "enterprise"]

    def test_all_tiers_present(self):
        """All expected billing tiers exist in BILLING_TIER_FEATURES."""
        for tier in self.EXPECTED_TIERS:
            assert tier in BILLING_TIER_FEATURES, f"Missing tier: {tier}"

    def test_all_tiers_have_same_feature_keys(self):
        """All tiers define the same set of boolean feature keys."""
        # Get all BillingFeature keys (string attributes, not max_* limits)
        feature_keys = {
            v for k, v in BillingFeature.__dict__.items()
            if not k.startswith("_") and isinstance(v, str)
        }

        for tier in self.EXPECTED_TIERS:
            tier_features = BILLING_TIER_FEATURES[tier]
            for key in feature_keys:
                assert key in tier_features, (
                    f"Tier '{tier}' is missing feature key '{key}'"
                )


class TestExportFeatureGating:
    """Export features must be gated to correct billing tiers."""

    def test_data_export_free_disabled(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.DATA_EXPORT] is False

    def test_data_export_growth_enabled(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.DATA_EXPORT] is True

    def test_data_export_pro_enabled(self):
        assert BILLING_TIER_FEATURES["pro"][BillingFeature.DATA_EXPORT] is True

    def test_warehouse_export_free_disabled(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.WAREHOUSE_EXPORT] is False

    def test_warehouse_export_growth_disabled(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.WAREHOUSE_EXPORT] is False

    def test_warehouse_export_pro_enabled(self):
        assert BILLING_TIER_FEATURES["pro"][BillingFeature.WAREHOUSE_EXPORT] is True

    def test_warehouse_export_enterprise_enabled(self):
        assert BILLING_TIER_FEATURES["enterprise"][BillingFeature.WAREHOUSE_EXPORT] is True

    def test_sheets_export_free_disabled(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.SHEETS_EXPORT] is False

    def test_sheets_export_growth_enabled(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.SHEETS_EXPORT] is True

    def test_scheduled_exports_free_disabled(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.SCHEDULED_EXPORTS] is False

    def test_scheduled_exports_growth_disabled(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.SCHEDULED_EXPORTS] is False

    def test_scheduled_exports_pro_enabled(self):
        assert BILLING_TIER_FEATURES["pro"][BillingFeature.SCHEDULED_EXPORTS] is True


class TestTierHierarchy:
    """Higher tiers must have >= features than lower tiers."""

    TIER_ORDER = ["free", "growth", "pro", "enterprise"]

    def test_feature_monotonicity(self):
        """Boolean features never go from True to False as tier increases."""
        feature_keys = {
            v for k, v in BillingFeature.__dict__.items()
            if not k.startswith("_") and isinstance(v, str)
        }

        for feature in feature_keys:
            enabled_at = None
            for i, tier in enumerate(self.TIER_ORDER):
                value = BILLING_TIER_FEATURES[tier].get(feature)
                if value is True and enabled_at is None:
                    enabled_at = i
                elif value is False and enabled_at is not None:
                    pytest.fail(
                        f"Feature '{feature}' enabled at tier '{self.TIER_ORDER[enabled_at]}' "
                        f"but disabled at higher tier '{tier}'"
                    )

    def test_user_limits_increase_with_tier(self):
        """max_users increases (or stays equal) with each tier."""
        prev = 0
        for tier in self.TIER_ORDER:
            current = BILLING_TIER_FEATURES[tier].get("max_users", 0)
            assert current >= prev, (
                f"max_users decreased from {prev} to {current} at tier '{tier}'"
            )
            prev = current


class TestNewFeaturesExist:
    """New export features must be defined in the BillingFeature class."""

    def test_warehouse_export_defined(self):
        assert hasattr(BillingFeature, "WAREHOUSE_EXPORT")
        assert BillingFeature.WAREHOUSE_EXPORT == "warehouse_export"

    def test_sheets_export_defined(self):
        assert hasattr(BillingFeature, "SHEETS_EXPORT")
        assert BillingFeature.SHEETS_EXPORT == "sheets_export"

    def test_scheduled_exports_defined(self):
        assert hasattr(BillingFeature, "SCHEDULED_EXPORTS")
        assert BillingFeature.SCHEDULED_EXPORTS == "scheduled_exports"

    def test_data_export_defined(self):
        assert hasattr(BillingFeature, "DATA_EXPORT")
        assert BillingFeature.DATA_EXPORT == "data_export"


class TestPlansJsonConsistency:
    """plans.json must be valid and contain expected structure."""

    @pytest.fixture
    def plans_data(self):
        import os
        # Try both possible locations
        for path in ["config/plans.json", "../config/plans.json"]:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        pytest.skip("config/plans.json not found")

    def test_plans_json_parses(self, plans_data):
        """plans.json is valid JSON."""
        assert isinstance(plans_data, dict)

    def test_plans_key_exists(self, plans_data):
        """plans.json has a 'plans' key."""
        assert "plans" in plans_data

    def test_free_plan_exists(self, plans_data):
        """Free plan is defined."""
        plans = plans_data["plans"]
        if isinstance(plans, dict):
            assert "free" in plans
        elif isinstance(plans, list):
            ids = {p.get("id", "") for p in plans}
            names = {p.get("display_name", "").lower() for p in plans}
            assert "plan_free" in ids or "free" in names or "free" in ids

    def test_plans_have_features(self, plans_data):
        """Each plan has a 'features' field."""
        plans = plans_data["plans"]
        if isinstance(plans, dict):
            for plan_name, plan_data in plans.items():
                assert "features" in plan_data, f"Plan '{plan_name}' missing 'features'"
        elif isinstance(plans, list):
            for plan in plans:
                plan_id = plan.get("id", "unknown")
                assert "features" in plan, f"Plan '{plan_id}' missing 'features'"

    def test_plans_have_limits(self, plans_data):
        """Each plan has a 'limits' field."""
        plans = plans_data["plans"]
        if isinstance(plans, dict):
            for plan_name, plan_data in plans.items():
                assert "limits" in plan_data, f"Plan '{plan_name}' missing 'limits'"
        elif isinstance(plans, list):
            for plan in plans:
                plan_id = plan.get("id", "unknown")
                assert "limits" in plan, f"Plan '{plan_id}' missing 'limits'"


class TestPlanFeatureSeedSync:
    """Seed script BILLING_PLANS must stay in sync with BILLING_TIER_FEATURES (GL-3)."""

    EXPECTED_TIERS = ["free", "growth", "pro", "enterprise"]

    REQUIRED_FEATURE_KEYS = [
        "ai_insights", "ai_recommendations", "ai_actions", "custom_reports",
        "advanced_dashboards", "agency_access", "data_export", "warehouse_export",
        "cohort_analysis", "budget_pacing", "alerts",
    ]

    def test_seed_has_four_canonical_plans(self):
        """BILLING_PLANS contains exactly 4 plans matching the canonical tiers."""
        seed_names = {p["name"] for p in BILLING_PLANS}
        assert seed_names == set(self.EXPECTED_TIERS), (
            f"Seed plans {seed_names} != expected {set(self.EXPECTED_TIERS)}"
        )

    def test_seed_plan_ids_are_deterministic(self):
        """Plan IDs follow the plan_<tier> convention."""
        for plan in BILLING_PLANS:
            assert plan["id"] == f"plan_{plan['name']}", (
                f"Plan '{plan['name']}' has non-deterministic ID '{plan['id']}'"
            )

    def test_seed_has_all_feature_keys_per_plan(self):
        """Every plan in the seed defines all BillingFeature keys."""
        for plan in BILLING_PLANS:
            seed_keys = {f["feature_key"] for f in plan["features"]}
            for key in ALL_FEATURE_KEYS:
                assert key in seed_keys, (
                    f"Plan '{plan['name']}' seed is missing feature '{key}'"
                )

    def test_seed_enabled_matches_billing_tier_features(self):
        """is_enabled in seed matches the boolean in BILLING_TIER_FEATURES."""
        for plan in BILLING_PLANS:
            tier = plan["name"]
            tier_features = BILLING_TIER_FEATURES[tier]
            for feat in plan["features"]:
                fkey = feat["feature_key"]
                expected = bool(tier_features.get(fkey, False))
                assert feat["is_enabled"] == expected, (
                    f"Plan '{tier}' feature '{fkey}': "
                    f"seed is_enabled={feat['is_enabled']} but "
                    f"BILLING_TIER_FEATURES={expected}"
                )

    def test_required_feature_keys_present_in_billing_feature(self):
        """All acceptance-criteria feature keys exist in BillingFeature."""
        for key in self.REQUIRED_FEATURE_KEYS:
            assert key in ALL_FEATURE_KEYS, (
                f"Required feature key '{key}' not in BillingFeature constants"
            )

    def test_seed_metadata_matches_plan_metadata(self):
        """BILLING_PLANS pricing matches PLAN_METADATA."""
        for plan in BILLING_PLANS:
            meta = PLAN_METADATA[plan["name"]]
            assert plan["price_monthly_cents"] == meta["price_monthly_cents"]
            assert plan["price_yearly_cents"] == meta["price_yearly_cents"]

    def test_all_feature_keys_cover_acceptance_criteria(self):
        """The 11 feature keys from acceptance criteria are all seeded for every plan."""
        for plan in BILLING_PLANS:
            seed_keys = {f["feature_key"] for f in plan["features"]}
            for key in self.REQUIRED_FEATURE_KEYS:
                assert key in seed_keys, (
                    f"Plan '{plan['name']}' missing AC feature '{key}'"
                )
