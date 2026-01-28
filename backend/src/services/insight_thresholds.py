"""
Configurable thresholds for insight detection.

Thresholds determine when metric changes are significant enough
to generate an insight. Can be customized per plan tier.

Story 8.1 - AI Insight Generation (Read-Only Analytics)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InsightThresholds:
    """
    Threshold configuration for insight detection.

    All thresholds are percentage values (e.g., 15.0 = 15%).
    """

    # Spend anomaly thresholds
    spend_anomaly_pct: float = 15.0
    spend_critical_pct: float = 30.0

    # ROAS change thresholds
    roas_change_pct: float = 15.0
    roas_critical_pct: float = 25.0

    # Revenue vs Spend divergence threshold
    divergence_pct: float = 10.0

    # Channel mix shift threshold
    channel_shift_pct: float = 20.0

    # CAC anomaly thresholds
    cac_anomaly_pct: float = 15.0
    cac_critical_pct: float = 30.0

    # AOV change threshold
    aov_change_pct: float = 10.0

    # Order volume anomaly
    order_volume_pct: float = 20.0

    # Minimum values to consider (avoid noise from small numbers)
    min_spend_for_analysis: float = 100.0
    min_revenue_for_analysis: float = 100.0
    min_orders_for_analysis: int = 10


# Default thresholds for standard plans
DEFAULT_THRESHOLDS = InsightThresholds()

# Enterprise thresholds (more sensitive detection)
ENTERPRISE_THRESHOLDS = InsightThresholds(
    spend_anomaly_pct=10.0,
    spend_critical_pct=20.0,
    roas_change_pct=10.0,
    roas_critical_pct=20.0,
    divergence_pct=8.0,
    cac_anomaly_pct=10.0,
    cac_critical_pct=20.0,
    aov_change_pct=8.0,
)


def get_thresholds_for_tier(tier: str) -> InsightThresholds:
    """
    Get thresholds based on plan tier.

    Args:
        tier: Plan tier name (free, growth, pro, enterprise)

    Returns:
        InsightThresholds appropriate for the tier
    """
    if tier == "enterprise":
        return ENTERPRISE_THRESHOLDS
    return DEFAULT_THRESHOLDS
