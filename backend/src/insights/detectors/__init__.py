"""
Insight detectors module.

Contains:
- Base detector interface
- Detector registry
- Concrete detector implementations

Each detector analyzes aggregated metrics and produces InsightCandidate
objects when meaningful changes are detected.
"""

from src.insights.detectors.base import InsightDetector
from src.insights.detectors.registry import DetectorRegistry

__all__ = [
    "InsightDetector",
    "DetectorRegistry",
]
