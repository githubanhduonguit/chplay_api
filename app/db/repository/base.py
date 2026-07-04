"""
Base repository with generic CRUD operations.

Provides a reusable base class for all repositories with common
async CRUD methods. Specific repositories extend this class.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic base repository with common CRUD operations.

    Args:
        model: The SQLAlchemy model class this repository manages.
        session: An async SQLAlchemy session.
    """

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def create(self, **kwargs: Any) -> ModelT:
        """Create a new record.

        Args:
            **kwargs: Field values for the new record.

        Returns:
            The created model instance.
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, id: int) -> ModelT | None:
        """Get a record by its primary key.

        Args:
            id: The primary key value.

        Returns:
            The model instance if found, otherwise None.
        """
        return await self.session.get(self.model, id)

    async def get_many(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
    ) -> list[ModelT]:
        """Get multiple records with optional filtering and pagination.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            filters: Key-value pairs to filter by (e.g., {"status": "active"}).
            order_by: Column name to order by.
            descending: Whether to sort in descending order.

        Returns:
            A list of model instances.
        """
        stmt: Select = select(self.model).offset(skip).limit(limit)

        if filters:
            for key, value in filters.items():
                column = getattr(self.model, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)

        if order_by:
            column = getattr(self.model, order_by, None)
            if column is not None:
                stmt = stmt.order_by(column.desc() if descending else column.asc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, id: int, **kwargs: Any) -> ModelT | None:
        """Update a record by its primary key.

        Args:
            id: The primary key value.
            **kwargs: Field values to update.

        Returns:
            The updated model instance if found, otherwise None.
        """
        instance = await self.get(id)
        if instance is None:
            return None

        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        await self.session.flush()
        return instance

    async def delete(self, id: int) -> bool:
        """Delete a record by its primary key.

        Args:
            id: The primary key value.

        Returns:
            True if the record was deleted, False if not found.
        """
        instance = await self.get(id)
        if instance is None:
            return False

        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records with optional filters.

        Args:
            filters: Key-value pairs to filter by.

        Returns:
            The total count of matching records.
        """
        stmt = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                column = getattr(self.model, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)

        result = await self.session.execute(stmt)
        return result.scalar_one()
