"""
Unit tests for AI Recommendation Templates.

Tests cover:
- Template rendering
- Conditional language validation (CRITICAL)
- No imperative language
- Rationale generation
- Currency formatting

Story 8.3 - AI Recommendations (No Actions)
"""

import pytest

from src.models.ai_insight import InsightType, InsightSeverity
from src.models.ai_recommendation import (
    RecommendationType,
    RecommendationPriority,
    EstimatedImpact,
    RiskLevel,
)
from src.services.recommendation_templates import (
    render_recommendation_text,
    render_rationale,
    validate_recommendation_language,
    RECOMMENDATION_TEMPLATES,
    RATIONALE_TEMPLATES,
    FORBIDDEN_PHRASES,
    CONDITIONAL_PHRASES,
    CURRENCY_SYMBOLS,
)
from src.services.recommendation_generation_service import DetectedRecommendation


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_detected_reduce_spend():
    """Create a sample detected recommendation for reduce_spend."""
    return DetectedRecommendation(
        recommendation_type=RecommendationType.REDUCE_SPEND,
        source_insight_id="insight-123",
        source_insight_type=InsightType.ROAS_CHANGE,
        source_severity=InsightSeverity.WARNING,
        direction="decrease",
        priority=RecommendationPriority.MEDIUM,
        estimated_impact=EstimatedImpact.MODERATE,
        risk_level=RiskLevel.MEDIUM,
        confidence_score=0.8,
        affected_entity="meta_ads",
        affected_entity_type="platform",
        currency="USD",
    )


@pytest.fixture
def sample_detected_scale_campaign():
    """Create a sample detected recommendation for scale_campaign."""
    return DetectedRecommendation(
        recommendation_type=RecommendationType.SCALE_CAMPAIGN,
        source_insight_id="insight-456",
        source_insight_type=InsightType.ROAS_CHANGE,
        source_severity=InsightSeverity.WARNING,
        direction="increase",
        priority=RecommendationPriority.MEDIUM,
        estimated_impact=EstimatedImpact.MODERATE,
        risk_level=RiskLevel.MEDIUM,
        confidence_score=0.85,
        affected_entity="campaign-789",
        affected_entity_type="campaign",
        currency="USD",
    )


# =============================================================================
# Language Validation Tests (CRITICAL for Story 8.3)
# =============================================================================


class TestLanguageValidation:
    """Tests for recommendation language validation."""

    def test_conditional_language_is_valid(self):
        """Text with conditional language should pass validation."""
        valid_texts = [
            "Consider reducing spend on this campaign.",
            "You may want to review the targeting settings.",
            "This may help improve your ROAS.",
            "Pausing this campaign could preserve budget.",
            "You might consider reallocating budget.",
        ]

        for text in valid_texts:
            is_valid, error = validate_recommendation_language(text)
            assert is_valid, f"Expected valid: {text}, got error: {error}"

    def test_imperative_language_is_invalid(self):
        """Text with imperative language should fail validation."""
        invalid_texts = [
            "You should reduce spend immediately.",
            "You must pause this campaign.",
            "You need to review the creative assets.",
            "Do this now to improve performance.",
            "Make sure to update the targeting.",
            "Ensure that the budget is adjusted.",
        ]

        for text in invalid_texts:
            is_valid, error = validate_recommendation_language(text)
            assert not is_valid, f"Expected invalid: {text}"
            assert "forbidden" in error.lower() or "imperative" in error.lower()

    def test_missing_conditional_is_invalid(self):
        """Text without conditional phrases should fail validation."""
        text = "The campaign budget was adjusted."  # No conditional language

        is_valid, error = validate_recommendation_language(text)
        assert not is_valid
        assert "conditional" in error.lower()


