"""
Entitlements: upgrade, downgrade, override apply/remove, override expiry,
Shopify drift reconciliation, cache invalidation, fail-closed, audit/alert signals.
Target ≥90% coverage.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.entitlements import loader as loader_mod
from src.entitlements.loader import (
    load_plans,
    get_plan_features,
    get_loaded_plans,
    DEFAULT_PLANS_PATH,
)
from src.entitlements.models import (
    EntitlementSet,
    OverrideEntry,
    PlanConfig,
    ResolutionResult,
)
from src.entitlements.cache import get_cached, set_cached, delete_cached, _key
from src.entitlements.overrides import (
    can_manage_overrides,
    ALLOWED_OVERRIDE_ROLES,
)
from src.entitlements.service import (
    get_entitlements,
    invalidate_entitlements,
    has_feature,
)
from src.monitoring.entitlement_alerts import (
    DENY_THRESHOLD_PER_MIN,
    record_deny_and_alert,
    emit_evaluation_failure,
)


# ----- Loader & config -----

def test_loader_plan_config_immutable():
    config = PlanConfig(name="free", features=("a", "b"))
    assert config.name == "free"
    assert config.features == ("a", "b")
    with pytest.raises(AttributeError):
        config.features = ("x",)


def test_loader_get_plan_features_returns_tuple(tmp_path):
    loader_mod._plans_cache = None
    plans_file = tmp_path / "plans.json"
    plans_file.write_text(json.dumps({
        "plans": {
            "free": {"features": ["f1"]},
            "growth": {"features": ["f1", "f2"]},
            "enterprise": {"features": ["f1", "f2", "f3"]},
        }
    }))
    load_plans(plans_file)
    assert get_plan_features("free") == ("f1",)
    assert get_plan_features("growth") == ("f1", "f2")
    assert get_plan_features("enterprise") == ("f1", "f2", "f3")
    assert get_plan_features("unknown") == ()


def test_loader_reject_unknown_plan(tmp_path):
    plans_file = tmp_path / "plans.json"
    plans_file.write_text(json.dumps({"plans": {"custom": {"features": ["x"]}}}))
    with pytest.raises(ValueError, match="Unknown plan"):
        load_plans(plans_file)


def test_loader_missing_plans_key(tmp_path):
    plans_file = tmp_path / "plans.json"
    plans_file.write_text("{}")
    with pytest.raises(ValueError, match="plans"):
        load_plans(plans_file)


# ----- Models -----

def test_entitlement_set_has_feature():
    ent = EntitlementSet(tenant_id="t1", plan="growth", features=("custom_dashboards",))
    assert ent.has_feature("custom_dashboards") is True
    assert ent.has_feature("other") is False


def test_override_entry_is_expired():
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)
    o = OverrideEntry(
        feature_key="x", tenant_id="t1", expires_at=past, reason="r", actor_id="a",
        created_at=past, updated_at=past,
    )
    assert o.is_expired(now) is True
    o2 = OverrideEntry(
        feature_key="x", tenant_id="t1", expires_at=future, reason="r", actor_id="a",
        created_at=now, updated_at=now,
    )
    assert o2.is_expired(now) is False


def test_resolution_result_allowed():
    ent = EntitlementSet(tenant_id="t1", plan="free", features=("a",))
    r = ResolutionResult(allowed=True, entitlement_set=ent)
    assert r.allowed is True
    assert r.entitlement_set is ent
    assert r.deny_reason is None


def test_resolution_result_denied():
    r = ResolutionResult(
        allowed=False, entitlement_set=None,
        deny_reason="Eval failed", error_code="ENTITLEMENT_EVAL_FAILED",
    )
    assert r.allowed is False
    assert r.entitlement_set is None
    assert r.error_code == "ENTITLEMENT_EVAL_FAILED"


# ----- Overrides governance -----

def test_can_manage_overrides_super_admin():
    assert can_manage_overrides(["super_admin"]) is True
    assert can_manage_overrides(["Super_Admin"]) is True


def test_can_manage_overrides_support():
    assert can_manage_overrides(["support"]) is True


def test_can_manage_overrides_denied():
    assert can_manage_overrides(["viewer"]) is False
    assert can_manage_overrides([]) is False


# ----- Cache -----

def test_cache_key():
    assert _key("tenant_123") == "entitlements:tenant_123"


@patch("src.entitlements.cache.get_redis_client")
def test_get_cached_miss(mock_redis):
    mock_redis.return_value = MagicMock()
    mock_redis.return_value.get.return_value = None
    assert get_cached("t1") is None


@patch("src.entitlements.cache.get_redis_client")
def test_set_cached_and_get(mock_redis):
    client = MagicMock()
    mock_redis.return_value = client
    ent = EntitlementSet(tenant_id="t1", plan="growth", features=("a", "b"), overrides_applied=())
    set_cached(ent)
    call_args = client.setex.call_args
    assert call_args[0][0] == "entitlements:t1"
    raw = call_args[0][2]
    data = json.loads(raw)
    assert data["tenant_id"] == "t1"
    assert data["plan"] == "growth"
    assert "a" in data["features"] and "b" in data["features"]


@patch("src.entitlements.cache.get_redis_client")
def test_delete_cached(mock_redis):
    client = MagicMock()
    mock_redis.return_value = client
    delete_cached("t1")
    client.delete.assert_called_once_with("entitlements:t1")


# ----- Service: upgrade / downgrade / override / fail closed -----

@patch("src.entitlements.service._get_plan_for_tenant")
@patch("src.entitlements.service.list_active_overrides")
@patch("src.entitlements.cache.get_cached")
@patch("src.entitlements.cache.set_cached")
def test_get_entitlements_cache_hit(mock_set, mock_get_cached, mock_overrides, mock_plan):
    ent = EntitlementSet(tenant_id="t1", plan="growth", features=("custom_dashboards",), overrides_applied=())
    mock_get_cached.return_value = ent
    result = get_entitlements("t1")
    assert result.allowed is True
    assert result.entitlement_set is ent
    mock_plan.assert_not_called()
    mock_overrides.assert_not_called()


@patch("src.entitlements.service.get_plan_features", return_value=("analytics_view", "custom_dashboards"))
@patch("src.entitlements.service._get_plan_for_tenant", return_value="growth")
@patch("src.entitlements.service.list_active_overrides", return_value=[])
@patch("src.entitlements.cache.get_cached", return_value=None)
@patch("src.entitlements.cache.set_cached")
def test_get_entitlements_upgrade_plan(mock_set, mock_get_cached, mock_overrides, mock_plan, mock_features):
    result = get_entitlements("t1")
    assert result.allowed is True
    assert result.entitlement_set is not None
    assert result.entitlement_set.plan == "growth"
    mock_set.assert_called_once()


@patch("src.entitlements.service.get_plan_features", return_value=("analytics_view",))
@patch("src.entitlements.service._get_plan_for_tenant", return_value="free")
@patch("src.entitlements.service.list_active_overrides", return_value=[])
@patch("src.entitlements.cache.get_cached", return_value=None)
@patch("src.entitlements.cache.set_cached")
def test_get_entitlements_downgrade_plan(mock_set, mock_get_cached, mock_overrides, mock_plan, mock_features):
    result = get_entitlements("t1")
    assert result.allowed is True
    assert result.entitlement_set.plan == "free"
    assert "custom_dashboards" not in (result.entitlement_set.features or ())


@patch("src.entitlements.service.get_plan_features", return_value=("analytics_view",))
@patch("src.entitlements.service._get_plan_for_tenant", return_value="free")
@patch("src.entitlements.service.list_active_overrides")
@patch("src.entitlements.cache.get_cached", return_value=None)
@patch("src.entitlements.cache.set_cached")
def test_override_apply(mock_set, mock_get_cached, mock_overrides, mock_plan, mock_features):
    now = datetime.now(timezone.utc)
    override = OverrideEntry(
        feature_key="custom_dashboards", tenant_id="t1", expires_at=now + timedelta(days=1),
        reason="trial", actor_id="admin", created_at=now, updated_at=now,
    )
    mock_overrides.return_value = [override]
    result = get_entitlements("t1")
    assert result.allowed is True
    assert result.entitlement_set is not None
    assert "custom_dashboards" in result.entitlement_set.features
    assert "custom_dashboards" in result.entitlement_set.overrides_applied


@patch("src.entitlements.service.get_plan_features", return_value=("analytics_view", "custom_dashboards"))
@patch("src.entitlements.service._get_plan_for_tenant", return_value="growth")
@patch("src.entitlements.service.list_active_overrides", return_value=[])
@patch("src.entitlements.cache.get_cached", return_value=None)
@patch("src.entitlements.cache.set_cached")
def test_override_remove_no_overrides(mock_set, mock_get_cached, mock_overrides, mock_plan, mock_features):
    result = get_entitlements("t1")
    assert result.allowed is True
    assert result.entitlement_set.overrides_applied == ()


@patch("src.entitlements.service.get_entitlements")
def test_has_feature_true(mock_get):
    mock_get.return_value = ResolutionResult(
        allowed=True,
        entitlement_set=EntitlementSet(tenant_id="t1", plan="growth", features=("x",), overrides_applied=()),
    )
    assert has_feature("t1", "x") is True


@patch("src.entitlements.service.get_entitlements")
def test_has_feature_fail_closed(mock_get):
    mock_get.return_value = ResolutionResult(allowed=False, entitlement_set=None, error_code="EVAL_FAILED")
    assert has_feature("t1", "x") is False


@patch("src.entitlements.service.list_active_overrides")
@patch("src.entitlements.service._get_plan_for_tenant")
@patch("src.entitlements.cache.get_cached", return_value=None)
@patch("src.entitlements.cache.set_cached")
def test_evaluation_failure_fail_closed(mock_set, mock_get_cached, mock_plan, mock_overrides):
    mock_plan.side_effect = RuntimeError("Billing unavailable")
    with patch("src.entitlements.service.emit_evaluation_failure") as mock_alert:
        result = get_entitlements("t1")
    assert result.allowed is False
    assert result.error_code == "ENTITLEMENT_EVAL_FAILED"
    mock_alert.assert_called_once()


def test_invalidate_entitlements():
    with patch("src.entitlements.cache.delete_cached") as mock_del:
        invalidate_entitlements("t1")
    mock_del.assert_called_once_with("t1")


# ----- Monitoring -----

def test_emit_evaluation_failure_logs():
    with patch("src.monitoring.entitlement_alerts.logger") as mock_log:
        emit_evaluation_failure("t1", "error msg")
    mock_log.error.assert_called_once()


def test_record_deny_and_alert_under_threshold():
    with patch("src.monitoring.entitlement_alerts.emit_deny_alert") as mock_emit:
        for _ in range(DENY_THRESHOLD_PER_MIN - 1):
            record_deny_and_alert("t1", "feature_x")
    mock_emit.assert_not_called()


# ----- Reconciliation job -----

@patch("src.entitlements.overrides.remove_expired_overrides_and_return_tenants")
@patch("src.entitlements.service.invalidate_entitlements")
def test_reconcile_job_invalidates_affected_tenants(mock_inv, mock_remove):
    mock_remove.return_value = (["t1", "t2"], 2)
    from src.jobs.entitlement_reconcile_job import run_entitlement_reconcile_with_invalidation
    out = run_entitlement_reconcile_with_invalidation()
    assert out["expired_overrides_removed"] == 2
    assert out["tenants_invalidated"] == 2
    assert mock_inv.call_count == 2
    mock_inv.assert_any_call("t1")
    mock_inv.assert_any_call("t2")
