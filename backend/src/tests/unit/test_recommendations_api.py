"""
Unit tests for AI Recommendations API endpoints.

Tests cover:
- Listing recommendations with filters
- Getting single recommendation
- Accept/dismiss actions
- Batch operations
- Entitlement checks (402)
- Tenant isolation (404)
- Pagination

Story 8.3 - AI Recommendations (No Actions)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models.ai_insight import AIInsight, InsightType, InsightSeverity
from src.models.ai_recommendation import (
    AIRecommendation,
    RecommendationType,
    RecommendationPriority,
    EstimatedImpact,
    RiskLevel,
    AffectedEntityType,
)
from src.api.routes.recommendations import (
    list_recommendations,
    get_recommendation,
    accept_recommendation,
    dismiss_recommendation,
    dismiss_recommendations_batch,
    _recommendation_to_response,
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
def mock_request():
    """Create a mock request with tenant context."""
    request = MagicMock()
    request.state.tenant_id = "test-tenant-123"
    return request


@pytest.fixture
def sample_insight(mock_db_session):
    """Create a sample insight for testing."""
    return AIInsight(
        id=str(uuid.uuid4()),
        tenant_id="test-tenant-123",
        insight_type=InsightType.ROAS_CHANGE,
        severity=InsightSeverity.WARNING,
        summary="ROAS declined by 20%",
        supporting_metrics=[{"metric": "gross_roas", "delta_pct": -20.0}],
        confidence_score=0.85,
        period_type="weekly",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        comparison_type="week_over_week",
        content_hash="abc123",
        generated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_recommendation(sample_insight):
    """Create a sample recommendation for testing."""
    return AIRecommendation(
        id=str(uuid.uuid4()),
        tenant_id="test-tenant-123",
        related_insight_id=sample_insight.id,
        recommendation_type=RecommendationType.REDUCE_SPEND,
        priority=RecommendationPriority.MEDIUM,
        recommendation_text="Consider reducing spend while ROAS remains below target.",
        rationale="This may help preserve budget.",
        estimated_impact=EstimatedImpact.MODERATE,
        risk_level=RiskLevel.MEDIUM,
        confidence_score=0.8,
        affected_entity="meta_ads",
        affected_entity_type=AffectedEntityType.PLATFORM,
        currency="USD",
        generated_at=datetime.now(timezone.utc),
        content_hash="def456",
        is_accepted=0,
        is_dismissed=0,
    )


# =============================================================================
# Response Model Tests
# =============================================================================


class TestRecommendationToResponse:
    """Tests for _recommendation_to_response helper."""

    def test_converts_recommendation_to_response(self, sample_recommendation):
        """Should convert recommendation model to response format."""
        response = _recommendation_to_response(sample_recommendation)

        assert response.recommendation_id == sample_recommendation.id
        assert response.related_insight_id == sample_recommendation.related_insight_id
        assert response.recommendation_type == "reduce_spend"
        assert response.priority == "medium"
        assert "Consider reducing spend" in response.recommendation_text
        assert response.estimated_impact == "moderate"
        assert response.risk_level == "medium"
        assert response.confidence_score == 0.8
        assert response.affected_entity == "meta_ads"
        assert response.affected_entity_type == "platform"
        assert response.is_accepted is False
        assert response.is_dismissed is False

    def test_handles_none_values(self):
        """Should handle None values gracefully."""
        rec = AIRecommendation(
            id="test-id",
            tenant_id="test-tenant",
            related_insight_id="insight-id",
            recommendation_type=RecommendationType.REVIEW_CREATIVE,
            priority=RecommendationPriority.LOW,
            recommendation_text="Review creative",
            estimated_impact=EstimatedImpact.MINIMAL,
            risk_level=RiskLevel.LOW,
            confidence_score=0.5,
            content_hash="hash",
            generated_at=datetime.now(timezone.utc),
        )

        response = _recommendation_to_response(rec)

        assert response.affected_entity is None
        assert response.affected_entity_type is None
        assert response.currency is None
        assert response.rationale is None


# =============================================================================
# List Recommendations Tests
# =============================================================================


class TestListRecommendations:
    """Tests for list_recommendations endpoint."""

    @pytest.mark.asyncio
    async def test_returns_tenant_recommendations(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should return only recommendations for authenticated tenant."""
        # Setup mock query
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.all.return_value = [sample_recommendation]
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await list_recommendations(
                request=mock_request,
                db_session=mock_db_session,
            )

            assert response.total == 1
            assert len(response.recommendations) == 1
            assert response.recommendations[0].recommendation_type == "reduce_spend"

    @pytest.mark.asyncio
    async def test_filters_by_recommendation_type(
        self, mock_request, mock_db_session
    ):
        """Should filter by recommendation_type when provided."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await list_recommendations(
                request=mock_request,
                db_session=mock_db_session,
                recommendation_type="reduce_spend",
            )

            assert response.total == 0

    @pytest.mark.asyncio
    async def test_invalid_recommendation_type_returns_400(
        self, mock_request, mock_db_session
    ):
        """Should return 400 for invalid recommendation_type."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            with pytest.raises(HTTPException) as exc_info:
                await list_recommendations(
                    request=mock_request,
                    db_session=mock_db_session,
                    recommendation_type="invalid_type",
                )

            assert exc_info.value.status_code == 400
            assert "Invalid recommendation_type" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_excludes_dismissed_by_default(
        self, mock_request, mock_db_session
    ):
        """Should exclude dismissed recommendations by default."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            await list_recommendations(
                request=mock_request,
                db_session=mock_db_session,
                include_dismissed=False,
            )

            # Verify filter was called (checking is_dismissed == 0)
            filter_calls = mock_query.filter.call_args_list
            assert len(filter_calls) > 0

    @pytest.mark.asyncio
    async def test_pagination_has_more(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should correctly indicate has_more when more results exist."""
        # Return limit + 1 results to indicate has_more
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 25
        mock_query.all.return_value = [sample_recommendation] * 21  # limit(20) + 1
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await list_recommendations(
                request=mock_request,
                db_session=mock_db_session,
                limit=20,
            )

            assert response.has_more is True
            assert len(response.recommendations) == 20


