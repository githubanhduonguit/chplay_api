"""
Document database model.

Represents an uploaded document with its metadata,
versioning, and processing status.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin


class Document(BaseMixin, Base):
    """Represents an uploaded document.

    Attributes:
        filename: Original name of the uploaded file.
        file_path: Path where the file is stored on disk.
        mime_type: MIME type of the file.
        size: File size in bytes.
        version: Current version number of the document.
        metadata: Arbitrary JSON metadata attached to the document.
        status: Processing status (uploaded, processing, indexed, failed).
        chunks: Relationship to associated document chunks.
    """

    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=dict)
    status: Mapped[str] = mapped_column(
        String(32),
        default="uploaded",
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename='{self.filename}' version={self.version}>"
