"""Service for app-related operations."""

import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import App, Comment
from app.schemas import (
    AuthorSchema,
    ReviewSchema,
    GetReviewsResponseSchema,
    RatingSchema,
    DeveloperSchema,
    AppDetailSchema,
)

logger = logging.getLogger(__name__)


class AppService:
    """Service for handling app operations."""

    def __init__(self, db: AsyncSession):
        """Initialize service with async database session."""
        self.db = db

    async def get_app_detail(self, package_name: str) -> AppDetailSchema:
        """Get detailed information for an app by package_name.

        Args:
            package_name: The app's package name (e.g., com.vnpt.vnpttoken.vneid).

        Returns:
            AppDetailSchema with app information.

        Raises:
            HTTPException: If app not found (404) or database error (500).
        """
        try:
            logger.info(f"Searching for app with package_name: {package_name}")
            stmt = select(App).where(App.package_name == package_name)
            result = await self.db.execute(stmt)
            app = result.scalars().first()

            if not app:
                logger.warning(f"App not found: {package_name}")
                raise HTTPException(status_code=404, detail="App not found")

            logger.info(f"Found app: {app.id}")

            # Build rating schema
            rating = RatingSchema(
                average=float(app.avg_rating) if app.avg_rating else 0.0,
                count=app.rating_count or 0,
            )


            # Build app detail response
            app_detail = AppDetailSchema(
                id=app.id,
                packageName=app.package_name,
                name=app.name,
                icon=app.icon_url,
                rating=rating,
                createdAt=app.created_at,
            )

            logger.info(f"Successfully retrieved app detail for: {package_name}")
            return app_detail

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_app_detail: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}",
            )

    async def get_reviews(
        self, package_name: str, page: int = 1, page_size: int = 20
    ) -> GetReviewsResponseSchema:
        """Get reviews and comments for an app by package_name.

        Args:
            package_name: The app's package name (e.g., com.example.app).
            page: Page number for pagination (1-indexed).
            page_size: Number of items per page.

        Returns:
            GetReviewsResponseSchema with reviews and comments separated.

        Raises:
            HTTPException: If app not found (404) or database error (500).
        """
        try:
            # Find app
            logger.info(f"Searching for app with package_name: {package_name}")
            stmt = select(App.id).where(App.package_name == package_name)
            result = await self.db.execute(stmt)
            app_id = result.scalar()

            if not app_id:
                logger.warning(f"App not found: {package_name}")
                raise HTTPException(status_code=404, detail="App not found")

            logger.info(f"Found app: {app_id}")

            # Get total count
            logger.info(f"Fetching comment count for app_id: {app_id}")
            count_stmt = select(func.count()).select_from(Comment).where(Comment.app_id == app_id)
            count_result = await self.db.execute(count_stmt)
            total = count_result.scalar()
            logger.info(f"Total comments: {total}")

            # Get paginated comments
            logger.info(f"Fetching comments - page: {page}, page_size: {page_size}")
            offset = (page - 1) * page_size
            comments_stmt = (
                select(Comment)
                .where(Comment.app_id == app_id)
                .order_by(Comment.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            comments_result = await self.db.execute(comments_stmt)
            comments = comments_result.scalars().all()
            logger.info(f"Fetched {len(comments)} comments")

            # Separate reviews (has rating) and comments (no rating)
            reviews = []
            comment_list = []

            for comment in comments:
                try:
                    author = AuthorSchema(
                        type=comment.author_type,
                        name=comment.author_name,
                        avatar=(
                            f"https://ui-avatars.com/api/?name={comment.author_name}"
                            if comment.author_type == "user"
                            else None
                        ),
                    )

                    review_item = ReviewSchema(
                        id=comment.id,
                        reviewId=comment.review_id,
                        type="review" if comment.rating is not None else "comment",
                        author=author,
                        rating=comment.rating,
                        content=comment.content,
                        createdAt=comment.created_at,
                        absaStatus=comment.absa_status,
                        botReplyStatus=comment.bot_reply_status,
                    )

                    if comment.rating is not None:
                        reviews.append(review_item)
                    elif comment.review_id is not None:
                        comment_list.append(review_item)
                except Exception as e:
                    logger.error(f"Error processing comment {comment.id}: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error processing comment {comment.id}: {str(e)}",
                    )

            logger.info(f"Processed {len(reviews)} reviews and {len(comment_list)} comments")

            return GetReviewsResponseSchema(
                total=total,
                page=page,
                pageSize=page_size,
                reviews=reviews,
                comments=comment_list,
            )

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_reviews: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}",
            )
