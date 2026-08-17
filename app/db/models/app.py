"""
App database model.

Represents a mobile application with its metadata and ratings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.comment import Comment
    from app.db.models.ticket_proposal import TicketProposal


class App(BaseMixin, Base):
    """Represents a mobile application.

    Attributes:
        package_name: Unique package name of the app (e.g., com.example.app).
        name: Display name of the application.
        icon_url: URL to the app's icon image.
        avg_rating: Average rating of the app (0-5).
        rating_count: Total number of ratings received.
        comments: Relationship to associated comments/reviews.
    """

    __tablename__ = "apps"

    package_name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), default=0, nullable=True)
    rating_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)

    # Relationships
    comments: Mapped[list[Comment]] = relationship(
        "Comment",
        back_populates="app",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ticket_proposals: Mapped[list[TicketProposal]] = relationship(
        "TicketProposal",
        back_populates="app",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<App id={self.id} package_name='{self.package_name}' name='{self.name}'>"
