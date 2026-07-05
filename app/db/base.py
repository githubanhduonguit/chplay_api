"""
SQLAlchemy declarative base and common mixins.

Provides a base class for all models and a mixin with common
timestamp columns (id, created_at, updated_at).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base class for all database models."""


class BaseMixin:
    """Mixin providing common columns for all models.

    Attributes:
        id: Primary key (auto-increment integer).
        created_at: Timestamp of record creation.
        updated_at: Timestamp of last record update.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    # updated_at: Mapped[datetime | None] = mapped_column(
    #     DateTime(timezone=True),
    #     default=lambda: datetime.now(timezone.utc),
    #     onupdate=lambda: datetime.now(timezone.utc),
    #     nullable=True,
    # )
