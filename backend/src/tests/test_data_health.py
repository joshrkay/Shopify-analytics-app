"""
Tests for data freshness and health monitoring.

CRITICAL: These tests verify that:
1. Freshness status is calculated correctly
2. Stale data is properly flagged
3. Per-source health indicators are accurate
4. Tenant isolation is enforced
5. Health summary aggregates correctly

Story 3.6 - Data Freshness & Health Monitoring
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment
os.environ["ENV"] = "test"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-data-health"

from src.db_base import Base
from src.models.airbyte_connection import (
    TenantAirbyteConnection,
    ConnectionStatus,
    ConnectionType,
)
from src.services.data_health_service import (
    DataHealthService,
    FreshnessStatus,
    SourceHealthInfo,
    DataHealthSummary,
    DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
    DEFAULT_CRITICAL_THRESHOLD_MINUTES,
    DEFAULT_SYNC_FREQUENCY_MINUTES,
)


# =============================================================================
# Test Database Fixtures
# =============================================================================

def _get_test_database_url():
    """Get database URL for testing."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return "sqlite:///:memory:"
    return database_url


@pytest.fixture(scope="module")
def db_engine():
    """Create database engine for tests."""
    database_url = _get_test_database_url()

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(database_url, pool_pre_ping=True)

    from src.models import airbyte_connection

    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test with transaction rollback."""
    connection = db_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# =============================================================================
# Test Identity Fixtures
# =============================================================================

@pytest.fixture
def tenant_id() -> str:
    """Generate unique tenant ID."""
    return f"tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def other_tenant_id() -> str:
    """Generate unique tenant ID for cross-tenant tests."""
    return f"other-tenant-{uuid.uuid4().hex[:8]}"


# =============================================================================
# Connection Creation Fixtures
# =============================================================================

@pytest.fixture
def create_connection(db_session, tenant_id):
    """Factory to create test connections with various states."""
    def _create(
        status: ConnectionStatus = ConnectionStatus.ACTIVE,
        is_enabled: bool = True,
        last_sync_at: datetime = None,
        last_sync_status: str = None,
        sync_frequency_minutes: str = "60",
        source_type: str = "shopify",
        connection_name: str = None,
        custom_tenant_id: str = None,
    ) -> TenantAirbyteConnection:
        connection = TenantAirbyteConnection(
            id=str(uuid.uuid4()),
            tenant_id=custom_tenant_id or tenant_id,
            airbyte_connection_id=f"airbyte-{uuid.uuid4().hex[:8]}",
            connection_name=connection_name or f"Test Connection {uuid.uuid4().hex[:4]}",
            connection_type=ConnectionType.SOURCE,
            source_type=source_type,
            status=status,
            is_enabled=is_enabled,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            sync_frequency_minutes=sync_frequency_minutes,
        )
        db_session.add(connection)
        db_session.commit()
        return connection

    return _create


@pytest.fixture
def data_health_service(db_session, tenant_id):
    """Create DataHealthService for testing."""
    return DataHealthService(db_session, tenant_id)


# =============================================================================
# Test: Service Initialization
# =============================================================================

class TestServiceInitialization:
    """Tests for DataHealthService initialization."""

    def test_requires_tenant_id(self, db_session):
        """Service requires tenant_id."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            DataHealthService(db_session, "")

        with pytest.raises(ValueError, match="tenant_id is required"):
            DataHealthService(db_session, None)

    def test_initializes_with_valid_tenant_id(self, db_session, tenant_id):
        """Service initializes with valid tenant_id."""
        service = DataHealthService(db_session, tenant_id)
        assert service.tenant_id == tenant_id

    def test_configurable_thresholds(self, db_session, tenant_id):
        """Freshness thresholds can be configured."""
        service = DataHealthService(
            db_session,
            tenant_id,
            freshness_threshold_minutes=30,
            critical_threshold_minutes=120,
        )
        assert service.freshness_threshold_minutes == 30
        assert service.critical_threshold_minutes == 120


# =============================================================================
# Test: Freshness Status Calculation
# =============================================================================

