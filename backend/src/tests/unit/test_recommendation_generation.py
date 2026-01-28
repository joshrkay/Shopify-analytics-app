"""
Unit tests for AI Recommendation Generation Service.

Tests cover:
- Recommendation generation from insights
- Priority, risk, and impact calculation
- Content hash deduplication
- Insight direction detection
- Maximum recommendations per insight

Story 8.3 - AI Recommendations (No Actions)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.ai_insight import AIInsight, InsightType, InsightSeverity
from src.models.ai_recommendation import (
    AIRecommendation,
    RecommendationType,
    RecommendationPriority,
    EstimatedImpact,
    RiskLevel,
)
from src.services.recommendation_generation_service import (
    RecommendationGenerationService,
    DetectedRecommendation,
)
from src.services.recommendation_rules import (
    get_applicable_recommendations,
    calculate_priority,
    calculate_risk_level,
    calculate_estimated_impact,
    calculate_recommendation_confidence,
    MAX_RECOMMENDATIONS_PER_INSIGHT,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def sample_roas_decline_insight(tenant_id):
    """Create a sample ROAS decline insight."""
    return AIInsight(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        insight_type=InsightType.ROAS_CHANGE,
        severity=InsightSeverity.WARNING,
        summary="ROAS declined by 20%",
        why_it_matters="Lower returns may indicate ad fatigue.",
        supporting_metrics=[
            {
                "metric": "gross_roas",
                "current_value": 2.0,
                "prior_value": 2.5,
                "delta": -0.5,
                "delta_pct": -20.0,
                "timeframe": "week_over_week",
            }
        ],
        confidence_score=0.85,
        period_type="weekly",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        comparison_type="week_over_week",
        platform="meta_ads",
        currency="USD",
        content_hash="abc123",
        generated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_spend_increase_insight(tenant_id):
    """Create a sample spend increase insight."""
    return AIInsight(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        insight_type=InsightType.SPEND_ANOMALY,
        severity=InsightSeverity.CRITICAL,
        summary="Marketing spend increased by 35%",
        supporting_metrics=[
            {
                "metric": "spend",
                "current_value": 13500.0,
                "prior_value": 10000.0,
                "delta": 3500.0,
                "delta_pct": 35.0,
                "timeframe": "week_over_week",
            }
        ],
        confidence_score=0.90,
        period_type="weekly",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        comparison_type="week_over_week",
        currency="USD",
        content_hash="def456",
        generated_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Recommendation Rules Tests
# =============================================================================


class TestGetApplicableRecommendations:
    """Tests for get_applicable_recommendations."""

    def test_roas_decrease_returns_multiple_types(self):
        """ROAS decrease should return multiple recommendation types."""
        recs = get_applicable_recommendations(InsightType.ROAS_CHANGE, "decrease")

        assert len(recs) > 0
        assert len(recs) <= MAX_RECOMMENDATIONS_PER_INSIGHT
        assert RecommendationType.REDUCE_SPEND in recs

    def test_roas_increase_returns_scale_recommendations(self):
        """ROAS increase should return scale recommendations."""
        recs = get_applicable_recommendations(InsightType.ROAS_CHANGE, "increase")

        assert RecommendationType.SCALE_CAMPAIGN in recs

    def test_spend_increase_returns_reduce_spend(self):
        """Spend increase should return reduce_spend recommendation."""
        recs = get_applicable_recommendations(InsightType.SPEND_ANOMALY, "increase")

        assert RecommendationType.REDUCE_SPEND in recs
        assert RecommendationType.REVIEW_CREATIVE in recs

    def test_unknown_direction_uses_default(self):
        """Unknown direction should fall back to default rules."""
        recs = get_applicable_recommendations(
            InsightType.REVENUE_VS_SPEND_DIVERGENCE,
            "unknown",
        )

        # Should use "default" rules
        assert len(recs) > 0

    def test_limits_to_max_recommendations(self):
        """Should never return more than MAX_RECOMMENDATIONS_PER_INSIGHT."""
        for insight_type in InsightType:
            for direction in ["increase", "decrease", "default"]:
                recs = get_applicable_recommendations(insight_type, direction)
                assert len(recs) <= MAX_RECOMMENDATIONS_PER_INSIGHT


class TestCalculatePriority:
    """Tests for priority calculation."""

    def test_critical_severity_returns_high_priority(self):
        """Critical severity should result in high priority."""
        priority = calculate_priority(
            InsightSeverity.CRITICAL,
            RecommendationType.REDUCE_SPEND,
        )
        assert priority == RecommendationPriority.HIGH

    def test_warning_severity_returns_medium_priority(self):
        """Warning severity should result in medium priority."""
        priority = calculate_priority(
            InsightSeverity.WARNING,
            RecommendationType.REVIEW_CREATIVE,
        )
        assert priority == RecommendationPriority.MEDIUM

    def test_info_severity_returns_low_priority(self):
        """Info severity should result in low priority."""
        priority = calculate_priority(
            InsightSeverity.INFO,
            RecommendationType.REVIEW_CREATIVE,
        )
        assert priority == RecommendationPriority.LOW

    def test_high_impact_type_boosts_low_priority(self):
        """High impact types should boost low priority to medium."""
        priority = calculate_priority(
            InsightSeverity.INFO,
            RecommendationType.PAUSE_CAMPAIGN,
        )
        # PAUSE_CAMPAIGN is high impact, should boost to medium
        assert priority == RecommendationPriority.MEDIUM


class TestCalculateRiskLevel:
    """Tests for risk level calculation."""

    def test_pause_campaign_is_high_risk(self):
        """Pause campaign should be high risk."""
        risk = calculate_risk_level(
            RecommendationType.PAUSE_CAMPAIGN,
            InsightSeverity.WARNING,
        )
        assert risk == RiskLevel.HIGH

    def test_review_creative_is_low_risk(self):
        """Review creative should be low risk."""
        risk = calculate_risk_level(
            RecommendationType.REVIEW_CREATIVE,
            InsightSeverity.WARNING,
        )
        assert risk == RiskLevel.LOW

    def test_reduce_spend_is_medium_risk(self):
        """Reduce spend should be medium risk."""
        risk = calculate_risk_level(
            RecommendationType.REDUCE_SPEND,
            InsightSeverity.WARNING,
        )
        assert risk == RiskLevel.MEDIUM

    def test_critical_severity_increases_budget_risk(self):
        """Critical severity should increase risk for budget recommendations."""
        risk = calculate_risk_level(
            RecommendationType.REDUCE_SPEND,
            InsightSeverity.CRITICAL,
        )
        assert risk == RiskLevel.HIGH


class TestCalculateEstimatedImpact:
    """Tests for estimated impact calculation."""

    def test_critical_severity_significant_impact(self):
        """Critical severity should result in significant impact."""
        impact = calculate_estimated_impact(
            InsightSeverity.CRITICAL,
            RecommendationType.REDUCE_SPEND,
        )
        assert impact == EstimatedImpact.SIGNIFICANT

    def test_info_severity_minimal_impact(self):
        """Info severity should result in minimal impact."""
        impact = calculate_estimated_impact(
            InsightSeverity.INFO,
            RecommendationType.REVIEW_CREATIVE,
        )
        assert impact == EstimatedImpact.MINIMAL

    def test_large_change_magnitude_increases_impact(self):
        """Large change magnitude should increase impact."""
        impact = calculate_estimated_impact(
            InsightSeverity.WARNING,
            RecommendationType.REDUCE_SPEND,
            change_magnitude=40.0,
        )
        assert impact == EstimatedImpact.SIGNIFICANT


class TestCalculateRecommendationConfidence:
    """Tests for confidence score calculation."""

    def test_inherits_from_insight_confidence(self):
        """Should start with insight confidence score."""
        confidence = calculate_recommendation_confidence(
            insight_confidence=0.85,
            recommendation_type=RecommendationType.REDUCE_SPEND,
            insight_severity=InsightSeverity.WARNING,
        )
        # Should be close to 0.85, may be adjusted
        assert 0.7 <= confidence <= 1.0

    def test_simple_recommendations_have_higher_confidence(self):
        """Simple recommendations should have slightly higher confidence."""
        simple_confidence = calculate_recommendation_confidence(
            insight_confidence=0.80,
            recommendation_type=RecommendationType.REVIEW_CREATIVE,
            insight_severity=InsightSeverity.WARNING,
        )
        complex_confidence = calculate_recommendation_confidence(
            insight_confidence=0.80,
            recommendation_type=RecommendationType.REALLOCATE_BUDGET,
            insight_severity=InsightSeverity.WARNING,
        )

        assert simple_confidence >= complex_confidence


# =============================================================================
# Generation Service Tests
# =============================================================================


class TestRecommendationGenerationService:
    """Tests for RecommendationGenerationService."""

    def test_requires_tenant_id(self, mock_db_session):
        """Should raise ValueError if tenant_id is not provided."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            RecommendationGenerationService(mock_db_session, "")

    def test_get_insight_direction_increase(
        self, mock_db_session, tenant_id, sample_spend_increase_insight
    ):
        """Should detect increase direction from positive delta_pct."""
        service = RecommendationGenerationService(mock_db_session, tenant_id)
        direction = service._get_insight_direction(sample_spend_increase_insight)
        assert direction == "increase"

    def test_get_insight_direction_decrease(
        self, mock_db_session, tenant_id, sample_roas_decline_insight
    ):
        """Should detect decrease direction from negative delta_pct."""
        service = RecommendationGenerationService(mock_db_session, tenant_id)
        direction = service._get_insight_direction(sample_roas_decline_insight)
        assert direction == "decrease"

    def test_get_insight_direction_default_when_no_metrics(
        self, mock_db_session, tenant_id
    ):
        """Should return 'default' when no metrics available."""
        insight = AIInsight(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            insight_type=InsightType.CHANNEL_MIX_SHIFT,
            severity=InsightSeverity.INFO,
            summary="Channel mix shifted",
            supporting_metrics=[],
            confidence_score=0.7,
            period_type="weekly",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            comparison_type="week_over_week",
            content_hash="xyz789",
            generated_at=datetime.now(timezone.utc),
        )

        service = RecommendationGenerationService(mock_db_session, tenant_id)
        direction = service._get_insight_direction(insight)
        assert direction == "default"

    def test_generate_for_insight_creates_recommendations(
        self, mock_db_session, tenant_id, sample_roas_decline_insight
    ):
        """Should generate recommendations for an insight."""
        service = RecommendationGenerationService(mock_db_session, tenant_id)
        recommendations = service._generate_for_insight(sample_roas_decline_insight)

        assert len(recommendations) > 0
        assert len(recommendations) <= MAX_RECOMMENDATIONS_PER_INSIGHT

        for rec in recommendations:
            assert isinstance(rec, DetectedRecommendation)
            assert rec.source_insight_id == sample_roas_decline_insight.id
            assert rec.source_insight_type == InsightType.ROAS_CHANGE
            assert rec.direction == "decrease"

    def test_generate_content_hash_is_deterministic(
        self, mock_db_session, tenant_id
    ):
        """Content hash should be deterministic for same inputs."""
        service = RecommendationGenerationService(mock_db_session, tenant_id)

        detected = DetectedRecommendation(
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
        )

        hash1 = service._generate_content_hash(detected)
        hash2 = service._generate_content_hash(detected)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_generate_recommendations_returns_count(
        self, mock_db_session, tenant_id, sample_roas_decline_insight
    ):
        """Should return tuple of recommendations and insights processed count."""
        # Mock the database queries
        mock_execute = MagicMock()
        mock_execute.fetchall.return_value = [(sample_roas_decline_insight.id,)]
        mock_db_session.execute.return_value = mock_execute

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_roas_decline_insight]
        mock_db_session.query.return_value = mock_query

        # Mock add/flush to prevent actual DB operations
        mock_db_session.add = MagicMock()
        mock_db_session.flush = MagicMock()

        service = RecommendationGenerationService(mock_db_session, tenant_id)
        recommendations, insights_processed = service.generate_recommendations(
            job_id=str(uuid.uuid4()),
            insight_ids=[sample_roas_decline_insight.id],
        )

        assert insights_processed == 1

    def test_deduplication_handles_integrity_error(
        self, mock_db_session, tenant_id, sample_roas_decline_insight
    ):
        """Should handle IntegrityError for duplicate recommendations."""
        service = RecommendationGenerationService(mock_db_session, tenant_id)

        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.REDUCE_SPEND,
            source_insight_id=sample_roas_decline_insight.id,
            source_insight_type=InsightType.ROAS_CHANGE,
            source_severity=InsightSeverity.WARNING,
            direction="decrease",
            priority=RecommendationPriority.MEDIUM,
            estimated_impact=EstimatedImpact.MODERATE,
            risk_level=RiskLevel.MEDIUM,
            confidence_score=0.8,
        )

        # Mock flush to raise IntegrityError (duplicate)
        mock_db_session.flush.side_effect = IntegrityError(
            "duplicate key", None, None
        )

        result = service._persist_recommendation(detected, job_id="job-123")

        assert result is None
        mock_db_session.rollback.assert_called_once()


