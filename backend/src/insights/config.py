"""
Configuration for AI insight generation.

Provides:
- InsightThresholds: Configurable thresholds for insight detection
- InsightConfig: Full configuration for the insight generation pipeline
- load_insight_config: Load configuration from file or defaults

Thresholds can be configured via:
1. config/insights.json file
2. Environment variables (future)
3. Default values in this module
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.insights.models import InsightType


@dataclass
class InsightThresholds:
    """
    Configurable thresholds for insight detection.

    All percentage thresholds are in percentage points (e.g., 15.0 = 15%).
    """

    # Spend anomaly thresholds
    spend_threshold_percent: float = 15.0  # Trigger on ±15% WoW change
    spend_std_dev_multiplier: float = 2.0  # Trigger if outside 2 std devs

    # ROAS change thresholds
    roas_threshold_percent: float = 10.0  # Trigger on ±10% WoW change
    roas_profitability_threshold: float = 1.5  # Alert if ROAS drops below this

    # Revenue/spend divergence thresholds
    divergence_threshold_percent: float = 20.0  # Trigger on 20%+ divergence

    # Channel mix shift thresholds
    channel_shift_threshold_pp: float = 10.0  # Trigger on 10+ percentage point shift

    # AOV change thresholds
    aov_threshold_percent: float = 10.0  # Trigger on ±10% WoW change

    # Conversion rate thresholds
    conversion_threshold_percent: float = 15.0  # Trigger on ±15% WoW change

    # CPA anomaly thresholds
    cpa_threshold_percent: float = 20.0  # Trigger on ±20% WoW change

    def get_threshold_for_type(self, insight_type: InsightType) -> float:
        """Get the primary threshold for a specific insight type."""
        thresholds = {
            InsightType.SPEND_ANOMALY: self.spend_threshold_percent,
            InsightType.ROAS_CHANGE: self.roas_threshold_percent,
            InsightType.REVENUE_SPEND_DIVERGENCE: self.divergence_threshold_percent,
            InsightType.CHANNEL_MIX_SHIFT: self.channel_shift_threshold_pp,
            InsightType.AOV_CHANGE: self.aov_threshold_percent,
            InsightType.CONVERSION_RATE_CHANGE: self.conversion_threshold_percent,
            InsightType.CPA_ANOMALY: self.cpa_threshold_percent,
        }
        return thresholds.get(insight_type, 15.0)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "spend_threshold_percent": self.spend_threshold_percent,
            "spend_std_dev_multiplier": self.spend_std_dev_multiplier,
            "roas_threshold_percent": self.roas_threshold_percent,
            "roas_profitability_threshold": self.roas_profitability_threshold,
            "divergence_threshold_percent": self.divergence_threshold_percent,
            "channel_shift_threshold_pp": self.channel_shift_threshold_pp,
            "aov_threshold_percent": self.aov_threshold_percent,
            "conversion_threshold_percent": self.conversion_threshold_percent,
            "cpa_threshold_percent": self.cpa_threshold_percent,
        }


@dataclass
class InsightConfig:
    """
    Full configuration for insight generation.

    Controls:
    - Detection thresholds
    - Confidence requirements
    - Output limits
    - Historical lookback
    - Feature flags
    """

    # Thresholds for detection
    thresholds: InsightThresholds = field(default_factory=InsightThresholds)

    # Confidence filtering
    min_confidence_threshold: float = 0.5  # Minimum confidence to emit insight

    # Output limits
    max_insights_per_run: int = 10  # Cap insights per tenant per run

    # Historical context
    lookback_days: int = 28  # Days of historical data for variance calculation
    min_days_with_data: int = 5  # Minimum data requirement for analysis

    # Model version (for tracking/auditing)
    model_version: str = "v1.0"

    # Enabled insight types (feature flags)
    enabled_insight_types: list[str] = field(default_factory=lambda: [
        InsightType.SPEND_ANOMALY.value,
        InsightType.ROAS_CHANGE.value,
        InsightType.REVENUE_SPEND_DIVERGENCE.value,
        InsightType.CHANNEL_MIX_SHIFT.value,
    ])

    def is_insight_type_enabled(self, insight_type: InsightType) -> bool:
        """Check if an insight type is enabled."""
        return insight_type.value in self.enabled_insight_types

    def get_enabled_types(self) -> list[InsightType]:
        """Get list of enabled InsightType enums."""
        return [
            InsightType(t) for t in self.enabled_insight_types
            if t in [it.value for it in InsightType]
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "thresholds": self.thresholds.to_dict(),
            "min_confidence_threshold": self.min_confidence_threshold,
            "max_insights_per_run": self.max_insights_per_run,
            "lookback_days": self.lookback_days,
            "min_days_with_data": self.min_days_with_data,
            "model_version": self.model_version,
            "enabled_insight_types": self.enabled_insight_types,
        }


def load_insight_config(config_path: Optional[Path] = None) -> InsightConfig:
    """
    Load insight configuration from file or environment.

    Priority:
    1. Explicit config file path argument
    2. INSIGHT_CONFIG_PATH environment variable
    3. config/insights.json relative to project root
    4. Default values

    Args:
        config_path: Optional explicit path to configuration file

    Returns:
        InsightConfig instance
    """
    # Try explicit path first
    if config_path and config_path.exists():
        return _load_from_file(config_path)

    # Try environment variable
    env_path = os.environ.get("INSIGHT_CONFIG_PATH")
    if env_path:
        env_config_path = Path(env_path)
        if env_config_path.exists():
            return _load_from_file(env_config_path)

    # Try default location (relative to this file's location)
    # Go up from backend/src/insights to project root, then to config/
    default_paths = [
        Path(__file__).parent.parent.parent.parent / "config" / "insights.json",
        Path("config/insights.json"),
        Path("/app/config/insights.json"),  # Docker path
    ]

    for default_path in default_paths:
        if default_path.exists():
            return _load_from_file(default_path)

    # Return defaults if no config file found
    return InsightConfig()


def _load_from_file(path: Path) -> InsightConfig:
    """
    Load configuration from a JSON file.

    Args:
        path: Path to the JSON configuration file

    Returns:
        InsightConfig instance

    Raises:
        json.JSONDecodeError: If file is not valid JSON
        KeyError: If required fields are missing
    """
    with open(path, "r") as f:
        data = json.load(f)

    # Parse thresholds
    thresholds_data = data.get("thresholds", {})
    thresholds = InsightThresholds(
        spend_threshold_percent=thresholds_data.get("spend_threshold_percent", 15.0),
        spend_std_dev_multiplier=thresholds_data.get("spend_std_dev_multiplier", 2.0),
        roas_threshold_percent=thresholds_data.get("roas_threshold_percent", 10.0),
        roas_profitability_threshold=thresholds_data.get("roas_profitability_threshold", 1.5),
        divergence_threshold_percent=thresholds_data.get("divergence_threshold_percent", 20.0),
        channel_shift_threshold_pp=thresholds_data.get("channel_shift_threshold_pp", 10.0),
        aov_threshold_percent=thresholds_data.get("aov_threshold_percent", 10.0),
        conversion_threshold_percent=thresholds_data.get("conversion_threshold_percent", 15.0),
        cpa_threshold_percent=thresholds_data.get("cpa_threshold_percent", 20.0),
    )

    return InsightConfig(
        thresholds=thresholds,
        min_confidence_threshold=data.get("min_confidence_threshold", 0.5),
        max_insights_per_run=data.get("max_insights_per_run", 10),
        lookback_days=data.get("lookback_days", 28),
        min_days_with_data=data.get("min_days_with_data", 5),
        model_version=data.get("model_version", "v1.0"),
        enabled_insight_types=data.get("enabled_insight_types", [
            InsightType.SPEND_ANOMALY.value,
            InsightType.ROAS_CHANGE.value,
            InsightType.REVENUE_SPEND_DIVERGENCE.value,
            InsightType.CHANNEL_MIX_SHIFT.value,
        ]),
    )


# Singleton config instance (loaded once)
_config_instance: Optional[InsightConfig] = None


def get_insight_config() -> InsightConfig:
    """
    Get the singleton insight configuration.

    Loads configuration once and caches it.

    Returns:
        InsightConfig instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = load_insight_config()
    return _config_instance


def reload_insight_config(config_path: Optional[Path] = None) -> InsightConfig:
    """
    Reload the insight configuration.

    Useful for testing or when configuration changes.

    Args:
        config_path: Optional explicit path to configuration file

    Returns:
        New InsightConfig instance
    """
    global _config_instance
    _config_instance = load_insight_config(config_path)
    return _config_instance