class TestFreshnessStatusCalculation:
    """Tests for freshness status calculation."""

    def test_fresh_status_recent_sync(self, data_health_service, create_connection):
        """Connection with recent sync is fresh."""
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
            sync_frequency_minutes="60",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health is not None
        assert health.freshness_status == FreshnessStatus.FRESH
        assert health.is_stale is False
        assert health.is_healthy is True

    def test_stale_status_old_sync(self, data_health_service, create_connection):
        """Connection with old sync is stale."""
        last_sync = datetime.now(timezone.utc) - timedelta(hours=5)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
            sync_frequency_minutes="60",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health is not None
        assert health.freshness_status == FreshnessStatus.STALE
        assert health.is_stale is True
        assert health.is_healthy is False
        assert "stale" in health.warning_message.lower()

    def test_critical_status_very_old_sync(self, db_session, tenant_id, create_connection):
        """Connection with very old sync is critical."""
        last_sync = datetime.now(timezone.utc) - timedelta(hours=30)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
        )

        service = DataHealthService(
            db_session, tenant_id,
            critical_threshold_minutes=1440,  # 24 hours
        )
        health = service.get_source_health(connection.id)

        assert health is not None
        assert health.freshness_status == FreshnessStatus.CRITICAL
        assert health.is_stale is True
        assert health.is_healthy is False
        assert "critically stale" in health.warning_message.lower()

    def test_never_synced_status(self, data_health_service, create_connection):
        """Connection that has never synced has never_synced status."""
        connection = create_connection(
            last_sync_at=None,
            last_sync_status=None,
        )

        health = data_health_service.get_source_health(connection.id)

        assert health is not None
        assert health.freshness_status == FreshnessStatus.NEVER_SYNCED
        assert health.is_stale is True
        assert health.is_healthy is False
        assert "never been synced" in health.warning_message.lower()

    def test_uses_sync_frequency_for_threshold(self, db_session, tenant_id, create_connection):
        """Freshness threshold uses connection sync_frequency."""
        # Sync was 90 minutes ago, frequency is 120 minutes - should be fresh
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=90)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
            sync_frequency_minutes="120",  # 2 hour frequency
        )

        service = DataHealthService(
            db_session, tenant_id,
            freshness_threshold_minutes=60,  # 1 hour threshold
        )
        health = service.get_source_health(connection.id)

        # Should be fresh because 90 mins < 120 mins (sync frequency)
        assert health.freshness_status == FreshnessStatus.FRESH
        assert health.is_healthy is True


# =============================================================================
# Test: Source Health Information
# =============================================================================

class TestSourceHealthInfo:
    """Tests for source health information."""

    def test_includes_all_fields(self, data_health_service, create_connection):
        """Health info includes all required fields."""
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
            source_type="shopify",
            connection_name="My Shopify Store",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health.connection_id == connection.id
        assert health.connection_name == "My Shopify Store"
        assert health.source_type == "shopify"
        assert health.status == "active"
        assert health.is_enabled is True
        assert health.freshness_status == FreshnessStatus.FRESH
        assert health.last_sync_at is not None
        assert health.last_sync_status == "success"
        assert health.sync_frequency_minutes == 60
        assert health.minutes_since_sync is not None
        assert health.expected_next_sync_at is not None

    def test_calculates_minutes_since_sync(self, data_health_service, create_connection):
        """Correctly calculates minutes since last sync."""
        minutes_ago = 45
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        connection = create_connection(last_sync_at=last_sync)

        health = data_health_service.get_source_health(connection.id)

        # Allow 1 minute tolerance for test execution time
        assert abs(health.minutes_since_sync - minutes_ago) <= 1

    def test_calculates_expected_next_sync(self, data_health_service, create_connection):
        """Correctly calculates expected next sync time."""
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)
        connection = create_connection(
            last_sync_at=last_sync,
            sync_frequency_minutes="60",
        )

        health = data_health_service.get_source_health(connection.id)

        expected_next = last_sync + timedelta(minutes=60)
        # Allow 1 second tolerance
        assert abs((health.expected_next_sync_at - expected_next).total_seconds()) < 1

    def test_returns_none_for_nonexistent(self, data_health_service):
        """Returns None for nonexistent connection."""
        health = data_health_service.get_source_health("nonexistent-id")
        assert health is None


# =============================================================================
# Test: Warning Messages
# =============================================================================

