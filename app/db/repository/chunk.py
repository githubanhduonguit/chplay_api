"""
Chunk repository with chunk-specific queries.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import DocumentChunk
from app.db.repository.base import BaseRepository


class ChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for DocumentChunk model with chunk-specific queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(DocumentChunk, session)

    async def get_by_document_id(self, document_id: int) -> list[DocumentChunk]:
        """Get all chunks for a given document.

        Args:
            document_id: The parent document ID.

        Returns:
            A list of chunks ordered by chunk_index.
        """
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_document_id(self, document_id: int) -> int:
        """Delete all chunks for a given document.

        Args:
            document_id: The parent document ID.

        Returns:
            The number of deleted chunks.
        """
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        result = await self.session.execute(stmt)
        chunks = list(result.scalars().all())
        for chunk in chunks:
            await self.session.delete(chunk)
        await self.session.flush()
        return len(chunks)

    async def bulk_create(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[DocumentChunk]:
        """Create multiple chunks in bulk.

        Args:
            chunks: List of dictionaries with chunk field values.

        Returns:
            A list of created DocumentChunk instances.
        """
        instances = [DocumentChunk(**chunk) for chunk in chunks]
        self.session.add_all(instances)
        await self.session.flush()
        return instances
