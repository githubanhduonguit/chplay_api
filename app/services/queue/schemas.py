"""Schemas for the in-app review job queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReviewJob:
    """A job describing a review that needs a bot reply.

    Args:
        review_id: The ID of the review Comment to process.
        app_id: The ID of the app the review belongs to.
        created_at: When the review was created, if known.
    """

    review_id: int
    app_id: int
    created_at: datetime | None = None
