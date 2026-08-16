"""Schemas for review/comment responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AspectSchema(BaseModel):
    """Single aspect-level label assigned to a review/comment by PhoBERT.

    Attributes:
        topic_l1: Coarse topic (e.g., "account_user").
        topic_l2: Finer topic under topic_l1 (e.g., "signup_issue"), optional.
        sentiment: Sentiment toward this aspect (positive/negative/neutral).
        confidence: Confidence score of the aspect prediction (0-1).
    """

    topic_l1: str
    topic_l2: Optional[str] = None
    sentiment: str
    confidence: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


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
    # Aspect-level labels assigned by PhoBERT (from comment_aspects).
    # Empty list when the review/comment has not been labeled yet.
    labels: list[AspectSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class GetReviewsResponseSchema(BaseModel):
    """Response schema for get reviews endpoint."""

    total: int | None
    page: int
    pageSize: int
    reviews: list[ReviewSchema]
    comments: list[ReviewSchema]
