"""
Template-based natural language summary generation.

Provides deterministic, human-readable insight summaries.
No LLM dependency - ensures same inputs produce same outputs.

Story 8.1 - AI Insight Generation (Read-Only Analytics)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.insight_generation_service import DetectedInsight

from src.models.ai_insight import InsightType, InsightSeverity


# Currency symbols for formatting
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "CAD": "C$",
    "AUD": "A$",
    "JPY": "\u00a5",
    "CNY": "\u00a5",
    "INR": "\u20b9",
    "BRL": "R$",
    "MXN": "MX$",
}


# Templates organized by: InsightType -> direction -> severity
INSIGHT_TEMPLATES = {
    InsightType.SPEND_ANOMALY: {
        "increase": {
            InsightSeverity.CRITICAL: (
                "Marketing spend increased significantly by {delta_pct:.1f}% {timeframe}, "
                "reaching {currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "This is a critical change that warrants immediate review."
            ),
            InsightSeverity.WARNING: (
                "Marketing spend increased by {delta_pct:.1f}% {timeframe} "
                "to {currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "Review campaign budgets to ensure alignment with targets."
            ),
            InsightSeverity.INFO: (
                "Marketing spend increased by {delta_pct:.1f}% {timeframe}{platform_suffix}."
            ),
        },
        "decrease": {
            InsightSeverity.CRITICAL: (
                "Marketing spend dropped significantly by {delta_pct:.1f}% {timeframe}, "
                "now at {currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "This may impact campaign reach and performance."
            ),
            InsightSeverity.WARNING: (
                "Marketing spend decreased by {delta_pct:.1f}% {timeframe} "
                "to {currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "Check if this aligns with planned budget adjustments."
            ),
            InsightSeverity.INFO: (
                "Marketing spend decreased by {delta_pct:.1f}% {timeframe}{platform_suffix}."
            ),
        },
    },
    InsightType.ROAS_CHANGE: {
        "increase": {
            InsightSeverity.CRITICAL: (
                "ROAS improved dramatically by {delta_pct:.1f}% {timeframe}, "
                "now at {current_value:.2f}x{platform_suffix}. "
                "Identify what's working and consider scaling successful campaigns."
            ),
            InsightSeverity.WARNING: (
                "ROAS improved by {delta_pct:.1f}% {timeframe} "
                "to {current_value:.2f}x{platform_suffix}. "
                "Good performance - monitor for sustainability."
            ),
            InsightSeverity.INFO: (
                "ROAS improved by {delta_pct:.1f}% {timeframe}{platform_suffix}."
            ),
        },
        "decrease": {
            InsightSeverity.CRITICAL: (
                "ROAS declined significantly by {delta_pct:.1f}% {timeframe}, "
                "now at {current_value:.2f}x{platform_suffix}. "
                "Urgent review of ad efficiency recommended."
            ),
            InsightSeverity.WARNING: (
                "ROAS declined by {delta_pct:.1f}% {timeframe} "
                "to {current_value:.2f}x{platform_suffix}. "
                "Review campaign targeting and creative performance."
            ),
            InsightSeverity.INFO: (
                "ROAS declined by {delta_pct:.1f}% {timeframe}{platform_suffix}."
            ),
        },
    },
    InsightType.REVENUE_VS_SPEND_DIVERGENCE: {
        "default": {
            InsightSeverity.WARNING: (
                "Revenue and spend are moving in opposite directions: "
                "revenue {revenue_direction} by {revenue_delta_pct:.1f}% while "
                "spend {spend_direction} by {spend_delta_pct:.1f}% {timeframe}. "
                "Review marketing efficiency."
            ),
            InsightSeverity.CRITICAL: (
                "Significant divergence detected: revenue {revenue_direction} by "
                "{revenue_delta_pct:.1f}% while spend {spend_direction} by "
                "{spend_delta_pct:.1f}% {timeframe}. Immediate review recommended."
            ),
        },
    },
    InsightType.CHANNEL_MIX_SHIFT: {
        "default": {
            InsightSeverity.WARNING: (
                "Significant shift in channel mix: {platform} share changed by "
                "{delta_pct:.1f}% {timeframe}. Evaluate if this aligns with strategy."
            ),
            InsightSeverity.INFO: (
                "Channel mix shifted with {platform} changing by "
                "{delta_pct:.1f}% {timeframe}."
            ),
        },
    },
    InsightType.CAC_ANOMALY: {
        "increase": {
            InsightSeverity.CRITICAL: (
                "Customer acquisition cost increased significantly by {delta_pct:.1f}% "
                "{timeframe}, now at {currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "Review targeting and funnel efficiency."
            ),
            InsightSeverity.WARNING: (
                "CAC increased by {delta_pct:.1f}% {timeframe} to "
                "{currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "Monitor acquisition efficiency."
            ),
            InsightSeverity.INFO: (
                "CAC increased by {delta_pct:.1f}% {timeframe}{platform_suffix}."
            ),
        },
        "decrease": {
            InsightSeverity.INFO: (
                "CAC improved by {delta_pct:.1f}% {timeframe} to "
                "{currency_symbol}{current_value:,.0f}{platform_suffix}. "
                "Acquisition efficiency is improving."
            ),
            InsightSeverity.WARNING: (
                "CAC improved by {delta_pct:.1f}% {timeframe}{platform_suffix}. "
                "Good trend - acquisition is becoming more efficient."
            ),
        },
    },
    InsightType.AOV_CHANGE: {
        "increase": {
            InsightSeverity.INFO: (
                "Average order value increased by {delta_pct:.1f}% {timeframe} "
                "to {currency_symbol}{current_value:,.2f}. Customers are spending more per order."
            ),
            InsightSeverity.WARNING: (
                "AOV increased significantly by {delta_pct:.1f}% {timeframe} to "
                "{currency_symbol}{current_value:,.2f}. Verify this aligns with pricing strategy."
            ),
        },
        "decrease": {
            InsightSeverity.WARNING: (
                "Average order value decreased by {delta_pct:.1f}% {timeframe} "
                "to {currency_symbol}{current_value:,.2f}. Review product mix and pricing."
            ),
            InsightSeverity.CRITICAL: (
                "AOV dropped significantly by {delta_pct:.1f}% {timeframe} to "
                "{currency_symbol}{current_value:,.2f}. Urgent review of pricing and promotions."
            ),
        },
    },
}


def _format_timeframe(comparison_type: str) -> str:
    """Format comparison type as readable timeframe."""
    mappings = {
        "week_over_week": "week-over-week",
        "month_over_month": "month-over-month",
        "day_over_day": "day-over-day",
        "quarter_over_quarter": "quarter-over-quarter",
        "year_over_year": "year-over-year",
    }
    return mappings.get(comparison_type, comparison_type.replace("_", " "))


def _get_direction(delta_pct: float) -> str:
    """Get direction word based on delta."""
    return "increased" if delta_pct > 0 else "decreased"


def render_insight_summary(detected: "DetectedInsight") -> str:
    """
    Render a natural language summary for a detected insight.

    Args:
        detected: DetectedInsight object with metrics and context

    Returns:
        Human-readable summary string (deterministic)
    """
    templates = INSIGHT_TEMPLATES.get(detected.insight_type, {})

    # Get primary metric
    if not detected.metrics:
        return f"Insight detected: {detected.insight_type.value.replace('_', ' ')}"

    primary_metric = detected.metrics[0]

    # Determine direction
    direction = "increase" if primary_metric.delta_pct > 0 else "decrease"

    # Get severity-specific template
    direction_templates = templates.get(direction, templates.get("default", {}))
    template = direction_templates.get(detected.severity)

    # Fallback to INFO if specific severity not found
    if not template:
        template = direction_templates.get(InsightSeverity.INFO)

    # Final fallback
    if not template:
        return (
            f"{detected.insight_type.value.replace('_', ' ').title()} detected "
            f"with {abs(primary_metric.delta_pct):.1f}% change."
        )

    # Build context for template
    currency_symbol = CURRENCY_SYMBOLS.get(detected.currency or "USD", "$")
    platform_suffix = ""
    if detected.platform:
        platform_suffix = f" on {detected.platform.replace('_', ' ').title()}"

    context = {
        "delta_pct": abs(primary_metric.delta_pct),
        "current_value": float(primary_metric.current_value),
        "prior_value": float(primary_metric.prior_value),
        "timeframe": _format_timeframe(primary_metric.timeframe),
        "currency_symbol": currency_symbol,
        "platform_suffix": platform_suffix,
        "platform": (detected.platform or "").replace("_", " ").title(),
        "insight_type": detected.insight_type.value,
    }

    # Add secondary metrics for divergence insights
    if (
        detected.insight_type == InsightType.REVENUE_VS_SPEND_DIVERGENCE
        and len(detected.metrics) >= 2
    ):
        revenue_metric = detected.metrics[0]
        spend_metric = detected.metrics[1]
        context["revenue_delta_pct"] = abs(revenue_metric.delta_pct)
        context["spend_delta_pct"] = abs(spend_metric.delta_pct)
        context["revenue_direction"] = _get_direction(revenue_metric.delta_pct)
        context["spend_direction"] = _get_direction(spend_metric.delta_pct)

    try:
        return template.format(**context)
    except KeyError:
        # Fallback if template has missing keys
        return (
            f"{detected.insight_type.value.replace('_', ' ').title()} detected "
            f"with {abs(primary_metric.delta_pct):.1f}% change."
        )