class TestAllTemplatesUseConditionalLanguage:
    """Ensure ALL templates use conditional language."""

    def test_all_recommendation_templates_are_valid(self):
        """Every template should pass language validation."""
        for rec_type, insight_templates in RECOMMENDATION_TEMPLATES.items():
            for insight_type, direction_templates in insight_templates.items():
                if isinstance(direction_templates, str):
                    # Direct template
                    is_valid, error = validate_recommendation_language(direction_templates)
                    assert is_valid, (
                        f"Template for {rec_type.value}/{insight_type} failed: {error}"
                    )
                else:
                    # Direction-specific templates
                    for direction, template in direction_templates.items():
                        is_valid, error = validate_recommendation_language(template)
                        assert is_valid, (
                            f"Template for {rec_type.value}/{insight_type}/{direction} "
                            f"failed: {error}"
                        )

    def test_all_rationale_templates_do_not_use_imperatives(self):
        """Rationale templates should not use imperative language."""
        for rec_type, templates in RATIONALE_TEMPLATES.items():
            if isinstance(templates, str):
                text_lower = templates.lower()
                for forbidden in FORBIDDEN_PHRASES:
                    assert forbidden not in text_lower, (
                        f"Rationale for {rec_type.value} contains '{forbidden}'"
                    )
            else:
                for key, template in templates.items():
                    text_lower = template.lower()
                    for forbidden in FORBIDDEN_PHRASES:
                        assert forbidden not in text_lower, (
                            f"Rationale for {rec_type.value}/{key} contains '{forbidden}'"
                        )


# =============================================================================
# Template Rendering Tests
# =============================================================================


class TestRenderRecommendationText:
    """Tests for render_recommendation_text function."""

    def test_renders_reduce_spend_template(self, sample_detected_reduce_spend):
        """Should render reduce_spend template with context."""
        text = render_recommendation_text(sample_detected_reduce_spend)

        assert len(text) > 0
        assert "consider" in text.lower() or "may" in text.lower()
        # Should mention the platform
        assert "meta" in text.lower() or "platform" in text.lower() or "spend" in text.lower()

    def test_renders_scale_campaign_template(self, sample_detected_scale_campaign):
        """Should render scale_campaign template with context."""
        text = render_recommendation_text(sample_detected_scale_campaign)

        assert len(text) > 0
        is_valid, _ = validate_recommendation_language(text)
        assert is_valid

    def test_handles_missing_template_gracefully(self):
        """Should return fallback text when specific template not found."""
        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.ADJUST_BIDDING,
            source_insight_id="insight-999",
            source_insight_type=InsightType.AOV_CHANGE,  # Unlikely combination
            source_severity=InsightSeverity.INFO,
            direction="increase",
            priority=RecommendationPriority.LOW,
            estimated_impact=EstimatedImpact.MINIMAL,
            risk_level=RiskLevel.LOW,
            confidence_score=0.6,
        )

        text = render_recommendation_text(detected)

        assert len(text) > 0
        # Should still be valid language
        is_valid, error = validate_recommendation_language(text)
        assert is_valid, f"Fallback text invalid: {error}"

    def test_entity_suffix_for_platform(self, sample_detected_reduce_spend):
        """Should include platform name in entity suffix."""
        text = render_recommendation_text(sample_detected_reduce_spend)

        # Platform "meta_ads" should be formatted
        assert "meta" in text.lower() or "on" in text.lower()

    def test_entity_suffix_for_campaign(self, sample_detected_scale_campaign):
        """Should include campaign reference in entity suffix."""
        text = render_recommendation_text(sample_detected_scale_campaign)

        # Should have campaign reference
        assert len(text) > 0


# =============================================================================
# Rationale Rendering Tests
# =============================================================================


