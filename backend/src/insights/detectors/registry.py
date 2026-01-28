"""
Detector registry for managing insight detectors.

The registry provides:
- Registration of detector classes via decorator
- Retrieval of detector instances by type
- Listing all registered detectors
- Configuration-aware instantiation

Usage:
    @DetectorRegistry.register(InsightType.SPEND_ANOMALY)
    class SpendAnomalyDetector(InsightDetector):
        ...

    # Get all detectors
    detectors = DetectorRegistry.get_all_detectors(config)

    # Get specific detector
    detector = DetectorRegistry.get_detector(InsightType.SPEND_ANOMALY, config)
"""

import logging
from typing import Type, Optional

from src.insights.config import InsightConfig
from src.insights.models import InsightType

# Forward reference to avoid circular import
# InsightDetector is imported at runtime
InsightDetector = None

logger = logging.getLogger(__name__)


class DetectorRegistry:
    """
    Registry for insight detectors.

    Manages the mapping between InsightType and detector classes.
    Provides factory methods for instantiating detectors with configuration.
    """

    # Class-level storage for registered detectors
    _detectors: dict[InsightType, Type] = {}

    @classmethod
    def register(cls, insight_type: InsightType):
        """
        Decorator to register a detector class for an insight type.

        Usage:
            @DetectorRegistry.register(InsightType.SPEND_ANOMALY)
            class SpendAnomalyDetector(InsightDetector):
                ...

        Args:
            insight_type: The InsightType this detector handles

        Returns:
            Decorator function
        """
        def decorator(detector_cls: Type):
            if insight_type in cls._detectors:
                logger.warning(
                    f"Overwriting existing detector for {insight_type}: "
                    f"{cls._detectors[insight_type].__name__} -> {detector_cls.__name__}"
                )

            cls._detectors[insight_type] = detector_cls
            logger.debug(f"Registered detector {detector_cls.__name__} for {insight_type}")

            return detector_cls

        return decorator

    @classmethod
    def get_detector(
        cls,
        insight_type: InsightType,
        config: InsightConfig
    ):
        """
        Get an instantiated detector for a specific insight type.

        Args:
            insight_type: The type of insight to detect
            config: Configuration for the detector

        Returns:
            Instantiated detector

        Raises:
            ValueError: If no detector is registered for the type
        """
        detector_cls = cls._detectors.get(insight_type)

        if detector_cls is None:
            raise ValueError(
                f"No detector registered for insight type: {insight_type}. "
                f"Available types: {list(cls._detectors.keys())}"
            )

        return detector_cls(config)

    @classmethod
    def get_all_detectors(cls, config: InsightConfig) -> list:
        """
        Get instantiated detectors for all registered types.

        Only returns detectors for insight types that are enabled
        in the configuration.

        Args:
            config: Configuration for the detectors

        Returns:
            List of instantiated detectors
        """
        detectors = []

        for insight_type, detector_cls in cls._detectors.items():
            if config.is_insight_type_enabled(insight_type):
                try:
                    detector = detector_cls(config)
                    detectors.append(detector)
                except Exception as e:
                    logger.error(
                        f"Failed to instantiate detector for {insight_type}: {e}"
                    )

        return detectors

    @classmethod
    def get_registered_types(cls) -> list[InsightType]:
        """
        Get list of all registered insight types.

        Returns:
            List of InsightType values that have registered detectors
        """
        return list(cls._detectors.keys())

    @classmethod
    def is_registered(cls, insight_type: InsightType) -> bool:
        """
        Check if a detector is registered for an insight type.

        Args:
            insight_type: The insight type to check

        Returns:
            True if a detector is registered, False otherwise
        """
        return insight_type in cls._detectors

    @classmethod
    def clear(cls):
        """
        Clear all registered detectors.

        Primarily used for testing.
        """
        cls._detectors.clear()

    @classmethod
    def count(cls) -> int:
        """
        Get the number of registered detectors.

        Returns:
            Number of registered detectors
        """
        return len(cls._detectors)