class TestWarningMessages:
    """Tests for warning message generation."""

    def test_no_warning_for_healthy(self, data_health_service, create_connection):
        """No warning for healthy connections."""
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=10)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="success",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health.warning_message is None

    def test_warning_for_failed_sync(self, data_health_service, create_connection):
        """Warning for failed last sync."""
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=10)
        connection = create_connection(
            last_sync_at=last_sync,
            last_sync_status="failed",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health.warning_message is not None
        assert "failed" in health.warning_message.lower()

    def test_warning_for_failed_connection(self, data_health_service, create_connection):
        """Warning for connection in failed state."""
        connection = create_connection(
            status=ConnectionStatus.FAILED,
            last_sync_at=datetime.now(timezone.utc),
            last_sync_status="success",
        )

        health = data_health_service.get_source_health(connection.id)

        assert health.warning_message is not None
        assert "failed" in health.warning_message.lower()


# =============================================================================
# Test: Data Health Summary
# =============================================================================

class TestDataHealthSummary:
    """Tests for data health summary."""

    def test_empty_summary_for_no_sources(self, data_health_service):
        """Summary is empty when no sources exist."""
        summary = data_health_service.get_data_health_summary()

        assert summary.total_sources == 0
        assert summary.healthy_sources == 0
        assert summary.stale_sources == 0
        assert summary.overall_health_score == 100.0
        assert summary.has_warnings is False
        assert len(summary.sources) == 0

    def test_counts_healthy_sources(self, data_health_service, create_connection):
        """Correctly counts healthy sources."""
        # Create 2 healthy connections
        for _ in range(2):
            create_connection(
                last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                last_sync_status="success",
            )

        summary = data_health_service.get_data_health_summary()

        assert summary.total_sources == 2
        assert summary.healthy_sources == 2
        assert summary.stale_sources == 0

    def test_counts_stale_sources(self, data_health_service, create_connection):
        """Correctly counts stale sources."""
        # Create 1 healthy, 1 stale
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_sync_status="success",
        )
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
            last_sync_status="success",
        )

        summary = data_health_service.get_data_health_summary()

        assert summary.total_sources == 2
        assert summary.healthy_sources == 1
        assert summary.stale_sources == 1
        assert summary.has_warnings is True

    def test_counts_never_synced(self, data_health_service, create_connection):
        """Correctly counts never synced sources."""
        create_connection(last_sync_at=None)

        summary = data_health_service.get_data_health_summary()

        assert summary.never_synced_sources == 1
        assert summary.has_warnings is True

    def test_counts_disabled_sources(self, data_health_service, create_connection):
        """Correctly counts disabled sources."""
        create_connection(is_enabled=False)

        summary = data_health_service.get_data_health_summary()

        assert summary.disabled_sources == 1

    def test_counts_failed_sources(self, data_health_service, create_connection):
        """Correctly counts failed sources."""
        create_connection(status=ConnectionStatus.FAILED)

        summary = data_health_service.get_data_health_summary()

        assert summary.failed_sources == 1
        assert summary.has_warnings is True

    def test_health_score_all_healthy(self, data_health_service, create_connection):
        """Health score is 100 when all sources are healthy."""
        for _ in range(3):
            create_connection(
                last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                last_sync_status="success",
            )

        summary = data_health_service.get_data_health_summary()

        assert summary.overall_health_score == 100.0

    def test_health_score_with_stale(self, data_health_service, create_connection):
        """Health score decreases with stale sources."""
        # 1 healthy (100), 1 stale (50)
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_sync_status="success",
        )
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
            last_sync_status="success",
        )

        summary = data_health_service.get_data_health_summary()

        # Average of 100 + 50 = 75
        assert summary.overall_health_score == 75.0

    def test_includes_source_details(self, data_health_service, create_connection):
        """Summary includes source details."""
        connection = create_connection(
            connection_name="Test Store",
            source_type="shopify",
        )

        summary = data_health_service.get_data_health_summary()

        assert len(summary.sources) == 1
        assert summary.sources[0].connection_id == connection.id
        assert summary.sources[0].connection_name == "Test Store"


# =============================================================================
# Test: Stale Sources List
# =============================================================================

class TestStaleSources:
    """Tests for stale sources retrieval."""

    def test_returns_empty_when_all_fresh(self, data_health_service, create_connection):
        """Returns empty list when all sources are fresh."""
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_sync_status="success",
        )

        stale = data_health_service.get_stale_sources()

        assert len(stale) == 0

    def test_returns_stale_sources(self, data_health_service, create_connection):
        """Returns stale sources."""
        fresh = create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_sync_status="success",
        )
        stale_conn = create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
            last_sync_status="success",
        )

        stale = data_health_service.get_stale_sources()

        assert len(stale) == 1
        assert stale[0].connection_id == stale_conn.id

    def test_returns_never_synced(self, data_health_service, create_connection):
        """Returns never synced sources as stale."""
        connection = create_connection(last_sync_at=None)

        stale = data_health_service.get_stale_sources()

        assert len(stale) == 1
        assert stale[0].connection_id == connection.id

    def test_excludes_disabled_sources(self, data_health_service, create_connection):
        """Excludes disabled sources from stale list."""
        # Stale but disabled
        create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
            is_enabled=False,
        )

        stale = data_health_service.get_stale_sources()

        assert len(stale) == 0


# =============================================================================
# Test: Tenant Isolation
# =============================================================================

