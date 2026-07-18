"""Schemas for review/comment responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuthorSchema(BaseModel):
    """Author information for a review or comment."""

    type: str
    name: str | None
    avatar: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewSchema(BaseModel):
    """Single review or comment response."""

    id: int
    reviewId: Optional[int] = None
    author: AuthorSchema
    rating: Optional[int] = None
    content: str
    createdAt: datetime
    absaStatus: Optional[str] = None
    botReplyStatus: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GetReviewsResponseSchema(BaseModel):
    """Response schema for get reviews endpoint."""

    total: int | None
    page: int
    pageSize: int
    reviews: list[ReviewSchema]
    comments: list[ReviewSchema]
