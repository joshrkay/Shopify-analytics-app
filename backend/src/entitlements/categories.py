"""
Premium category definitions for entitlement enforcement.

Categories are used to group endpoints by access level requirements.
Premium categories require specific billing states for access.
"""

from enum import Enum
from typing import Set, Optional


class PremiumCategory(str, Enum):
    """
    Premium categories for category-based entitlement enforcement.
    
    These categories map to billing state restrictions:
    - exports: Data export endpoints (CSV, Excel, API exports)
    - ai: AI-powered features (insights, recommendations, actions)
    - heavy_recompute: Resource-intensive operations (attribution, backfills)
    """
    EXPORTS = "exports"
    AI = "ai"
    HEAVY_RECOMPUTE = "heavy_recompute"
    OTHER = "other"  # Non-premium endpoints (always allowed if billing_state allows)


# Category to HTTP method restrictions for READ-ONLY enforcement
READ_ONLY_METHODS: Set[str] = {"GET", "HEAD", "OPTIONS"}
WRITE_METHODS: Set[str] = {"POST", "PUT", "PATCH", "DELETE"}


def is_write_method(method: str) -> bool:
    """
    Check if HTTP method is a write operation.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        
    Returns:
        True if method is a write operation
    """
    return method.upper() in WRITE_METHODS


def is_read_method(method: str) -> bool:
    """
    Check if HTTP method is a read operation.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        
    Returns:
        True if method is a read operation
    """
    return method.upper() in READ_ONLY_METHODS


def get_category_from_route(path: str, method: str) -> PremiumCategory:
    """
    Infer category from route path and method.
    
    This is a fallback - routes should explicitly declare their category.
    
    Args:
        path: Request path
        method: HTTP method
        
    Returns:
        Inferred PremiumCategory
    """
    path_lower = path.lower()
    
    # Export endpoints
    if "/export" in path_lower or "/download" in path_lower:
        return PremiumCategory.EXPORTS
    
    # AI endpoints
    if "/ai" in path_lower or "/insight" in path_lower or "/recommendation" in path_lower:
        return PremiumCategory.AI
    
    # Heavy compute endpoints
    if "/backfill" in path_lower or "/attribution" in path_lower or "/recompute" in path_lower:
        return PremiumCategory.HEAVY_RECOMPUTE
    
    return PremiumCategory.OTHER