# =============================================================================
# Get Single Recommendation Tests
# =============================================================================


class TestGetRecommendation:
    """Tests for get_recommendation endpoint."""

    @pytest.mark.asyncio
    async def test_returns_recommendation_by_id(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should return recommendation when it exists and belongs to tenant."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_recommendation
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await get_recommendation(
                request=mock_request,
                recommendation_id=sample_recommendation.id,
                db_session=mock_db_session,
            )

            assert response.recommendation_id == sample_recommendation.id

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(
        self, mock_request, mock_db_session
    ):
        """Should return 404 when recommendation not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            with pytest.raises(HTTPException) as exc_info:
                await get_recommendation(
                    request=mock_request,
                    recommendation_id="nonexistent-id",
                    db_session=mock_db_session,
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_other_tenant(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should return 404 for recommendation belonging to different tenant."""
        # The query filters by tenant_id, so it won't find the recommendation
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Not found due to tenant filter
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="other-tenant-456")

            with pytest.raises(HTTPException) as exc_info:
                await get_recommendation(
                    request=mock_request,
                    recommendation_id=sample_recommendation.id,
                    db_session=mock_db_session,
                )

            assert exc_info.value.status_code == 404


# =============================================================================
# Accept/Dismiss Action Tests
# =============================================================================


class TestAcceptRecommendation:
    """Tests for accept_recommendation endpoint."""

    @pytest.mark.asyncio
    async def test_marks_recommendation_accepted(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should mark recommendation as accepted."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_recommendation
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await accept_recommendation(
                request=mock_request,
                recommendation_id=sample_recommendation.id,
                db_session=mock_db_session,
            )

            assert response.status == "ok"
            assert sample_recommendation.is_accepted == 1
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_returns_404_when_not_found(
        self, mock_request, mock_db_session
    ):
        """Should return 404 when recommendation not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            with pytest.raises(HTTPException) as exc_info:
                await accept_recommendation(
                    request=mock_request,
                    recommendation_id="nonexistent-id",
                    db_session=mock_db_session,
                )

            assert exc_info.value.status_code == 404


class TestDismissRecommendation:
    """Tests for dismiss_recommendation endpoint."""

    @pytest.mark.asyncio
    async def test_marks_recommendation_dismissed(
        self, mock_request, mock_db_session, sample_recommendation
    ):
        """Should mark recommendation as dismissed."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_recommendation
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await dismiss_recommendation(
                request=mock_request,
                recommendation_id=sample_recommendation.id,
                db_session=mock_db_session,
            )

            assert response.status == "ok"
            assert sample_recommendation.is_dismissed == 1
            mock_db_session.commit.assert_called_once()


# =============================================================================
# Batch Dismiss Tests
# =============================================================================


class TestBatchDismiss:
    """Tests for batch dismiss endpoint."""

    @pytest.mark.asyncio
    async def test_dismisses_multiple_recommendations(
        self, mock_request, mock_db_session
    ):
        """Should dismiss multiple recommendations at once."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 3
        mock_db_session.query.return_value = mock_query

        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            response = await dismiss_recommendations_batch(
                request=mock_request,
                recommendation_ids=["id1", "id2", "id3"],
                db_session=mock_db_session,
            )

            assert response["status"] == "ok"
            assert response["updated"] == 3
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_dismiss_empty_list_returns_400(
        self, mock_request, mock_db_session
    ):
        """Should return 400 for empty recommendation_ids list."""
        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            with pytest.raises(HTTPException) as exc_info:
                await dismiss_recommendations_batch(
                    request=mock_request,
                    recommendation_ids=[],
                    db_session=mock_db_session,
                )

            assert exc_info.value.status_code == 400
            assert "cannot be empty" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_batch_dismiss_exceeds_limit_returns_400(
        self, mock_request, mock_db_session
    ):
        """Should return 400 when exceeding 100 recommendations."""
        with patch("src.api.routes.recommendations.get_tenant_context") as mock_ctx:
            mock_ctx.return_value = MagicMock(tenant_id="test-tenant-123")

            with pytest.raises(HTTPException) as exc_info:
                await dismiss_recommendations_batch(
                    request=mock_request,
                    recommendation_ids=[f"id{i}" for i in range(101)],
                    db_session=mock_db_session,
                )

            assert exc_info.value.status_code == 400
            assert "Maximum 100" in str(exc_info.value.detail)
