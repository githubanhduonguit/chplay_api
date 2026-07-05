"""Routes for app-related endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas import GetReviewsResponseSchema
from app.services import AppService

router = APIRouter(prefix="/api", tags=["apps"])


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
