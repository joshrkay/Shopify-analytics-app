"""
Service for managing Explore guardrail bypass exceptions.

Story 5.4 - Explore Mode Guardrails (Finalized)
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.explore_guardrail_exception import ExploreGuardrailException
from src.models.user import User


MAX_BYPASS_DURATION_MINUTES = 60


class ExploreGuardrailExceptionError(Exception):
    """Base exception for guardrail exception errors."""


class ExploreGuardrailExceptionNotFound(ExploreGuardrailExceptionError):
    """Raised when exception record is missing."""


class ExploreGuardrailExceptionValidationError(ExploreGuardrailExceptionError):
    """Raised when request payload is invalid."""


class ExploreGuardrailExceptionService:
    """Service for creating, approving, and checking guardrail exceptions."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _normalize_dataset_names(dataset_names: list[str]) -> list[str]:
        cleaned = sorted({name.strip() for name in dataset_names if name and name.strip()})
        if not cleaned:
            raise ExploreGuardrailExceptionValidationError(
                "dataset_names must include at least one dataset"
            )
        return cleaned

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _get_user_or_raise(self, user_id: str) -> User:
        user = (
            self.session.query(User)
            .filter(User.id == user_id, User.is_active == True)
            .first()
        )
        if not user:
            raise ExploreGuardrailExceptionValidationError(
                f"User '{user_id}' not found or inactive"
            )
        return user

    def request_exception(
        self,
        *,
        user_id: str,
        dataset_names: list[str],
        reason: str,
    ) -> tuple[ExploreGuardrailException, bool, str]:
        """Create a pending guardrail exception request (idempotent)."""
        if not reason or not reason.strip():
            raise ExploreGuardrailExceptionValidationError("reason is required")

        self._get_user_or_raise(user_id)
        normalized = self._normalize_dataset_names(dataset_names)

        existing = (
            self.session.query(ExploreGuardrailException)
            .filter(
                ExploreGuardrailException.user_id == user_id,
                ExploreGuardrailException.dataset_names == normalized,
                ExploreGuardrailException.reason == reason.strip(),
                ExploreGuardrailException.approved_by.is_(None),
            )
            .first()
        )
        if existing:
            return existing, False, "Existing pending request returned (idempotent match)"

        active = self._find_active_exception(user_id, normalized)
        if active:
            return active, False, "Active exception already exists for user + datasets"

        record = ExploreGuardrailException(
            user_id=user_id,
            approved_by=None,
            dataset_names=normalized,
            expires_at=None,
            reason=reason.strip(),
        )
        self.session.add(record)
        self.session.flush()
        return record, True, "Guardrail bypass request created"

    def approve_exception(
        self,
        *,
        exception_id: str,
        approved_by: str,
        duration_minutes: int,
    ) -> ExploreGuardrailException:
        """Approve a pending guardrail exception request."""
        if duration_minutes <= 0 or duration_minutes > MAX_BYPASS_DURATION_MINUTES:
            raise ExploreGuardrailExceptionValidationError(
                f"duration_minutes must be 1-{MAX_BYPASS_DURATION_MINUTES}"
            )

        record = (
            self.session.query(ExploreGuardrailException)
            .filter(ExploreGuardrailException.id == exception_id)
            .first()
        )
        if not record:
            raise ExploreGuardrailExceptionNotFound(
                f"Exception '{exception_id}' not found"
            )

        now = self._utc_now()
        if record.approved_by and record.expires_at and record.expires_at > now:
            return record  # Idempotent: already approved and active

        record.approved_by = approved_by
        record.expires_at = now + timedelta(minutes=duration_minutes)
        self.session.add(record)
        self.session.flush()
        return record

    def revoke_exception(self, *, exception_id: str) -> ExploreGuardrailException:
        """Revoke an exception early by expiring it."""
        record = (
            self.session.query(ExploreGuardrailException)
            .filter(ExploreGuardrailException.id == exception_id)
            .first()
        )
        if not record:
            raise ExploreGuardrailExceptionNotFound(
                f"Exception '{exception_id}' not found"
            )

        now = self._utc_now()
        if record.expires_at and record.expires_at <= now:
            return record  # Already expired

        record.expires_at = now
        self.session.add(record)
        self.session.flush()
        return record

    def list_active_exceptions(
        self,
        *,
        user_id: Optional[str] = None,
        dataset_name: Optional[str] = None,
    ) -> list[ExploreGuardrailException]:
        """List active (approved, unexpired) exceptions."""
        now = self._utc_now()
        query = (
            self.session.query(ExploreGuardrailException)
            .filter(
                ExploreGuardrailException.approved_by.isnot(None),
                ExploreGuardrailException.expires_at.isnot(None),
                ExploreGuardrailException.expires_at > now,
            )
        )
        if user_id:
            query = query.filter(ExploreGuardrailException.user_id == user_id)
        if dataset_name:
            query = query.filter(ExploreGuardrailException.dataset_names.any(dataset_name))
        return query.order_by(ExploreGuardrailException.expires_at.asc()).all()

    def get_active_exception_for_user_dataset(
        self,
        *,
        user_id: str,
        dataset_name: str,
    ) -> Optional[ExploreGuardrailException]:
        """Return active exception for user/dataset if present."""
        now = self._utc_now()
        return (
            self.session.query(ExploreGuardrailException)
            .filter(
                ExploreGuardrailException.user_id == user_id,
                ExploreGuardrailException.approved_by.isnot(None),
                ExploreGuardrailException.expires_at.isnot(None),
                ExploreGuardrailException.expires_at > now,
                ExploreGuardrailException.dataset_names.any(dataset_name),
            )
            .first()
        )

    def _find_active_exception(
        self,
        user_id: str,
        dataset_names: list[str],
    ) -> Optional[ExploreGuardrailException]:
        now = self._utc_now()
        return (
            self.session.query(ExploreGuardrailException)
            .filter(
                ExploreGuardrailException.user_id == user_id,
                ExploreGuardrailException.approved_by.isnot(None),
                ExploreGuardrailException.expires_at.isnot(None),
                ExploreGuardrailException.expires_at > now,
                ExploreGuardrailException.dataset_names == dataset_names,
            )
            .first()
        )

    def build_bypass_claim(self, user_id: str) -> dict:
        """Build a compact bypass claim for embed JWTs."""
        now = self._utc_now()
        expired = (
            self.session.query(ExploreGuardrailException)
            .filter(
                ExploreGuardrailException.user_id == user_id,
                ExploreGuardrailException.approved_by.isnot(None),
                ExploreGuardrailException.expires_at.isnot(None),
                ExploreGuardrailException.expires_at <= now,
            )
            .all()
        )
        for record in expired:
            self.ensure_expiration_audit_logged(record.id)

        active = self.list_active_exceptions(user_id=user_id)
        if not active:
            return {}

        datasets = {}
        earliest_exp = None
        for record in active:
            exp = record.expires_at
            if exp:
                for dataset in record.dataset_names:
                    datasets[dataset] = exp.isoformat()
                if earliest_exp is None or exp < earliest_exp:
                    earliest_exp = exp

        return {
            "datasets": datasets,
            "expires_at": earliest_exp.isoformat() if earliest_exp else None,
        }

    def ensure_expiration_audit_logged(self, exception_id: str) -> None:
        """Log expiration once by checking audit logs for existing entry."""
        from src.platform.audit import AuditAction, AuditLog
        from src.services.audit_logger import emit_explore_guardrail_bypass_expired

        already_logged = (
            self.session.query(AuditLog)
            .filter(
                AuditLog.resource_id == exception_id,
                AuditLog.action == AuditAction.EXPLORE_GUARDRAIL_BYPASS_EXPIRED.value,
            )
            .first()
        )
        if already_logged:
            return

        record = (
            self.session.query(ExploreGuardrailException)
            .filter(ExploreGuardrailException.id == exception_id)
            .first()
        )
        if record and record.expires_at:
            emit_explore_guardrail_bypass_expired(self.session, record)
