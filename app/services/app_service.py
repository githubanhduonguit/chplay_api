"""Service for app-related operations."""

import logging
from datetime import datetime
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import App, Comment
from app.schemas import (
    AspectSchema,
    AuthorSchema,
    ReviewSchema,
    GetReviewsResponseSchema,
    RatingSchema,
    DeveloperSchema,
    AppDetailSchema,
    CreateReviewRequest,
    CreateCommentRequest,
    CommentResponseSchema,
)
from app.services.queue.queue import review_job_queue
from app.services.queue.schemas import ReviewJob

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

                    # Build aspect-level labels from CommentAspect rows
                    # (one entry per detected aspect).
                    aspects = [
                        AspectSchema(
                            topic_l1=aspect.topic_l1,
                            topic_l2=aspect.topic_l2,
                            sentiment=aspect.sentiment,
                            confidence=(
                                float(aspect.confidence_score)
                                if aspect.confidence_score is not None
                                else None
                            ),
                        )
                        for aspect in comment.aspects
                    ]

                    review_item = ReviewSchema(
                        id=comment.id,
                        author=author,
                        reviewId=comment.review_parent_id,
                        rating=comment.rating,
                        content=comment.content,
                        createdAt=comment.created_at,
                        absaStatus=comment.absa_status,
                        botReplyStatus=comment.bot_reply_status,
                        labels=aspects,
                    )

                    if comment.rating is not None:
                        reviews.append(review_item)
                    elif comment.review_parent_id is not None:
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

    async def create_review(
        self,
        package_name: str,
        request: CreateReviewRequest,
    ) -> CommentResponseSchema:
        """Create a new review for an app.

        Args:
            package_name: The app's package name.
            request: Review creation request with authorName, rating, content.

        Returns:
            CommentResponseSchema with created review data.

        Raises:
            HTTPException: If app not found (404) or database error (500).
        """
        try:
            logger.info(f"Creating review for app: {package_name}")

            # Find app
            stmt = select(App).where(App.package_name == package_name)
            result = await self.db.execute(stmt)
            app = result.scalars().first()

            if not app:
                logger.warning(f"App not found: {package_name}")
                raise HTTPException(status_code=404, detail="App not found")

            logger.info(f"Creating review for app_id: {app.id}")

            # Create comment record (review is a type of comment).
            # The id is auto-generated by the DB sequence so that other
            # inserts (e.g. bot replies) never collide with manual ids.
            comment = Comment(
                app_id=app.id,
                review_parent_id=None,
                type="review",
                author_type="user",
                author_name=request.authorName,
                rating=request.rating,
                content=request.content,
                absa_status="pending",
                bot_reply_status="pending",
                created_at=datetime.utcnow(),
            )

            self.db.add(comment)
            await self.db.flush()  # Flush to get the ID
            await self.db.commit()

            logger.info(f"Review created with id: {comment.id}")

            # Enqueue review job for bot reply generation (best-effort:
            # a queue failure must not fail the API since the review is
            # already persisted with bot_reply_status='pending').
            try:
                job = ReviewJob(
                    review_id=comment.id,
                    app_id=comment.app_id,
                    created_at=comment.created_at,
                )
                await review_job_queue.enqueue(job)
                logger.info(
                    "Enqueued review job for review %s (queue size=%s)",
                    comment.id,
                    review_job_queue.size(),
                )
            except Exception as e:
                logger.warning(
                    "Failed to enqueue review job for review %s: %s",
                    comment.id,
                    str(e),
                    exc_info=True,
                )

            # Return response
            return CommentResponseSchema(
                id=comment.id,
                appId=comment.app_id,
                reviewId=comment.review_parent_id,
                rating=comment.rating,
                content=comment.content,
                type=comment.type,
                authorType=comment.author_type,
                botReplyStatus=comment.bot_reply_status,
                createdAt=comment.created_at,
            )

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Unexpected error in create_review: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}",
            )

    async def create_comment(
        self,
        package_name: str,
        review_id: int,
        request: CreateCommentRequest,
    ) -> CommentResponseSchema:
        """Create a new comment on a review.

        Args:
            package_name: The app's package name.
            review_id: ID of the parent review.
            request: Comment creation request with authorName, content.

        Returns:
            CommentResponseSchema with created comment data.

        Raises:
            HTTPException: If app or review not found (404) or database error (500).
        """
        try:
            logger.info(f"Creating comment for review {review_id} on app: {package_name}")

            # Find app
            app_stmt = select(App).where(App.package_name == package_name)
            app_result = await self.db.execute(app_stmt)
            app = app_result.scalars().first()

            if not app:
                logger.warning(f"App not found: {package_name}")
                raise HTTPException(status_code=404, detail="App not found")

            # Find review (parent comment)
            review_stmt = select(Comment).where(
                (Comment.id == review_id) & (Comment.app_id == app.id)
            )
            review_result = await self.db.execute(review_stmt)
            review = review_result.scalars().first()

            if not review:
                logger.warning(f"Review {review_id} not found for app {package_name}")
                raise HTTPException(status_code=404, detail="Review not found")

            logger.info(f"Creating comment on review {review_id} for app_id: {app.id}")

            # Create comment record (id auto-generated by the DB sequence
            # to avoid collisions with other inserts, e.g. bot replies).
            comment = Comment(
                app_id=app.id,
                review_parent_id=review_id,
                type="comment",
                author_type="user",
                author_name=request.authorName,
                rating=None,  # Comments don't have ratings
                content=request.content,
                created_at=datetime.utcnow(),
            )

            self.db.add(comment)
            await self.db.flush()  # Flush to get the ID
            await self.db.commit()

            logger.info(f"Comment created with id: {comment.id}")

            # Return response
            return CommentResponseSchema(
                id=comment.id,
                appId=comment.app_id,
                reviewId=comment.review_parent_id,
                rating=comment.rating,
                content=comment.content,
                type=comment.type,
                authorType=comment.author_type,
                botReplyStatus=comment.bot_reply_status,
                createdAt=comment.created_at,
            )

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Unexpected error in create_comment: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}",
            )
