"""
Comment database model.

Represents a user review/comment on an application with sentiment analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.app import App
    from app.db.models.comment_aspect import CommentAspect


class Comment(BaseMixin, Base):
    """Represents a user review/comment on an application.

    Attributes:
        app_id: Foreign key to the associated app.
        review_id: External review ID (optional, for source tracking).
        type: Type/category of the comment.
        author_type: Type of author (e.g., 'user', 'bot').
        author_name: Name of the comment author.
        rating: Rating given with the comment (1-5 stars).
        content: The actual comment text.
        overall_sentiment: Overall sentiment of the comment.
        absa_status: Aspect-Based Sentiment Analysis status.
        bot_reply_status: Status of bot reply generation.
        app_version: App version the comment refers to.
        source_review_id: Original review ID from source platform.
        app: Relationship to the associated App.
        aspects: Relationship to associated CommentAspect entries.
    """

    __tablename__ = "comments"

    app_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    author_type: Mapped[str] = mapped_column(String(64), default="user", nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    overall_sentiment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    absa_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    bot_reply_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_review_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Relationships
    app: Mapped[App] = relationship(
        "App",
        back_populates="comments",
    )
    aspects: Mapped[list[CommentAspect]] = relationship(
        "CommentAspect",
        back_populates="comment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Comment id={self.id} app_id={self.app_id} rating={self.rating}>"
