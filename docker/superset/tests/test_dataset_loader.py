"""
Tests for dataset_loader.py — YAML-defined dataset registration.

Validates:
- YAML parsing produces correct DatasetConfig
- PII column validation catches customer_id, customer_email
- All 3 YAML files parse without error
- RLS required on every dataset
- No ad-hoc metric expressions allowed
- Column allow-list enforcement
- Version metadata present

Story 5.1.4 - Register Canonical Datasets
"""

import sys
import os
from pathlib import Path

import pytest

# Add parent directory to path for Superset module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataset_loader import (
    DatasetLoader,
    DatasetConfig,
    DatasetColumnConfig,
    DatasetMetricConfig,
    PII_COLUMNS,
    INTERNAL_COLUMNS,
)


# Path to the dataset YAML files
DATASETS_DIR = Path(__file__).parent.parent / "datasets"


# =============================================================================
# YAML PARSING TESTS
# =============================================================================


class TestYAMLParsing:
    """Test that YAML files are parsed correctly."""

    def test_load_fact_orders(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        assert config.table_name == "fact_orders"
        assert config.schema == "analytics"
        assert config.dbt_model == "fact_orders_v1"

    def test_load_fact_marketing_spend(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_marketing_spend.yaml")
        assert config.table_name == "fact_marketing_spend"
        assert config.dbt_model == "fact_marketing_spend_v1"

    def test_load_fact_campaign_performance(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_campaign_performance.yaml")
        assert config.table_name == "fact_campaign_performance"
        assert config.dbt_model == "fact_campaign_performance_v1"

    def test_load_all_datasets(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        configs = loader.load_all()
        assert len(configs) >= 3
        table_names = {c.table_name for c in configs}
        assert "fact_orders" in table_names
        assert "fact_marketing_spend" in table_names
        assert "fact_campaign_performance" in table_names

    def test_columns_are_frozen_tuples(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        assert isinstance(config.columns, tuple)
        assert all(isinstance(c, DatasetColumnConfig) for c in config.columns)

    def test_metrics_are_frozen_tuples(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        assert isinstance(config.metrics, tuple)
        assert all(isinstance(m, DatasetMetricConfig) for m in config.metrics)


# =============================================================================
# PII VALIDATION
# =============================================================================


class TestPIIValidation:
    """No PII columns must appear in dataset configs."""

    def test_pii_columns_set_not_empty(self):
        assert len(PII_COLUMNS) > 0

    def test_customer_id_is_pii(self):
        assert "customer_id" in PII_COLUMNS

    def test_customer_email_is_pii(self):
        assert "customer_email" in PII_COLUMNS

    def test_access_token_is_pii(self):
        assert "access_token" in PII_COLUMNS

    def test_fact_orders_no_pii(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        for col in config.columns:
            assert col.column_name not in PII_COLUMNS, (
                f"PII column '{col.column_name}' found in fact_orders"
            )

    def test_fact_marketing_spend_no_pii(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_marketing_spend.yaml")
        for col in config.columns:
            assert col.column_name not in PII_COLUMNS, (
                f"PII column '{col.column_name}' found in fact_marketing_spend"
            )

    def test_fact_campaign_performance_no_pii(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_campaign_performance.yaml")
        for col in config.columns:
            assert col.column_name not in PII_COLUMNS, (
                f"PII column '{col.column_name}' found in fact_campaign_performance"
            )

    def test_no_internal_columns_exposed(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            for col in config.columns:
                assert col.column_name not in INTERNAL_COLUMNS, (
                    f"Internal column '{col.column_name}' found in {name}"
                )


# =============================================================================
# RLS VALIDATION
# =============================================================================


class TestRLSValidation:
    """Every dataset must have RLS enabled."""

    def test_all_datasets_have_rls_enabled(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            assert config.rls_enabled, f"{name}: RLS not enabled"

    def test_all_datasets_have_rls_clause(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            assert config.rls_clause, f"{name}: RLS clause is empty"
            assert "tenant_id" in config.rls_clause, (
                f"{name}: RLS clause doesn't reference tenant_id"
            )

    def test_all_datasets_have_rls_column(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            assert config.has_rls_column, f"{name}: no RLS column (is_rls_column) defined"

    def test_tenant_id_is_rls_column(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        rls_cols = [c for c in config.columns if c.is_rls_column]
        assert len(rls_cols) == 1
        assert rls_cols[0].column_name == "tenant_id"


# =============================================================================
# METRIC VALIDATION
# =============================================================================


class TestMetricValidation:
    """Only predefined metrics allowed."""

    def test_fact_orders_has_metrics(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        assert len(config.metrics) >= 4

    def test_all_metrics_have_expressions(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            for metric in config.metrics:
                assert metric.expression, (
                    f"{name}: metric '{metric.metric_name}' has no expression"
                )

    def test_all_metrics_have_names(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            for metric in config.metrics:
                assert metric.metric_name, f"{name}: metric has no name"

    def test_campaign_performance_has_roas(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_campaign_performance.yaml")
        metric_names = [m.metric_name for m in config.metrics]
        assert "attributed_roas" in metric_names


# =============================================================================
# COLUMN ALLOW-LIST
# =============================================================================


class TestColumnAllowList:
    """Columns must match expected allow-lists."""

    def test_fact_orders_columns(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        expected = {
            "id", "tenant_id", "order_id", "order_date",
            "revenue_gross", "revenue_net", "currency", "is_refund",
        }
        assert config.column_names == expected

    def test_fact_marketing_spend_columns(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_marketing_spend.yaml")
        expected = {
            "id", "tenant_id", "spend_date", "channel", "campaign_id",
            "ad_set_id", "spend", "impressions", "clicks", "currency",
        }
        assert config.column_names == expected

    def test_fact_campaign_performance_columns(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_campaign_performance.yaml")
        col_names = config.column_names
        assert "tenant_id" in col_names
        assert "campaign_date" in col_names
        assert "attributed_revenue" in col_names
        assert "spend" in col_names


# =============================================================================
# DATE COLUMN
# =============================================================================


class TestDateColumn:
    """Every dataset must have a date column."""

    def test_fact_orders_date_column(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        assert config.date_column == "order_date"

    def test_fact_marketing_spend_date_column(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_marketing_spend.yaml")
        assert config.date_column == "spend_date"

    def test_fact_campaign_performance_date_column(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_campaign_performance.yaml")
        assert config.date_column == "campaign_date"


# =============================================================================
# VERSION METADATA
# =============================================================================


class TestVersionMetadata:
    """Version metadata must be present."""

    def test_all_datasets_have_version(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        for name, config in loader._configs.items():
            assert config.metric_version, f"{name}: missing metric_version"
            assert config.version_status, f"{name}: missing version_status"

    def test_all_datasets_have_status(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        valid_statuses = {"active", "governed_alias", "deprecated"}
        for name, config in loader._configs.items():
            assert config.version_status in valid_statuses, (
                f"{name}: unexpected status '{config.version_status}'"
            )


# =============================================================================
# VALIDATE_ALL
# =============================================================================


class TestValidateAll:
    """Test the comprehensive validation method."""

    def test_all_valid(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        is_valid, issues = loader.validate_all()
        assert is_valid, f"Validation failed with issues: {issues}"
        assert len(issues) == 0

    def test_empty_configs_fails(self):
        loader = DatasetLoader(datasets_dir="/nonexistent/path")
        loader.load_all()
        is_valid, issues = loader.validate_all()
        assert not is_valid
        assert any("No dataset configs" in i for i in issues)

    def test_get_config(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        config = loader.get_config("fact_orders")
        assert config is not None
        assert config.table_name == "fact_orders"

    def test_get_config_not_found(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        loader.load_all()
        config = loader.get_config("nonexistent_table")
        assert config is None


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================


class TestFrozenDataclasses:
    """Dataset config dataclasses must be immutable."""

    def test_dataset_config_frozen(self):
        loader = DatasetLoader(datasets_dir=str(DATASETS_DIR))
        config = loader.load_yaml(DATASETS_DIR / "fact_orders.yaml")
        with pytest.raises((AttributeError, TypeError)):
            config.table_name = "hacked"

    def test_column_config_frozen(self):
        col = DatasetColumnConfig(column_name="test", type="VARCHAR")
        with pytest.raises((AttributeError, TypeError)):
            col.column_name = "hacked"

    def test_metric_config_frozen(self):
        metric = DatasetMetricConfig(metric_name="test", expression="COUNT(*)")
        with pytest.raises((AttributeError, TypeError)):
            metric.metric_name = "hacked"
