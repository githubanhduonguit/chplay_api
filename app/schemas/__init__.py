"""Pydantic schemas for API requests and responses."""

from app.schemas.review import (
    AspectSchema,
    AuthorSchema,
    ReviewSchema,
    GetReviewsResponseSchema,
)
from app.schemas.app import RatingSchema, DeveloperSchema, AppDetailSchema
from app.schemas.comment import (
    CreateReviewRequest,
    CreateCommentRequest,
    CommentResponseSchema,
)

__all__ = [
    "AspectSchema",
    "AuthorSchema",
    "ReviewSchema",
    "GetReviewsResponseSchema",
    "RatingSchema",
    "DeveloperSchema",
    "AppDetailSchema",
    "CreateReviewRequest",
    "CreateCommentRequest",
    "CommentResponseSchema",
]
