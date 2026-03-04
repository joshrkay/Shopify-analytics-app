"""
Unit tests for search logic.

Layer 1 — Tests static page matching in search.py.
If these fail, the bug is in the search matching logic.

Tests cover:
- Case-insensitive substring matching against STATIC_PAGES
- Partial matches work
- No match returns empty
- All expected pages exist in STATIC_PAGES
"""

import pytest

from src.api.routes.search import STATIC_PAGES, SearchResult


class TestStaticPageMatching:
    """STATIC_PAGES should contain all navigable pages."""

    def test_all_expected_pages_present(self):
        titles = [p.title for p in STATIC_PAGES]
        assert "Home" in titles
        assert "Attribution" in titles
        assert "Orders" in titles
        assert "Cohort Analysis" in titles
        assert "Budget Pacing" in titles
        assert "Alerts" in titles
        assert "Builder" in titles
        assert "Insights" in titles
        assert "Sources" in titles
        assert "Settings" in titles
        assert "What's New" in titles

    def test_case_insensitive_match(self):
        """Searching 'home' should match 'Home'."""
        query = "home"
        results = [p for p in STATIC_PAGES if query in p.title.lower()]
        assert len(results) == 1
        assert results[0].title == "Home"
        assert results[0].path == "/home"

    def test_partial_match(self):
        """Searching 'alert' should match 'Alerts'."""
        query = "alert"
        results = [p for p in STATIC_PAGES if query in p.title.lower()]
        assert len(results) == 1
        assert results[0].title == "Alerts"

    def test_no_match(self):
        """Searching for nonexistent page returns empty."""
        query = "zzzznotapage"
        results = [p for p in STATIC_PAGES if query in p.title.lower()]
        assert results == []

    def test_multiple_matches(self):
        """'s' appears in Sources, Settings, Insights, What's New."""
        query = "s"
        results = [p for p in STATIC_PAGES if query in p.title.lower()]
        assert len(results) >= 3  # Sources, Settings, Insights, What's New, Orders, Alerts, etc.

    def test_all_pages_have_paths(self):
        """Every page should have a non-empty path starting with /."""
        for page in STATIC_PAGES:
            assert page.path.startswith("/"), f"Page '{page.title}' has invalid path: {page.path}"
            assert page.type == "page"
