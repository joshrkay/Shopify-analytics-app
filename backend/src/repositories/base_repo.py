"""Base repository with mandatory per-tenant query scoping. All operations are automatically bound to the tenant set at construction time."""

import logging
from typing import TypeVar, Generic, Optional, List
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.db_base import Base
from src.platform.errors import TenantIsolationError  # noqa: F401 — re-exported for callers

logger = logging.getLogger(__name__)

# Type variable for repository models
T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T], ABC):
    """Base repository. All queries are automatically scoped to the tenant supplied at construction."""

    def __init__(self, db_session: Session, tenant_id: str):
        """Bind repository to a specific tenant. tenant_id must come from JWT, never from request body."""
        if not tenant_id:
            raise ValueError("tenant_id is required and cannot be empty")

        self.db_session = db_session
        self.tenant_id = tenant_id
        self._model_class = self._get_model_class()

    @abstractmethod
    def _get_model_class(self) -> type[T]:
        """Return the SQLAlchemy model class for this repository."""
        pass

    @abstractmethod
    def _get_tenant_column_name(self) -> str:
        """Return the name of the tenant_id column in the model."""
        pass

    def _enforce_tenant_scope(self, query):
        """Scope a query to the repository's tenant."""
        tenant_column = getattr(self._model_class, self._get_tenant_column_name())
        return query.filter(tenant_column == self.tenant_id)

    def get_by_id(self, entity_id: str) -> Optional[T]:
        query = self.db_session.query(self._model_class)
        query = self._enforce_tenant_scope(query)
        return query.filter(self._model_class.id == entity_id).first()

    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[T]:
        query = self.db_session.query(self._model_class)
        query = self._enforce_tenant_scope(query)
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        return query.all()

    def create(self, entity_data: dict) -> T:
        """Create entity. Any tenant_id in entity_data is stripped and replaced with the repo's bound tenant_id."""
        # SECURITY: tenant_id MUST come from JWT context, never from request body.
        if "tenant_id" in entity_data:
            logger.warning(
                "tenant_id found in entity_data and stripped",
                extra={"repository_tenant_id": self.tenant_id},
            )
            entity_data.pop("tenant_id")

        entity_data[self._get_tenant_column_name()] = self.tenant_id
        entity = self._model_class(**entity_data)
        self.db_session.add(entity)

        try:
            self.db_session.commit()
            self.db_session.refresh(entity)
            logger.info(
                "Entity created",
                extra={
                    "tenant_id": self.tenant_id,
                    "entity_id": getattr(entity, "id", None),
                    "entity_type": self._model_class.__name__,
                },
            )
            return entity
        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error("Failed to create entity", extra={"tenant_id": self.tenant_id, "error": str(e)})
            raise

    def update(self, entity_id: str, entity_data: dict) -> Optional[T]:
        """Update entity fields. tenant_id in entity_data is stripped before applying."""
        # Strip any attempt to change the tenant columns.
        entity_data.pop("tenant_id", None)
        entity_data.pop(self._get_tenant_column_name(), None)

        entity = self.get_by_id(entity_id)
        if not entity:
            return None

        for key, value in entity_data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        try:
            self.db_session.commit()
            self.db_session.refresh(entity)
            logger.info(
                "Entity updated",
                extra={
                    "tenant_id": self.tenant_id,
                    "entity_id": entity_id,
                    "entity_type": self._model_class.__name__,
                },
            )
            return entity
        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "Failed to update entity",
                extra={"tenant_id": self.tenant_id, "entity_id": entity_id, "error": str(e)},
            )
            raise

    def delete(self, entity_id: str) -> bool:
        """Delete entity. Returns True if found and deleted, False if not found."""
        entity = self.get_by_id(entity_id)
        if not entity:
            return False

        try:
            self.db_session.delete(entity)
            self.db_session.commit()
            logger.info(
                "Entity deleted",
                extra={
                    "tenant_id": self.tenant_id,
                    "entity_id": entity_id,
                    "entity_type": self._model_class.__name__,
                },
            )
            return True
        except SQLAlchemyError as e:
            self.db_session.rollback()
            logger.error(
                "Failed to delete entity",
                extra={"tenant_id": self.tenant_id, "entity_id": entity_id, "error": str(e)},
            )
            raise

    def count(self) -> int:
        query = self.db_session.query(self._model_class)
        query = self._enforce_tenant_scope(query)
        return query.count()

    def exists(self, entity_id: str) -> bool:
        return self.get_by_id(entity_id) is not None
