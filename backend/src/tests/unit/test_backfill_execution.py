"""
Unit tests for BackfillExecution model.

Tests database model operations, field validation, and status transitions.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db_base import Base
from src.models.backfill_execution import BackfillExecution, BackfillStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def db_session():
    """Create in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ============================================================================
# TEST SUITE: MODEL CREATION
# ============================================================================

class TestBackfillExecutionCreation:
    """Test BackfillExecution model creation and field validation."""

    def test_create_backfill_execution_with_required_fields(self, db_session):
        """BackfillExecution can be created with required fields."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.RUNNING,
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.id is not None
        assert backfill.tenant_id == "tenant-123"
        # SQLite doesn't preserve timezone, so compare naive datetimes
        assert backfill.start_date.replace(tzinfo=None) == start_date.replace(tzinfo=None)
        assert backfill.end_date.replace(tzinfo=None) == end_date.replace(tzinfo=None)
        assert backfill.status == BackfillStatus.RUNNING
        assert backfill.created_at is not None
        assert backfill.updated_at is not None

    def test_create_global_backfill_with_null_tenant_id(self, db_session):
        """BackfillExecution supports global backfills with null tenant_id."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id=None,  # Global backfill
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.RUNNING,
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.tenant_id is None
        # SQLite doesn't preserve timezone, so compare naive datetimes
        assert backfill.start_date.replace(tzinfo=None) == start_date.replace(tzinfo=None)
        assert backfill.end_date.replace(tzinfo=None) == end_date.replace(tzinfo=None)

    def test_backfill_execution_default_status(self, db_session):
        """BackfillExecution defaults to RUNNING status."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            # status not specified - should default to RUNNING
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.status == BackfillStatus.RUNNING

    def test_backfill_execution_with_models_run(self, db_session):
        """BackfillExecution can store list of models executed."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            models_run=["staging.stg_shopify_orders", "facts.fact_orders"],
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.models_run == ["staging.stg_shopify_orders", "facts.fact_orders"]

    def test_backfill_execution_with_optional_fields(self, db_session):
        """BackfillExecution can store optional fields (records, duration, error)."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
            records_processed=1000,
            duration_seconds=45.5,
            error_message=None,
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.records_processed == 1000
        assert backfill.duration_seconds == 45.5
        assert backfill.error_message is None

    def test_backfill_execution_with_error(self, db_session):
        """BackfillExecution can store error messages."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.FAILED,
            error_message="dbt run failed: Connection timeout",
        )

        db_session.add(backfill)
        db_session.commit()

        assert backfill.status == BackfillStatus.FAILED
        assert backfill.error_message == "dbt run failed: Connection timeout"


# ============================================================================
# TEST SUITE: STATUS TRANSITIONS
# ============================================================================

class TestBackfillExecutionStatusTransitions:
    """Test BackfillExecution status transitions."""

    def test_status_transition_running_to_completed(self, db_session):
        """BackfillExecution can transition from RUNNING to COMPLETED."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.RUNNING,
        )

        db_session.add(backfill)
        db_session.commit()

        # Update status
        backfill.status = BackfillStatus.COMPLETED
        backfill.duration_seconds = 30.0
        backfill.records_processed = 500
        db_session.commit()

        assert backfill.status == BackfillStatus.COMPLETED
        assert backfill.duration_seconds == 30.0
        assert backfill.records_processed == 500

    def test_status_transition_running_to_failed(self, db_session):
        """BackfillExecution can transition from RUNNING to FAILED."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.RUNNING,
        )

        db_session.add(backfill)
        db_session.commit()

        # Update status to failed
        backfill.status = BackfillStatus.FAILED
        backfill.error_message = "dbt compile failed: SQL syntax error"
        backfill.duration_seconds = 5.2
        db_session.commit()

        assert backfill.status == BackfillStatus.FAILED
        assert backfill.error_message == "dbt compile failed: SQL syntax error"
        assert backfill.duration_seconds == 5.2


# ============================================================================
# TEST SUITE: TENANT ISOLATION
# ============================================================================

class TestBackfillExecutionTenantIsolation:
    """Test tenant isolation for BackfillExecution queries."""

    def test_query_by_tenant_id(self, db_session):
        """BackfillExecution can be queried by tenant_id."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        # Create backfills for different tenants
        backfill1 = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
        )

        backfill2 = BackfillExecution(
            tenant_id="tenant-456",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
        )

        backfill3 = BackfillExecution(
            tenant_id=None,  # Global backfill
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
        )

        db_session.add_all([backfill1, backfill2, backfill3])
        db_session.commit()

        # Query by tenant_id
        tenant_backfills = (
            db_session.query(BackfillExecution)
            .filter(BackfillExecution.tenant_id == "tenant-123")
            .all()
        )

        assert len(tenant_backfills) == 1
        assert tenant_backfills[0].tenant_id == "tenant-123"

    def test_query_global_backfills(self, db_session):
        """BackfillExecution can query global backfills (null tenant_id)."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        # Create tenant-scoped and global backfills
        tenant_backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
        )

        global_backfill = BackfillExecution(
            tenant_id=None,
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.COMPLETED,
        )

        db_session.add_all([tenant_backfill, global_backfill])
        db_session.commit()

        # Query global backfills
        global_backfills = (
            db_session.query(BackfillExecution)
            .filter(BackfillExecution.tenant_id.is_(None))
            .all()
        )

        assert len(global_backfills) == 1
        assert global_backfills[0].tenant_id is None


# ============================================================================
# TEST SUITE: REPR AND SERIALIZATION
# ============================================================================

class TestBackfillExecutionRepr:
    """Test BackfillExecution string representation."""

    def test_backfill_execution_repr(self, db_session):
        """BackfillExecution has informative __repr__."""
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

        backfill = BackfillExecution(
            tenant_id="tenant-123",
            start_date=start_date,
            end_date=end_date,
            status=BackfillStatus.RUNNING,
        )

        db_session.add(backfill)
        db_session.commit()

        repr_str = repr(backfill)

        assert "BackfillExecution" in repr_str
        assert "tenant-123" in repr_str
        assert "running" in repr_str.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