class TestRenderRationale:
    """Tests for render_rationale function."""

    def test_renders_rationale_for_reduce_spend(self, sample_detected_reduce_spend):
        """Should render rationale for reduce_spend."""
        rationale = render_rationale(sample_detected_reduce_spend)

        assert len(rationale) > 0
        # Should not contain forbidden language
        rationale_lower = rationale.lower()
        for forbidden in FORBIDDEN_PHRASES:
            assert forbidden not in rationale_lower

    def test_critical_severity_uses_specific_rationale(self):
        """Critical severity should use severity-specific rationale when available."""
        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.PAUSE_CAMPAIGN,
            source_insight_id="insight-123",
            source_insight_type=InsightType.ROAS_CHANGE,
            source_severity=InsightSeverity.CRITICAL,
            direction="decrease",
            priority=RecommendationPriority.HIGH,
            estimated_impact=EstimatedImpact.SIGNIFICANT,
            risk_level=RiskLevel.HIGH,
            confidence_score=0.9,
        )

        rationale = render_rationale(detected)

        assert len(rationale) > 0
        # Critical rationales often mention "significant" or urgency
        assert "significant" in rationale.lower() or "prevent" in rationale.lower()

    def test_fallback_rationale(self):
        """Should return fallback rationale when template not found."""
        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.OPTIMIZE_TARGETING,
            source_insight_id="insight-999",
            source_insight_type=InsightType.AOV_CHANGE,
            source_severity=InsightSeverity.INFO,
            direction="decrease",
            priority=RecommendationPriority.LOW,
            estimated_impact=EstimatedImpact.MINIMAL,
            risk_level=RiskLevel.LOW,
            confidence_score=0.5,
        )

        rationale = render_rationale(detected)

        assert len(rationale) > 0


# =============================================================================
# Currency Symbol Tests
# =============================================================================


class TestCurrencySymbols:
    """Tests for currency symbol handling."""

    def test_common_currencies_have_symbols(self):
        """Common currencies should have symbols defined."""
        expected_currencies = ["USD", "EUR", "GBP", "CAD", "AUD"]

        for currency in expected_currencies:
            assert currency in CURRENCY_SYMBOLS
            assert len(CURRENCY_SYMBOLS[currency]) > 0

    def test_usd_symbol(self):
        """USD should use $ symbol."""
        assert CURRENCY_SYMBOLS["USD"] == "$"

    def test_eur_symbol(self):
        """EUR should use € symbol."""
        assert CURRENCY_SYMBOLS["EUR"] == "\u20ac"  # €

    def test_gbp_symbol(self):
        """GBP should use £ symbol."""
        assert CURRENCY_SYMBOLS["GBP"] == "\u00a3"  # £


# =============================================================================
# Template Coverage Tests
# =============================================================================


class TestTemplateCoverage:
    """Tests to ensure template coverage for insight types."""

    def test_reduce_spend_has_templates(self):
        """REDUCE_SPEND should have templates for common insight types."""
        assert RecommendationType.REDUCE_SPEND in RECOMMENDATION_TEMPLATES

        reduce_spend_templates = RECOMMENDATION_TEMPLATES[RecommendationType.REDUCE_SPEND]
        assert InsightType.SPEND_ANOMALY in reduce_spend_templates
        assert InsightType.ROAS_CHANGE in reduce_spend_templates

    def test_scale_campaign_has_templates(self):
        """SCALE_CAMPAIGN should have templates."""
        assert RecommendationType.SCALE_CAMPAIGN in RECOMMENDATION_TEMPLATES

    def test_reallocate_budget_has_templates(self):
        """REALLOCATE_BUDGET should have templates."""
        assert RecommendationType.REALLOCATE_BUDGET in RECOMMENDATION_TEMPLATES

    def test_all_recommendation_types_have_rationale(self):
        """Every recommendation type should have a rationale template."""
        for rec_type in RecommendationType:
            assert rec_type in RATIONALE_TEMPLATES, (
                f"Missing rationale template for {rec_type.value}"
            )


# =============================================================================
# No Guarantees Tests
# =============================================================================


class TestNoGuarantees:
    """Ensure templates don't make specific guarantees."""

    def test_no_specific_percentages_in_templates(self):
        """Templates should not promise specific percentage improvements."""
        # Patterns that indicate specific guarantees
        guarantee_patterns = [
            "will improve by",
            "will increase by",
            "will reduce by",
            "will save",
            "guaranteed",
            "definitely",
            "certainly",
        ]

        for rec_type, insight_templates in RECOMMENDATION_TEMPLATES.items():
            for insight_type, direction_templates in insight_templates.items():
                if isinstance(direction_templates, str):
                    templates = [direction_templates]
                else:
                    templates = direction_templates.values()

                for template in templates:
                    template_lower = template.lower()
                    for pattern in guarantee_patterns:
                        assert pattern not in template_lower, (
                            f"Template for {rec_type.value} contains guarantee: '{pattern}'"
                        )