class TestTenantIsolation:
    """Tests for tenant isolation."""

    def test_source_health_tenant_isolation(
        self, db_session, tenant_id, other_tenant_id, create_connection
    ):
        """Source health respects tenant isolation."""
        # Create connection for tenant A
        conn_a = create_connection()

        # Try to access as tenant B
        service_b = DataHealthService(db_session, other_tenant_id)
        health = service_b.get_source_health(conn_a.id)

        assert health is None

    def test_all_sources_tenant_isolation(
        self, db_session, tenant_id, other_tenant_id, create_connection
    ):
        """All sources health respects tenant isolation."""
        # Create connection for tenant A
        create_connection()

        # Create connection for tenant B
        create_connection(custom_tenant_id=other_tenant_id)

        # Check tenant A sees only their connection
        service_a = DataHealthService(db_session, tenant_id)
        sources_a = service_a.get_all_sources_health()
        assert len(sources_a) == 1

        # Check tenant B sees only their connection
        service_b = DataHealthService(db_session, other_tenant_id)
        sources_b = service_b.get_all_sources_health()
        assert len(sources_b) == 1

        # Verify they're different connections
        assert sources_a[0].connection_id != sources_b[0].connection_id

    def test_summary_tenant_isolation(
        self, db_session, tenant_id, other_tenant_id, create_connection
    ):
        """Summary respects tenant isolation."""
        # Create 2 connections for tenant A
        create_connection()
        create_connection()

        # Create 1 connection for tenant B
        create_connection(custom_tenant_id=other_tenant_id)

        # Check tenant A summary
        service_a = DataHealthService(db_session, tenant_id)
        summary_a = service_a.get_data_health_summary()
        assert summary_a.total_sources == 2

        # Check tenant B summary
        service_b = DataHealthService(db_session, other_tenant_id)
        summary_b = service_b.get_data_health_summary()
        assert summary_b.total_sources == 1

    def test_stale_sources_tenant_isolation(
        self, db_session, tenant_id, other_tenant_id, create_connection
    ):
        """Stale sources list respects tenant isolation."""
        # Create stale connection for tenant A
        stale_a = create_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5)
        )

        # Create stale connection for tenant B
        stale_b = create_connection(
            custom_tenant_id=other_tenant_id,
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )

        # Check tenant A sees only their stale connection
        service_a = DataHealthService(db_session, tenant_id)
        stale_list_a = service_a.get_stale_sources()
        assert len(stale_list_a) == 1
        assert stale_list_a[0].connection_id == stale_a.id

        # Check tenant B sees only their stale connection
        service_b = DataHealthService(db_session, other_tenant_id)
        stale_list_b = service_b.get_stale_sources()
        assert len(stale_list_b) == 1
        assert stale_list_b[0].connection_id == stale_b.id


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_handles_timezone_naive_datetime(self, data_health_service, db_session, create_connection):
        """Handles timezone-naive datetimes correctly."""
        # Create with timezone-naive datetime
        connection = TenantAirbyteConnection(
            id=str(uuid.uuid4()),
            tenant_id=data_health_service.tenant_id,
            airbyte_connection_id=f"airbyte-{uuid.uuid4().hex[:8]}",
            connection_name="Naive TZ Connection",
            connection_type=ConnectionType.SOURCE,
            source_type="test",
            status=ConnectionStatus.ACTIVE,
            is_enabled=True,
            last_sync_at=datetime.now(),  # No timezone
            last_sync_status="success",
        )
        db_session.add(connection)
        db_session.commit()

        # Should not raise error
        health = data_health_service.get_source_health(connection.id)
        assert health is not None
        assert health.freshness_status == FreshnessStatus.FRESH

    def test_handles_invalid_sync_frequency(self, db_session, tenant_id, create_connection):
        """Handles invalid sync frequency string."""
        connection = create_connection(sync_frequency_minutes="invalid")

        service = DataHealthService(db_session, tenant_id)
        health = service.get_source_health(connection.id)

        # Should fall back to default
        assert health.sync_frequency_minutes == DEFAULT_SYNC_FREQUENCY_MINUTES

    def test_handles_deleted_connection_status(self, data_health_service, create_connection):
        """Handles deleted connection status."""
        connection = create_connection(status=ConnectionStatus.DELETED)

        health = data_health_service.get_source_health(connection.id)

        assert health.freshness_status == FreshnessStatus.UNKNOWN

    def test_large_number_of_sources(self, data_health_service, create_connection):
        """Handles large number of sources efficiently."""
        # Create 50 connections
        for i in range(50):
            last_sync = datetime.now(timezone.utc) - timedelta(minutes=i * 10)
            create_connection(last_sync_at=last_sync)

        summary = data_health_service.get_data_health_summary()

        assert summary.total_sources == 50
        assert len(summary.sources) == 50
