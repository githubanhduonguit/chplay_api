"""
Document chunk and metadata database models.

Represents a single chunk of text extracted from a document,
along with its embedding vector and associated metadata key-value pairs.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.document import Document


class DocumentChunk(BaseMixin, Base):
    """Represents a single chunk of text from a document.

    Attributes:
        document_id: Foreign key to the parent document.
        chunk_index: Zero-based index of this chunk within the document.
        content: The text content of this chunk.
        embedding: Vector embedding of the chunk content (optional, populated after processing).
        metadata: Arbitrary JSON metadata for this chunk.
        document: Relationship to the parent Document.
        metadata_entries: Relationship to associated ChunkMetadata key-value pairs.
    """

    __tablename__ = "document_chunks"

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),  # match EMBEDDING_DIMENSION
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=dict)

    # Relationships
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
    )
    metadata_entries: Mapped[list[ChunkMetadata]] = relationship(
        "ChunkMetadata",
        back_populates="chunk",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} "
            f"document_id={self.document_id} "
            f"index={self.chunk_index}>"
        )


class ChunkMetadata(BaseMixin, Base):
    """Key-value metadata entries associated with a document chunk.

    Attributes:
        chunk_id: Foreign key to the parent DocumentChunk.
        key: Metadata key name.
        value: Metadata value.
        chunk: Relationship to the parent DocumentChunk.
    """

    __tablename__ = "chunk_metadata"

    chunk_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    chunk: Mapped[DocumentChunk] = relationship(
        "DocumentChunk",
        back_populates="metadata_entries",
    )

    def __repr__(self) -> str:
        return f"<ChunkMetadata id={self.id} key='{self.key}'>"
