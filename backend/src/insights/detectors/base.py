"""
Base class for insight detectors.

All insight detectors must inherit from InsightDetector and implement
the detect() method. Detectors analyze TenantMetrics and produce
InsightCandidate objects when meaningful patterns are detected.

DESIGN PRINCIPLES:
- Deterministic: Same inputs always produce same outputs
- Stateless: No state preserved between detect() calls
- Pure: No side effects, no external API calls
- Configurable: Thresholds from InsightConfig
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.insights.config import InsightConfig
from src.insights.models import (
    InsightCandidate,
    InsightType,
    InsightCategory,
    InsightSeverity,
    MetricDelta,
    TenantMetrics,
)


@dataclass
class DeltaResult:
    """Result of calculating a delta between two values."""
    absolute: Decimal
    percent: Optional[float]
    direction: str  # "up", "down", or "unchanged"

    @property
    def is_increase(self) -> bool:
        return self.direction == "up"

    @property
    def is_decrease(self) -> bool:
        return self.direction == "down"


class InsightDetector(ABC):
    """
    Abstract base class for insight detectors.

    Each detector is responsible for:
    1. Analyzing specific metrics from TenantMetrics
    2. Detecting statistically meaningful changes
    3. Producing InsightCandidate objects with supporting metrics

    Subclasses must implement:
    - insight_type: The type of insight this detector produces
    - detect(): The main detection logic
    """

    def __init__(self, config: InsightConfig):
        """
        Initialize detector with configuration.

        Args:
            config: InsightConfig containing thresholds and settings
        """
        self.config = config
        self.thresholds = config.thresholds

    @property
    @abstractmethod
    def insight_type(self) -> InsightType:
        """The type of insight this detector produces."""
        pass

    @abstractmethod
    def detect(self, metrics: TenantMetrics) -> list[InsightCandidate]:
        """
        Analyze metrics and detect insights.

        This method must be:
        - Deterministic: Same metrics always produce same insights
        - Side-effect free: No external calls, no state changes
        - Exception-safe: Handle edge cases gracefully

        Args:
            metrics: Aggregated tenant metrics from dbt marts

        Returns:
            List of InsightCandidate objects (may be empty)
        """
        pass

    def _calculate_delta(
        self,
        current: Decimal,
        previous: Decimal
    ) -> DeltaResult:
        """
        Calculate the change between two values.

        Args:
            current: Current period value
            previous: Previous period value (comparison)

        Returns:
            DeltaResult with absolute change, percent change, and direction
        """
        absolute = current - previous

        if previous == 0:
            # Can't calculate percentage if previous is zero
            if current == 0:
                return DeltaResult(
                    absolute=Decimal("0"),
                    percent=None,
                    direction="unchanged"
                )
            else:
                # Infinite increase from zero - use None for percent
                return DeltaResult(
                    absolute=absolute,
                    percent=None,
                    direction="up" if current > 0 else "down"
                )

        percent = float((absolute / previous) * 100)

        if absolute > 0:
            direction = "up"
        elif absolute < 0:
            direction = "down"
        else:
            direction = "unchanged"

        return DeltaResult(
            absolute=absolute,
            percent=round(percent, 2),
            direction=direction
        )

    def _calculate_confidence(
        self,
        delta_percent: Optional[float],
        sample_size: int,
        historical_std_dev: Decimal,
        data_completeness: float = 1.0
    ) -> float:
        """
        Calculate statistical confidence for an insight.

        Confidence is higher when:
        - Sample size is larger
        - Historical volatility is lower
        - Change exceeds historical variance
        - Data is more complete

        Args:
            delta_percent: Percentage change (None if unavailable)
            sample_size: Number of days with data
            historical_std_dev: Standard deviation of historical values
            data_completeness: Fraction of expected data present (0-1)

        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence from sample size (7 days = 0.7 base)
        # Max 0.4 from sample size alone
        sample_confidence = min(sample_size / 10, 1.0) * 0.4

        # Volatility-adjusted confidence
        # Higher confidence if change exceeds historical volatility
        volatility_confidence = 0.3  # Default if no variance data
        if historical_std_dev > 0 and delta_percent is not None:
            z_score = abs(delta_percent) / float(historical_std_dev)
            volatility_confidence = min(z_score / 3, 1.0) * 0.4

        # Data completeness factor (max 0.2)
        completeness_confidence = data_completeness * 0.2

        total_confidence = (
            sample_confidence +
            volatility_confidence +
            completeness_confidence
        )

        return round(min(max(total_confidence, 0.0), 1.0), 2)

    def _determine_severity(
        self,
        delta_percent: Optional[float],
        additional_context: Optional[dict] = None
    ) -> str:
        """
        Determine severity level based on magnitude of change.

        Default implementation:
        - Critical: > 50% change
        - Warning: > 25% change
        - Info: Otherwise

        Subclasses may override for type-specific logic.

        Args:
            delta_percent: Percentage change (None treated as info)
            additional_context: Optional context for advanced severity logic

        Returns:
            Severity level string
        """
        if delta_percent is None:
            return InsightSeverity.INFO.value

        abs_delta = abs(delta_percent)

        if abs_delta >= 50:
            return InsightSeverity.CRITICAL.value
        elif abs_delta >= 25:
            return InsightSeverity.WARNING.value
        else:
            return InsightSeverity.INFO.value

    def _create_metric_delta(
        self,
        metric_name: str,
        current: Decimal,
        previous: Decimal,
        timeframe: str = "WoW",
        unit: str = "USD"
    ) -> MetricDelta:
        """
        Create a MetricDelta from current and previous values.

        Args:
            metric_name: Name of the metric
            current: Current period value
            previous: Previous period value
            timeframe: Time comparison frame ("WoW", "MoM", "DoD")
            unit: Unit of measurement

        Returns:
            MetricDelta instance
        """
        delta = self._calculate_delta(current, previous)

        return MetricDelta(
            metric_name=metric_name,
            current_value=current,
            previous_value=previous,
            delta_absolute=delta.absolute,
            delta_percent=delta.percent,
            timeframe=timeframe,
            unit=unit,
        )

    def _safe_divide(
        self,
        numerator: Decimal,
        denominator: Decimal,
        default: Decimal = Decimal("0")
    ) -> Decimal:
        """
        Safely divide two decimals, returning default if denominator is zero.

        Args:
            numerator: The dividend
            denominator: The divisor
            default: Value to return if denominator is zero

        Returns:
            Result of division or default
        """
        if denominator == 0:
            return default
        return numerator / denominator

    def _meets_threshold(
        self,
        delta_percent: Optional[float],
        threshold: float
    ) -> bool:
        """
        Check if a delta meets or exceeds a threshold.

        Args:
            delta_percent: Percentage change to check
            threshold: Threshold percentage (absolute comparison)

        Returns:
            True if delta meets threshold, False otherwise
        """
        if delta_percent is None:
            return False
        return abs(delta_percent) >= threshold
