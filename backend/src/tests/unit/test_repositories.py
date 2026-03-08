"""
Comprehensive unit tests for the repository layer.

Tests:
- BaseRepository (via concrete subclass)
- SubscriptionRepository
- WebhookEventRepository
- BillingAuditRepository
- PlansRepository

All tests use mocked SQLAlchemy sessions — no database required.
"""

import uuid
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch, PropertyMock, call

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from src.repositories.base_repo import BaseRepository
from src.repositories.subscription_repository import (
    SubscriptionRepository,
    WebhookEventRepository,
    BillingAuditRepository,
)
from src.repositories.plans_repo import (
    PlansRepository,
    PlanNotFoundError,
    PlanAlreadyExistsError,
)
from src.db_base import Base
from src.models.subscription import Subscription, SubscriptionStatus
from src.models.billing_event import BillingEvent, BillingEventType
from src.models.plan import Plan, PlanFeature


# ---------------------------------------------------------------------------
# Helpers for BaseRepository tests
# ---------------------------------------------------------------------------

class _FakeModel:
    """Lightweight stand-in for an ORM model used in BaseRepository tests."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    id = "fake-id"
    tenant_id = "tenant-1"
    name = "test"


class _ConcreteRepository(BaseRepository):
    """Concrete subclass of the abstract BaseRepository for testing."""

    MODEL_CLASS = _FakeModel

    def _get_model_class(self):
        return self.MODEL_CLASS

    def _get_tenant_column_name(self):
        return "tenant_id"


def _make_query_chain(session_mock, terminal_value=None):
    """
    Build a fluent query-chain mock so that
        session.query(Model).filter(...).filter(...).first()
    returns *terminal_value*.  Also supports .all(), .count(), .offset(), .limit().
    """
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.order_by.return_value = chain
    chain.options.return_value = chain
    chain.first.return_value = terminal_value
    chain.all.return_value = [terminal_value] if terminal_value else []
    chain.count.return_value = 1 if terminal_value else 0
    chain.delete.return_value = 0
    session_mock.query.return_value = chain
    return chain


# ===================================================================
#  BaseRepository tests
# ===================================================================


class TestBaseRepositoryConstruction:
    """Tests for BaseRepository.__init__."""

    def test_constructor_stores_tenant_id_and_session(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-abc")
        assert repo.tenant_id == "tenant-abc"
        assert repo.db_session is session

    def test_constructor_raises_on_empty_tenant_id(self):
        session = MagicMock(spec=Session)
        with pytest.raises(ValueError, match="tenant_id is required"):
            _ConcreteRepository(session, "")

    def test_constructor_raises_on_none_tenant_id(self):
        session = MagicMock(spec=Session)
        with pytest.raises(ValueError, match="tenant_id is required"):
            _ConcreteRepository(session, None)

    def test_constructor_raises_on_falsy_tenant_id(self):
        session = MagicMock(spec=Session)
        # 0 is falsy — should raise
        with pytest.raises(ValueError, match="tenant_id is required"):
            _ConcreteRepository(session, 0)


class TestBaseRepositoryEnforceTenantScope:
    """Tests for _enforce_tenant_scope."""

    def test_enforce_tenant_scope_adds_filter(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")

        query_mock = MagicMock()
        query_mock.filter.return_value = query_mock

        result = repo._enforce_tenant_scope(query_mock)
        query_mock.filter.assert_called_once()
        assert result is query_mock


class TestBaseRepositoryGetById:
    """Tests for get_by_id."""

    def test_get_by_id_returns_entity(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        expected = _FakeModel(id="e1", tenant_id="tenant-1")
        chain = _make_query_chain(session, expected)

        result = repo.get_by_id("e1")
        assert result is expected
        session.query.assert_called_once_with(_FakeModel)

    def test_get_by_id_returns_none_when_not_found(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        _make_query_chain(session, None)

        result = repo.get_by_id("missing")
        assert result is None


class TestBaseRepositoryGetAll:
    """Tests for get_all with limit/offset."""

    def test_get_all_returns_list(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        items = [_FakeModel(id="1"), _FakeModel(id="2")]
        chain = _make_query_chain(session)
        chain.all.return_value = items

        result = repo.get_all()
        assert result == items

    def test_get_all_with_limit(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)
        chain.all.return_value = [_FakeModel(id="1")]

        repo.get_all(limit=10)
        chain.limit.assert_called_once_with(10)

    def test_get_all_with_offset(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)

        repo.get_all(offset=5)
        chain.offset.assert_called_once_with(5)

    def test_get_all_with_limit_and_offset(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)

        repo.get_all(limit=10, offset=20)
        chain.limit.assert_called_once_with(10)
        chain.offset.assert_called_once_with(20)

    def test_get_all_no_limit_no_offset_skips_calls(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)

        repo.get_all()
        chain.limit.assert_not_called()
        chain.offset.assert_not_called()


class TestBaseRepositoryCreate:
    """Tests for create."""

    def test_create_sets_tenant_id_from_repo(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")

        entity_data = {"name": "hello"}
        repo.create(entity_data)

        # The model constructor was called via session.add — check data dict was mutated
        assert entity_data["tenant_id"] == "tenant-1"
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()

    def test_create_strips_tenant_id_from_entity_data(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")

        entity_data = {"name": "hello", "tenant_id": "attacker-tenant"}
        repo.create(entity_data)

        # tenant_id should be replaced with the repo's tenant
        assert entity_data["tenant_id"] == "tenant-1"

    def test_create_rollback_on_sqlalchemy_error(self):
        session = MagicMock(spec=Session)
        session.commit.side_effect = SQLAlchemyError("db error")
        repo = _ConcreteRepository(session, "tenant-1")

        with pytest.raises(SQLAlchemyError):
            repo.create({"name": "boom"})

        session.rollback.assert_called_once()


class TestBaseRepositoryUpdate:
    """Tests for update."""

    def test_update_applies_fields(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1", name="old")
        _make_query_chain(session, entity)

        result = repo.update("e1", {"name": "new"})
        assert result is entity
        assert entity.name == "new"
        session.commit.assert_called_once()

    def test_update_returns_none_if_not_found(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        _make_query_chain(session, None)

        result = repo.update("missing", {"name": "x"})
        assert result is None
        session.commit.assert_not_called()

    def test_update_strips_tenant_id(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1", name="old")
        _make_query_chain(session, entity)

        repo.update("e1", {"tenant_id": "evil", "name": "new"})
        # tenant_id should NOT have been changed on the entity
        assert entity.tenant_id == "tenant-1"

    def test_update_rollback_on_sqlalchemy_error(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1", name="old")
        _make_query_chain(session, entity)
        session.commit.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            repo.update("e1", {"name": "new"})

        session.rollback.assert_called_once()

    def test_update_ignores_unknown_fields(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1", name="old")
        _make_query_chain(session, entity)

        repo.update("e1", {"nonexistent_field": "val"})
        assert not hasattr(entity, "nonexistent_field") or entity.__dict__.get("nonexistent_field") is None


class TestBaseRepositoryDelete:
    """Tests for delete."""

    def test_delete_returns_true_on_success(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1")
        _make_query_chain(session, entity)

        result = repo.delete("e1")
        assert result is True
        session.delete.assert_called_once_with(entity)
        session.commit.assert_called_once()

    def test_delete_returns_false_when_not_found(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        _make_query_chain(session, None)

        result = repo.delete("missing")
        assert result is False
        session.delete.assert_not_called()

    def test_delete_rollback_on_sqlalchemy_error(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        entity = _FakeModel(id="e1", tenant_id="tenant-1")
        _make_query_chain(session, entity)
        session.commit.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            repo.delete("e1")

        session.rollback.assert_called_once()


class TestBaseRepositoryCountAndExists:
    """Tests for count and exists."""

    def test_count_returns_value(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)
        chain.count.return_value = 42

        assert repo.count() == 42

    def test_count_returns_zero(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        chain = _make_query_chain(session)
        chain.count.return_value = 0

        assert repo.count() == 0

    def test_exists_true(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        _make_query_chain(session, _FakeModel(id="e1"))

        assert repo.exists("e1") is True

    def test_exists_false(self):
        session = MagicMock(spec=Session)
        repo = _ConcreteRepository(session, "tenant-1")
        _make_query_chain(session, None)

        assert repo.exists("missing") is False


# ===================================================================
#  SubscriptionRepository tests
# ===================================================================


class TestSubscriptionRepositoryGetById:
    """Tests for SubscriptionRepository.get_by_id."""

    def test_get_by_id_with_tenant_isolation(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        chain = _make_query_chain(session, sub)

        result = repo.get_by_id("sub-1", "tenant-1")
        assert result is sub
        session.query.assert_called_once_with(Subscription)
        chain.filter.assert_called_once()

    def test_get_by_id_not_found(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        _make_query_chain(session, None)

        result = repo.get_by_id("missing", "tenant-1")
        assert result is None


class TestSubscriptionRepositoryGetByShopifyId:
    """Tests for get_by_shopify_id."""

    def test_get_by_shopify_id_without_tenant(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        chain = _make_query_chain(session, sub)

        result = repo.get_by_shopify_id("gid://shopify/123")
        assert result is sub
        # filter called once (shopify_subscription_id only)
        chain.filter.assert_called_once()

    def test_get_by_shopify_id_with_tenant(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        chain = _make_query_chain(session, sub)

        result = repo.get_by_shopify_id("gid://shopify/123", tenant_id="tenant-1")
        assert result is sub
        # filter called twice: once for shopify_id, once for tenant_id
        assert chain.filter.call_count == 2

    def test_get_by_shopify_id_not_found(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        _make_query_chain(session, None)

        result = repo.get_by_shopify_id("gid://shopify/nonexistent")
        assert result is None


class TestSubscriptionRepositoryGetActiveForTenant:
    """Tests for get_active_for_tenant."""

    def test_get_active_for_tenant_returns_subscription(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        chain = _make_query_chain(session, sub)

        result = repo.get_active_for_tenant("tenant-1")
        assert result is sub
        session.query.assert_called_once_with(Subscription)

    def test_get_active_for_tenant_returns_none(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        _make_query_chain(session, None)

        result = repo.get_active_for_tenant("tenant-1")
        assert result is None


class TestSubscriptionRepositoryGetAllForTenant:
    """Tests for get_all_for_tenant."""

    def test_get_all_excludes_cancelled_by_default(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        subs = [MagicMock(spec=Subscription), MagicMock(spec=Subscription)]
        chain = _make_query_chain(session)
        chain.all.return_value = subs

        result = repo.get_all_for_tenant("tenant-1")
        assert result == subs
        # Should have two filter calls: tenant_id and notin_ (excluded statuses)
        assert chain.filter.call_count == 2

    def test_get_all_includes_cancelled_when_requested(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        subs = [MagicMock(spec=Subscription)]
        chain = _make_query_chain(session)
        chain.all.return_value = subs

        result = repo.get_all_for_tenant("tenant-1", include_cancelled=True)
        assert result == subs
        # Should only filter by tenant_id (one filter call)
        assert chain.filter.call_count == 1

    def test_get_all_orders_by_created_at_desc(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        chain = _make_query_chain(session)

        repo.get_all_for_tenant("tenant-1")
        chain.order_by.assert_called_once()


class TestSubscriptionRepositoryUpdateStatus:
    """Tests for update_status."""

    def test_update_status_changes_status(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        sub.status = SubscriptionStatus.PENDING.value
        sub.id = "sub-1"
        sub.tenant_id = "tenant-1"

        result = repo.update_status(sub, SubscriptionStatus.ACTIVE)
        assert sub.status == SubscriptionStatus.ACTIVE.value
        assert result is sub

    def test_update_status_from_active_to_cancelled(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        sub.status = SubscriptionStatus.ACTIVE.value
        sub.id = "sub-1"
        sub.tenant_id = "tenant-1"

        result = repo.update_status(sub, SubscriptionStatus.CANCELLED)
        assert sub.status == SubscriptionStatus.CANCELLED.value

    def test_update_status_from_active_to_frozen(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        sub.status = SubscriptionStatus.ACTIVE.value
        sub.id = "sub-1"
        sub.tenant_id = "tenant-1"

        result = repo.update_status(sub, SubscriptionStatus.FROZEN)
        assert sub.status == SubscriptionStatus.FROZEN.value


class TestSubscriptionRepositoryCreate:
    """Tests for SubscriptionRepository.create."""

    def test_create_adds_and_flushes(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)
        sub.id = "sub-1"
        sub.tenant_id = "tenant-1"
        sub.plan_id = "plan-free"

        result = repo.create(sub)
        assert result is sub
        session.add.assert_called_once_with(sub)
        session.flush.assert_called_once()


class TestSubscriptionRepositorySave:
    """Tests for save."""

    def test_save_adds_and_flushes(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        sub = MagicMock(spec=Subscription)

        result = repo.save(sub)
        assert result is sub
        session.add.assert_called_once_with(sub)
        session.flush.assert_called_once()


class TestSubscriptionRepositoryCommitRollback:
    """Tests for commit/rollback."""

    def test_commit_delegates_to_session(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        repo.commit()
        session.commit.assert_called_once()

    def test_rollback_delegates_to_session(self):
        session = MagicMock(spec=Session)
        repo = SubscriptionRepository(session)
        repo.rollback()
        session.rollback.assert_called_once()


# ===================================================================
#  WebhookEventRepository tests
# ===================================================================


class TestWebhookEventRepository:
    """Tests for WebhookEventRepository."""

    @patch("src.repositories.subscription_repository.WebhookEvent", create=True)
    def test_is_processed_returns_true_when_event_exists(self, _):
        session = MagicMock(spec=Session)
        repo = WebhookEventRepository(session)
        chain = _make_query_chain(session, MagicMock())  # non-None = found

        result = repo.is_processed("evt-1")
        assert result is True

    @patch("src.repositories.subscription_repository.WebhookEvent", create=True)
    def test_is_processed_returns_false_when_event_missing(self, _):
        session = MagicMock(spec=Session)
        repo = WebhookEventRepository(session)
        _make_query_chain(session, None)

        result = repo.is_processed("evt-missing")
        assert result is False

    def test_mark_processed_adds_and_flushes(self):
        session = MagicMock(spec=Session)
        repo = WebhookEventRepository(session)

        with patch("src.repositories.subscription_repository.WebhookEvent", create=True) as MockEvent:
            mock_event = MagicMock()
            MockEvent.return_value = mock_event

            repo.mark_processed(
                event_id="evt-1",
                topic="orders/create",
                shop_domain="test.myshopify.com",
                payload_hash="abc123",
            )

            session.add.assert_called_once()
            session.flush.assert_called_once()

    def test_mark_processed_without_payload_hash(self):
        session = MagicMock(spec=Session)
        repo = WebhookEventRepository(session)

        with patch("src.repositories.subscription_repository.WebhookEvent", create=True):
            repo.mark_processed(
                event_id="evt-2",
                topic="app/uninstalled",
                shop_domain="test.myshopify.com",
            )

            session.add.assert_called_once()
            session.flush.assert_called_once()


# ===================================================================
#  BillingAuditRepository tests
# ===================================================================


class TestBillingAuditRepositoryLogEvent:
    """Tests for BillingAuditRepository.log_event."""

    def test_log_event_creates_billing_event(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)

        result = repo.log_event(
            tenant_id="tenant-1",
            event_type=BillingEventType.SUBSCRIPTION_CREATED,
            store_id="store-1",
            subscription_id="sub-1",
            to_plan_id="plan-growth",
            amount_cents=2900,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result is not None

    def test_log_event_with_all_fields(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)

        result = repo.log_event(
            tenant_id="tenant-1",
            event_type=BillingEventType.PLAN_CHANGED,
            store_id="store-1",
            subscription_id="sub-1",
            from_plan_id="plan-free",
            to_plan_id="plan-growth",
            amount_cents=2900,
            shopify_subscription_id="gid://shopify/sub/1",
            metadata={"reason": "upgrade"},
        )

        session.add.assert_called_once()
        added_event = session.add.call_args[0][0]
        assert added_event.tenant_id == "tenant-1"
        assert added_event.event_type == BillingEventType.PLAN_CHANGED.value
        assert added_event.from_plan_id == "plan-free"
        assert added_event.to_plan_id == "plan-growth"
        assert added_event.amount_cents == 2900
        assert added_event.extra_metadata == {"reason": "upgrade"}

    def test_log_event_minimal_fields(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)

        result = repo.log_event(
            tenant_id="tenant-1",
            event_type=BillingEventType.CHARGE_SUCCEEDED,
        )

        session.add.assert_called_once()
        added_event = session.add.call_args[0][0]
        assert added_event.store_id is None
        assert added_event.subscription_id is None
        assert added_event.from_plan_id is None
        assert added_event.to_plan_id is None

    def test_log_event_generates_uuid_id(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)

        repo.log_event(
            tenant_id="tenant-1",
            event_type=BillingEventType.SUBSCRIPTION_CREATED,
        )

        added_event = session.add.call_args[0][0]
        # id should be a valid UUID string
        uuid.UUID(added_event.id)  # raises if not valid


class TestBillingAuditRepositoryGetEvents:
    """Tests for get_events_for_tenant."""

    def test_get_events_for_tenant_basic(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)
        events = [MagicMock(spec=BillingEvent), MagicMock(spec=BillingEvent)]
        chain = _make_query_chain(session)
        chain.all.return_value = events

        result = repo.get_events_for_tenant("tenant-1")
        assert result == events
        session.query.assert_called_once_with(BillingEvent)

    def test_get_events_with_event_type_filter(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)
        chain = _make_query_chain(session)

        repo.get_events_for_tenant("tenant-1", event_type="subscription_created")
        # Two filter calls: tenant_id and event_type
        assert chain.filter.call_count == 2

    def test_get_events_without_event_type_filter(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)
        chain = _make_query_chain(session)

        repo.get_events_for_tenant("tenant-1")
        # One filter call: tenant_id only
        assert chain.filter.call_count == 1

    def test_get_events_with_pagination(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)
        chain = _make_query_chain(session)

        repo.get_events_for_tenant("tenant-1", limit=50, offset=10)
        chain.offset.assert_called_once_with(10)
        chain.limit.assert_called_once_with(50)

    def test_get_events_orders_by_created_at_desc(self):
        session = MagicMock(spec=Session)
        repo = BillingAuditRepository(session)
        chain = _make_query_chain(session)

        repo.get_events_for_tenant("tenant-1")
        chain.order_by.assert_called_once()


# ===================================================================
#  PlansRepository tests
# ===================================================================


class TestPlansRepositoryGetById:
    """Tests for PlansRepository.get_by_id."""

    def test_get_by_id_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        _make_query_chain(session, plan)

        result = repo.get_by_id("plan-free")
        assert result is plan
        session.query.assert_called_once_with(Plan)

    def test_get_by_id_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.get_by_id("missing")
        assert result is None


class TestPlansRepositoryGetByName:
    """Tests for PlansRepository.get_by_name."""

    def test_get_by_name_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        _make_query_chain(session, plan)

        result = repo.get_by_name("growth")
        assert result is plan

    def test_get_by_name_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.get_by_name("nonexistent")
        assert result is None


class TestPlansRepositoryGetAll:
    """Tests for PlansRepository.get_all."""

    def test_get_all_active_only_by_default(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plans = [MagicMock(spec=Plan)]
        chain = _make_query_chain(session)
        chain.all.return_value = plans

        result = repo.get_all()
        assert result == plans
        # Should filter for is_active
        chain.filter.assert_called_once()

    def test_get_all_include_inactive(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)

        repo.get_all(include_inactive=True)
        # Should NOT filter for is_active
        chain.filter.assert_not_called()

    def test_get_all_include_features_uses_selectinload(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)

        repo.get_all(include_features=True)
        chain.options.assert_called_once()

    def test_get_all_without_features_skips_selectinload(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)

        repo.get_all(include_features=False)
        chain.options.assert_not_called()

    def test_get_all_applies_pagination(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)

        repo.get_all(limit=25, offset=50)
        chain.offset.assert_called_once_with(50)
        chain.limit.assert_called_once_with(25)


class TestPlansRepositoryCreate:
    """Tests for PlansRepository.create."""

    def test_create_plan_success(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)

        # Both get_by_name and get_by_id should return None (no conflict)
        chain = _make_query_chain(session, None)

        result = repo.create(
            name="growth",
            display_name="Growth",
            price_monthly_cents=2900,
        )

        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_create_plan_auto_generates_id(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.create(name="growth", display_name="Growth")

        added_plan = session.add.call_args[0][0]
        assert added_plan.id == "plan_growth"

    def test_create_plan_with_custom_id(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.create(
            name="growth",
            display_name="Growth",
            plan_id="custom-id",
        )

        added_plan = session.add.call_args[0][0]
        assert added_plan.id == "custom-id"

    def test_create_plan_duplicate_name_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        existing = MagicMock(spec=Plan)
        _make_query_chain(session, existing)  # get_by_name returns existing

        with pytest.raises(PlanAlreadyExistsError, match="already exists"):
            repo.create(name="growth", display_name="Growth")

    def test_create_plan_duplicate_id_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)

        # get_by_name returns None, but get_by_id returns existing
        chain = _make_query_chain(session, None)
        call_count = [0]
        original_first = chain.first

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # get_by_name
            return MagicMock(spec=Plan)  # get_by_id

        chain.first.side_effect = first_side_effect

        with pytest.raises(PlanAlreadyExistsError, match="already exists"):
            repo.create(name="growth", display_name="Growth", plan_id="existing-id")

    @patch("src.repositories.plans_repo.logger")
    def test_create_plan_integrity_error_raises_plan_already_exists(self, mock_logger):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)
        session.flush.side_effect = IntegrityError("dup", {}, None)

        with pytest.raises(PlanAlreadyExistsError, match="Plan creation failed"):
            repo.create(name="growth", display_name="Growth")

        session.rollback.assert_called_once()
        mock_logger.error.assert_called_once()


class TestPlansRepositoryUpdate:
    """Tests for PlansRepository.update."""

    def test_update_plan_success(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        plan.name = "growth"

        chain = _make_query_chain(session, plan)

        result = repo.update("plan-growth", display_name="Growth Plus")
        assert result is plan
        assert plan.display_name == "Growth Plus"
        session.flush.assert_called_once()

    def test_update_plan_not_found_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        with pytest.raises(PlanNotFoundError, match="Plan not found"):
            repo.update("missing")

    def test_update_plan_name_conflict_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)

        plan = MagicMock(spec=Plan)
        plan.name = "growth"

        # First call returns the plan (get_by_id), second returns conflict (get_by_name)
        chain = _make_query_chain(session)
        call_count = [0]

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return plan  # get_by_id
            return MagicMock(spec=Plan)  # get_by_name — conflict

        chain.first.side_effect = first_side_effect

        with pytest.raises(PlanAlreadyExistsError, match="already exists"):
            repo.update("plan-growth", name="pro")

    def test_update_plan_partial_fields(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        plan.name = "growth"
        plan.price_monthly_cents = 2900

        _make_query_chain(session, plan)

        result = repo.update("plan-growth", price_monthly_cents=3900)
        assert plan.price_monthly_cents == 3900
        session.flush.assert_called_once()

    def test_update_plan_is_active(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        plan.name = "growth"
        plan.is_active = True

        _make_query_chain(session, plan)

        result = repo.update("plan-growth", is_active=False)
        assert plan.is_active is False


class TestPlansRepositoryDelete:
    """Tests for PlansRepository.delete."""

    def test_delete_plan_success(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        _make_query_chain(session, plan)

        result = repo.delete("plan-growth")
        assert result is True
        session.delete.assert_called_once_with(plan)
        session.flush.assert_called_once()

    def test_delete_plan_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.delete("missing")
        assert result is False
        session.delete.assert_not_called()


class TestPlansRepositoryFeatureCRUD:
    """Tests for PlanFeature CRUD operations."""

    def test_get_features(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        features = [MagicMock(spec=PlanFeature), MagicMock(spec=PlanFeature)]
        chain = _make_query_chain(session)
        chain.all.return_value = features

        result = repo.get_features("plan-growth")
        assert result == features

    def test_get_feature_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        feature = MagicMock(spec=PlanFeature)
        _make_query_chain(session, feature)

        result = repo.get_feature("plan-growth", "ai_insights")
        assert result is feature

    def test_get_feature_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.get_feature("plan-growth", "nonexistent")
        assert result is None

    def test_add_feature_to_plan(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)

        # First call: get_by_id returns plan, second: get_feature returns None (no existing)
        chain = _make_query_chain(session)
        call_count = [0]

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return plan  # plan exists
            return None  # feature doesn't exist yet

        chain.first.side_effect = first_side_effect

        result = repo.add_feature("plan-growth", "ai_insights", is_enabled=True, limit_value=100)
        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_add_feature_updates_existing(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        existing_feature = MagicMock(spec=PlanFeature)

        chain = _make_query_chain(session)
        call_count = [0]

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return plan  # plan exists
            return existing_feature  # feature already exists

        chain.first.side_effect = first_side_effect

        result = repo.add_feature("plan-growth", "ai_insights", is_enabled=False, limit_value=50)
        assert existing_feature.is_enabled is False
        assert existing_feature.limit_value == 50
        # Should NOT call session.add for existing feature — just flush
        session.add.assert_not_called()
        session.flush.assert_called_once()

    def test_add_feature_plan_not_found_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)  # plan not found

        with pytest.raises(PlanNotFoundError, match="Plan not found"):
            repo.add_feature("missing", "ai_insights")

    def test_update_feature_success(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        feature = MagicMock(spec=PlanFeature)
        _make_query_chain(session, feature)

        result = repo.update_feature("plan-growth", "ai_insights", is_enabled=False, limit_value=200)
        assert result is feature
        assert feature.is_enabled is False
        assert feature.limit_value == 200
        session.flush.assert_called_once()

    def test_update_feature_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.update_feature("plan-growth", "nonexistent")
        assert result is None

    def test_update_feature_partial_fields(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        feature = MagicMock(spec=PlanFeature)
        feature.is_enabled = True
        feature.limit_value = 100
        _make_query_chain(session, feature)

        # Only update limit_value, leave is_enabled unchanged
        result = repo.update_feature("plan-growth", "ai_insights", limit_value=500)
        assert feature.limit_value == 500
        # is_enabled should NOT have been reassigned (None check in code)

    def test_update_feature_with_limits_dict(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        feature = MagicMock(spec=PlanFeature)
        _make_query_chain(session, feature)

        limits = {"max_queries": 1000, "max_dashboards": 5}
        result = repo.update_feature("plan-growth", "ai_insights", limits=limits)
        assert feature.limits == limits

    def test_remove_feature_success(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        feature = MagicMock(spec=PlanFeature)
        _make_query_chain(session, feature)

        result = repo.remove_feature("plan-growth", "ai_insights")
        assert result is True
        session.delete.assert_called_once_with(feature)
        session.flush.assert_called_once()

    def test_remove_feature_not_found(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        result = repo.remove_feature("plan-growth", "nonexistent")
        assert result is False
        session.delete.assert_not_called()


class TestPlansRepositorySetFeatures:
    """Tests for set_features (replace all)."""

    def test_set_features_replaces_all(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)

        # get_by_id returns the plan
        chain = _make_query_chain(session, plan)

        features_data = [
            {"feature_key": "ai_insights", "is_enabled": True, "limit_value": 100},
            {"feature_key": "custom_reports", "is_enabled": False},
        ]

        result = repo.set_features("plan-growth", features_data)
        assert len(result) == 2

        # Should delete existing features
        chain.delete.assert_called_once()
        # Should add two new features
        assert session.add.call_count == 2
        session.flush.assert_called_once()

    def test_set_features_plan_not_found_raises(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        _make_query_chain(session, None)

        with pytest.raises(PlanNotFoundError, match="Plan not found"):
            repo.set_features("missing", [{"feature_key": "ai_insights"}])

    def test_set_features_empty_list_clears_all(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        chain = _make_query_chain(session, plan)

        result = repo.set_features("plan-growth", [])
        assert result == []
        chain.delete.assert_called_once()
        session.add.assert_not_called()

    def test_set_features_uses_defaults_for_optional_fields(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        plan = MagicMock(spec=Plan)
        chain = _make_query_chain(session, plan)

        result = repo.set_features("plan-growth", [{"feature_key": "ai_insights"}])
        assert len(result) == 1
        created = session.add.call_args[0][0]
        assert created.feature_key == "ai_insights"
        assert created.is_enabled is True  # default
        assert created.limit_value is None  # default


class TestPlansRepositoryCount:
    """Tests for PlansRepository.count."""

    def test_count_active_only(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)
        chain.count.return_value = 3

        result = repo.count()
        assert result == 3
        chain.filter.assert_called_once()  # is_active filter

    def test_count_include_inactive(self):
        session = MagicMock(spec=Session)
        repo = PlansRepository(session)
        chain = _make_query_chain(session)
        chain.count.return_value = 5

        result = repo.count(include_inactive=True)
        assert result == 5
        chain.filter.assert_not_called()
