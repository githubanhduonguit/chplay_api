"""Schemas for the in-app job queues (review jobs + ticket proposal jobs)."""

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


@dataclass
class TicketProposalJob:
    """A job describing a ticket proposal that needs an external ticket.

    Created when an admin approves a proposal (HITL): the background worker
    consumes it and turns the APPROVED proposal into a ticket at the
    external provider (Trello / IT Helpdesk) asynchronously.

    Args:
        proposal_id: The ID of the TicketProposal to process.
    """

    proposal_id: int
