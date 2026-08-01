"""
Comment aspect database model.

Represents aspect-based sentiment analysis results for a comment.
Stores detected aspects, their sentiments, and confidence scores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.comment import Comment


class CommentAspect(BaseMixin, Base):
    """Represents aspect-based sentiment analysis for a comment.

    Aspect-Based Sentiment Analysis (ABSA) breaks down a comment into
    distinct aspects (e.g., "battery", "camera", "performance") and
    analyzes the sentiment expressed toward each aspect individually.

    Attributes:
        comment_id: Foreign key to the associated comment.
        aspect: The aspect being analyzed (e.g., "battery", "camera").
        sentiment: The sentiment toward this aspect (positive, negative, neutral).
        confidence_score: Confidence level of the sentiment classification.
        model_version: Version of the ML model that performed the analysis.
        comment: Relationship to the associated Comment.
    """

    __tablename__ = "comment_aspects"

    comment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aspect: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    sentiment: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Relationships
    comment: Mapped[Comment] = relationship(
        "Comment",
        back_populates="aspects",
    )

    def __repr__(self) -> str:
        return f"<CommentAspect id={self.id} aspect='{self.aspect}' sentiment='{self.sentiment}'>"
