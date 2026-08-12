"""Repository for Comment model operations.

Provides methods for reading pending reviews, creating bot replies,
and updating bot reply statuses.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, func
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

    async def get_pending_bot_reply_reviews(self, limit: int = 20) -> list[Comment]:
        """Get reviews that are pending bot reply generation.

        Filters:
            - type == "review"
            - author_type == "user"
            - bot_reply_status == "pending"

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
                & (Comment.author_type == "user")
                & (Comment.bot_reply_status == "pending")
            )
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_label_comments(self, limit: int = 100) -> list[Comment]:
        """Get comments that are pending aspect-based sentiment labeling.

        Filters:
            - absa_status == "pending"

        Ordered by created_at ascending (oldest first) for stable processing.

        Args:
            limit: Maximum number of comments to return.

        Returns:
            A list of Comment instances matching the criteria.
        """
        stmt = (
            select(Comment)
            .where(Comment.absa_status == "pending")
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
