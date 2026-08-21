"""Routes for app-related endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.schemas import (
    Auth0User,
    GetReviewsResponseSchema,
    AppDetailSchema,
    CreateReviewRequest,
    CreateCommentRequest,
    CommentResponseSchema,
)
from app.services import AppService

router = APIRouter(prefix="/api", tags=["apps"])


@router.get("/apps/{package_name}", response_model=AppDetailSchema)
async def get_app_detail(
    package_name: str,
    db: AsyncSession = Depends(get_db),
) -> AppDetailSchema:
    """Get detailed information for an app.

    Args:
        package_name: The app's package name (e.g., com.vnpt.vnpttoken.vneid).
        db: Database session.

    Returns:
        AppDetailSchema with app information.

    Raises:
        404: If app not found.
    """
    service = AppService(db)
    return await service.get_app_detail(package_name)


@router.get("/apps/{package_name}/reviews", response_model=GetReviewsResponseSchema)
async def get_reviews(
    package_name: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> GetReviewsResponseSchema:
    """Get reviews and comments for an app.

    Args:
        package_name: The app's package name (e.g., com.vnpt.vnpttoken.vneid).
        page: Page number for pagination (default: 1).
        pageSize: Number of items per page, max 100 (default: 20).
        db: Database session.

    Returns:
        GetReviewsResponseSchema with reviews and comments.

    Raises:
        404: If app not found.
    """
    service = AppService(db)
    return await service.get_reviews(package_name, page, pageSize)


@router.post(
    "/apps/{package_name}/reviews",
    response_model=CommentResponseSchema,
    status_code=201,
)
async def create_review(
    package_name: str,
    request: CreateReviewRequest,
    db: AsyncSession = Depends(get_db),
    _user: Auth0User = Depends(get_current_user),
) -> CommentResponseSchema:
    """Create a new review for an app.

    Args:
        package_name: The app's package name (e.g., com.vnpt.vnpttoken.vneid).
        request: Review creation request with authorName, rating, content.
        db: Database session.

    Returns:
        CommentResponseSchema with created review data.

    Raises:
        400: If request validation fails.
        404: If app not found.
        500: If database error occurs.
    """
    service = AppService(db)
    return await service.create_review(package_name, request)


@router.post(
    "/apps/{package_name}/reviews/{review_id}/comments",
    response_model=CommentResponseSchema,
    status_code=201,
)
async def create_comment(
    package_name: str,
    review_id: int,
    request: CreateCommentRequest,
    db: AsyncSession = Depends(get_db),
    _user: Auth0User = Depends(get_current_user),
) -> CommentResponseSchema:
    """Create a new comment on a review.

    Args:
        package_name: The app's package name (e.g., com.vnpt.vnpttoken.vneid).
        review_id: ID of the parent review.
        request: Comment creation request with authorName, content.
        db: Database session.

    Returns:
        CommentResponseSchema with created comment data.

    Raises:
        400: If request validation fails.
        404: If app or review not found.
        500: If database error occurs.
    """
    service = AppService(db)
    return await service.create_comment(package_name, review_id, request)
