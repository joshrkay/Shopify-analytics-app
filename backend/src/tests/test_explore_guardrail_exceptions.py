"""
Tests for Explore guardrail exception service (Story 5.4).
"""

import pytest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.services.explore_guardrail_exception_service import (
    ExploreGuardrailExceptionService,
    ExploreGuardrailExceptionValidationError,
)


def _mock_user(user_id="user_123"):
    return SimpleNamespace(id=user_id, is_active=True)


def _mock_exception(
    exception_id="ex_1",
    user_id="user_123",
    approved_by=None,
    expires_at=None,
    dataset_names=None,
    reason="Test reason",
):
    return SimpleNamespace(
        id=exception_id,
        user_id=user_id,
        approved_by=approved_by,
        expires_at=expires_at,
        dataset_names=dataset_names or ["fact_orders"],
        reason=reason,
    )


class TestExploreGuardrailExceptionService:
    def test_request_exception_idempotent_pending(self):
        mock_db = MagicMock()
        user = _mock_user()
        existing = _mock_exception(approved_by=None)

        # user lookup -> existing pending -> no active exception
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            user,
            existing,
            None,
        ]

        service = ExploreGuardrailExceptionService(mock_db)
        record, created, message = service.request_exception(
            user_id="user_123",
            dataset_names=["fact_orders", " fact_orders "],
            reason="Valid reason for request",
        )

        assert record == existing
        assert created is False
        assert "idempotent" in message.lower()

    def test_request_exception_requires_reason(self):
        mock_db = MagicMock()
        user = _mock_user()
        mock_db.query.return_value.filter.return_value.first.side_effect = [user]

        service = ExploreGuardrailExceptionService(mock_db)
        with pytest.raises(ExploreGuardrailExceptionValidationError):
            service.request_exception(
                user_id="user_123",
                dataset_names=["fact_orders"],
                reason="",
            )

    def test_approve_exception_sets_expiration(self):
        mock_db = MagicMock()
        record = _mock_exception(approved_by=None, expires_at=None)
        mock_db.query.return_value.filter.return_value.first.return_value = record

        service = ExploreGuardrailExceptionService(mock_db)
        result = service.approve_exception(
            exception_id="ex_1",
            approved_by="approver_1",
            duration_minutes=30,
        )

        assert result.approved_by == "approver_1"
        assert result.expires_at is not None

    def test_approve_exception_duration_limit(self):
        mock_db = MagicMock()
        service = ExploreGuardrailExceptionService(mock_db)
        with pytest.raises(ExploreGuardrailExceptionValidationError):
            service.approve_exception(
                exception_id="ex_1",
                approved_by="approver_1",
                duration_minutes=61,
            )

    def test_build_bypass_claim(self):
        mock_db = MagicMock()
        now = datetime.now(timezone.utc)
        active = _mock_exception(
            approved_by="approver",
            expires_at=now + timedelta(minutes=30),
            dataset_names=["fact_orders", "fact_marketing_spend"],
        )
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [active]

        service = ExploreGuardrailExceptionService(mock_db)
        claim = service.build_bypass_claim("user_123")

        assert "datasets" in claim
        assert "fact_orders" in claim["datasets"]
