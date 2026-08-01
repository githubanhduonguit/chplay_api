"""Schemas for comment/review requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateReviewRequest(BaseModel):
    """Request schema for creating a review."""

    authorName: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Name of the reviewer",
    )
    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Rating from 1 to 5 stars",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Review content",
    )


class CreateCommentRequest(BaseModel):
    """Request schema for creating a comment."""

    authorName: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Name of the commenter",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Comment content",
    )


class CommentResponseSchema(BaseModel):
    """Response schema for comment/review."""

    id: int = Field(..., description="Comment ID")
    appId: int = Field(..., description="App ID")
    reviewId: Optional[int] = Field(None, description="Parent review ID (for comments only)")
    rating: Optional[int] = Field(None, description="Rating (1-5 for reviews only)")
    content: str = Field(..., description="Comment/review content")
    type: str = Field(..., description="Type: 'review' or 'comment'")
    authorType: str = Field(..., description="Author type: 'user' or 'bot'")
    botReplyStatus: Optional[str] = Field(None, description="Bot reply status")
    createdAt: datetime = Field(..., description="Creation timestamp")

    model_config = ConfigDict(from_attributes=True)
