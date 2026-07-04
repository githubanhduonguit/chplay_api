"""
Document repository with document-specific queries.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.document import Document
from app.db.repository.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document model with document-specific queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Document, session)

    async def get_with_chunks(self, id: int) -> Document | None:
        """Get a document with its chunks eagerly loaded.

        Args:
            id: The document ID.

        Returns:
            The document with chunks if found, otherwise None.
        """
        stmt = (
            select(Document)
            .where(Document.id == id)
            .options(selectinload(Document.chunks))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_status(self, status: str) -> list[Document]:
        """Get all documents with a given status.

        Args:
            status: The status to filter by (e.g., "uploaded", "indexed").

        Returns:
            A list of matching documents.
        """
        stmt = select(Document).where(Document.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_filename(self, query: str, limit: int = 20) -> list[Document]:
        """Search documents by filename (case-insensitive).

        Args:
            query: The filename search query.
            limit: Maximum number of results to return.

        Returns:
            A list of matching documents.
        """
        stmt = (
            select(Document)
            .where(Document.filename.ilike(f"%{query}%"))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        id: int,
        status: str,
        error_message: str | None = None,
    ) -> Document | None:
        """Update the processing status of a document.

        Args:
            id: The document ID.
            status: The new status value.
            error_message: Optional error message if the status is "failed".

        Returns:
            The updated document if found, otherwise None.
        """
        return await self.update(
            id,
            status=status,
            error_message=error_message,
        )
