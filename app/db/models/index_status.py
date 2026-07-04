"""
Index status model.

Tracks the status of different indices (vector, BM25) for
monitoring and rebuilding purposes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseMixin


class IndexStatus(BaseMixin, Base):
    """Tracks the status of an index (vector or BM25).

    Attributes:
        index_type: Type of index (vector, bm25).
        status: Current status (building, ready, failed).
        error_message: Error details if the build failed.
        last_synced: Timestamp of the last successful sync.
    """

    __tablename__ = "index_status"

    index_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IndexStatus id={self.id} "
            f"type='{self.index_type}' "
            f"status='{self.status}'>"
        )
