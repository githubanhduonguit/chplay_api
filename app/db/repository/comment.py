"""Repository for Comment model operations.

Provides methods for reading pending reviews, creating bot replies,
and updating bot reply statuses.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.comment import Comment
from app.db.repository.base import BaseRepository

logger = logging.getLogger(__name__)


class CommentRepository(BaseRepository[Comment]):
    """Repository for Comment model with review-reply-specific operations.

    Args:
        session: An async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Comment, session)

    async def get_pending_bot_reply_reviews(
        self, limit: int = 20, include_stale: bool = False
    ) -> list[Comment]:
        """Get reviews that are pending bot reply generation.

        Filters:
            - type == "review"
            - author_type == "user"
            - bot_reply_status == "pending"

        With ``include_stale=True`` also returns retry candidates:
            - bot_reply_status == "failed"
            - bot_reply_status == "processing" stuck longer than 30 minutes
              (approximated with ``created_at`` since the model has no
              ``updated_at`` column)

        Ordered by created_at ascending (oldest first) for stable processing.

        Args:
            limit: Maximum number of reviews to return.
            include_stale: If True, also include failed and stuck-processing
                reviews for retry. Defaults to False (keeps current behavior).

        Returns:
            A list of Comment instances matching the criteria.
        """
        if include_stale:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            status_filter = or_(
                Comment.bot_reply_status == "pending",
                Comment.bot_reply_status == "failed",
                and_(
                    Comment.bot_reply_status == "processing",
                    Comment.created_at < stale_cutoff,
                ),
            )
        else:
            status_filter = Comment.bot_reply_status == "pending"

        stmt = (
            select(Comment)
            .where(
                (Comment.type == "review")
                & (Comment.author_type == "user")
                & status_filter
            )
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_label_comments(self, limit: int = 100) -> list[Comment]:
        """Get reviews that are pending aspect-based sentiment labeling.

        Only top-level reviews are labeled — comments (e.g. user replies
        and bot replies, type == "comment") are excluded.

        Filters:
            - type == "review"
            - absa_status == "pending"

        Ordered by created_at ascending (oldest first) for stable processing.

        Args:
            limit: Maximum number of reviews to return.

        Returns:
            A list of Comment instances matching the criteria.
        """
        stmt = (
            select(Comment)
            .where(
                (Comment.type == "review")
                & (Comment.absa_status == "pending")
            )
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_bot_reply_status(
        self, comment_id: int, status: str
    ) -> Comment | None:
        """Update the bot_reply_status of a comment.

        Valid statuses: pending, processing, completed, failed.

        Args:
            comment_id: The ID of the comment to update.
            status: The new bot_reply_status value.

        Returns:
            The updated Comment if found, otherwise None.
        """
        valid_statuses = {"pending", "processing", "completed", "failed"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid bot_reply_status '{status}'. "
                f"Must be one of: {', '.join(sorted(valid_statuses))}"
            )

        return await self.update(comment_id, bot_reply_status=status)

    async def has_bot_reply_for_review(self, review_id: int) -> bool:
        """Check if a bot reply already exists for a given review.

        Args:
            review_id: The ID of the parent review.

        Returns:
            True if a bot reply already exists, False otherwise.
        """
        stmt = (
            select(func.count())
            .select_from(Comment)
            .where(
                (Comment.review_parent_id == review_id)
                & (Comment.author_type == "bot")
            )
        )
        result = await self.session.execute(stmt)
        count: int = result.scalar_one()
        return count > 0

    async def create_bot_reply(
        self, review: Comment, content: str
    ) -> Comment:
        """Create a bot reply comment for a given review.

        The bot reply is linked to the review via review_parent_id.

        Args:
            review: The parent review Comment instance.
            content: The generated reply content.

        Returns:
            The newly created bot reply Comment instance.
        """
        bot_reply = Comment(
            app_id=review.app_id,
            review_parent_id=review.id,
            type="comment",
            author_type="bot",
            author_name="Trợ lý AI",
            rating=None,
            content=content,
            bot_reply_status="completed",
        )
        self.session.add(bot_reply)
        await self.session.flush()
        return bot_reply

    async def get_negative_labeled_reviews(
        self,
        limit: int = 100,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Comment]:
        """Get labeled negative reviews from users.

        Filters:
            - type == "review"
            - author_type == "user"
            - absa_status == "completed"
            - rating <= 3
            - created_at within (from_date, to_date) if provided

        Ordered by created_at ascending (oldest first) for stable processing.

        Args:
            limit: Maximum number of reviews to return.
            from_date: Only reviews created on/after this date.
            to_date: Only reviews created on/before this date.

        Returns:
            A list of Comment instances matching the criteria.
        """
        stmt = (
            select(Comment)
            .where(
                (Comment.type == "review")
                & (Comment.author_type == "user")
                & (Comment.absa_status == "completed")
                & (Comment.rating <= 3)
            )
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        if from_date is not None:
            stmt = stmt.where(Comment.created_at >= from_date)
        if to_date is not None:
            stmt = stmt.where(Comment.created_at <= to_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