# =============================================================================
# Detected Recommendation Tests
# =============================================================================


class TestDetectedRecommendation:
    """Tests for DetectedRecommendation dataclass."""

    def test_creates_with_required_fields(self):
        """Should create DetectedRecommendation with required fields."""
        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.REDUCE_SPEND,
            source_insight_id="insight-123",
            source_insight_type=InsightType.ROAS_CHANGE,
            source_severity=InsightSeverity.WARNING,
            direction="decrease",
            priority=RecommendationPriority.MEDIUM,
            estimated_impact=EstimatedImpact.MODERATE,
            risk_level=RiskLevel.MEDIUM,
            confidence_score=0.8,
        )

        assert detected.recommendation_type == RecommendationType.REDUCE_SPEND
        assert detected.source_insight_id == "insight-123"
        assert detected.affected_entity is None
        assert detected.currency is None

    def test_creates_with_all_fields(self):
        """Should create DetectedRecommendation with all fields."""
        detected = DetectedRecommendation(
            recommendation_type=RecommendationType.REALLOCATE_BUDGET,
            source_insight_id="insight-456",
            source_insight_type=InsightType.REVENUE_VS_SPEND_DIVERGENCE,
            source_severity=InsightSeverity.CRITICAL,
            direction="default",
            priority=RecommendationPriority.HIGH,
            estimated_impact=EstimatedImpact.SIGNIFICANT,
            risk_level=RiskLevel.HIGH,
            confidence_score=0.9,
            affected_entity="google_ads",
            affected_entity_type="platform",
            currency="EUR",
            change_magnitude=35.5,
        )

        assert detected.affected_entity == "google_ads"
        assert detected.affected_entity_type == "platform"
        assert detected.currency == "EUR"
        assert detected.change_magnitude == 35.5
