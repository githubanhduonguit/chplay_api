"""
TicketProposal repository.

Provides queries for the AI-generated ticket proposal flow:
fetching proposals by status/topic, pagination, and status transitions
(PROPOSED → APPROVED → CREATING → CREATED / REJECTED / FAILED).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ticket_proposal import TicketProposal
from app.db.repository.base import BaseRepository

# Statuses considered "open" — a proposal in one of these statuses can still
# receive newly detected reviews from a later batch (merge case daily).
OPEN_STATUSES = ("PROPOSED", "APPROVED", "CREATING")

# All valid statuses a proposal can transition to.
VALID_STATUSES = {"PROPOSED", "APPROVED", "REJECTED", "CREATING", "CREATED", "FAILED"}


class TicketProposalRepository(BaseRepository[TicketProposal]):
    """Repository for TicketProposal model with proposal-specific queries.

    Args:
        session: An async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TicketProposal, session)

    async def get_by_status(self, status: str, limit: int = 50) -> list[TicketProposal]:
        """Get proposals with a given status, ordered oldest first.

        Args:
            status: Status to filter by (e.g. "PROPOSED").
            limit: Maximum number of proposals to return.

        Returns:
            A list of matching proposals ordered by created_at ascending.
        """
        stmt = (
            select(TicketProposal)
            .where(TicketProposal.status == status)
            .order_by(TicketProposal.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_open_by_topic(
        self,
        app_id: int,
        topic_l1: str,
        topic_l2: str | None = None,
    ) -> TicketProposal | None:
        """Get an OPEN proposal for the same topic, regardless of batch_date.

        Used to merge newly detected reviews into a proposal created from an
        earlier batch (daily case). A topic match is exact on topic_l1 and
        topic_l2 (None matches None).

        Args:
            app_id: The app the proposal belongs to.
            topic_l1: Coarse topic (from PhoBERT aspects).
            topic_l2: Finer topic, optional.

        Returns:
            The oldest matching open proposal, or None if none exists.
        """
        stmt = (
            select(TicketProposal)
            .where(
                (TicketProposal.app_id == app_id)
                & (TicketProposal.status.in_(OPEN_STATUSES))
                & (TicketProposal.topic_l1 == topic_l1)
                & (
                    TicketProposal.topic_l2.is_(None)
                    if topic_l2 is None
                    else TicketProposal.topic_l2 == topic_l2
                )
            )
            .order_by(TicketProposal.created_at.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self, proposal_id: int, status: str
    ) -> TicketProposal | None:
        """Update the status of a proposal.

        Valid statuses: PROPOSED, APPROVED, REJECTED, CREATING, CREATED, FAILED.

        Args:
            proposal_id: The ID of the proposal to update.
            status: The new status value.

        Returns:
            The updated proposal if found, otherwise None.
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid ticket proposal status '{status}'. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return await self.update(proposal_id, status=status)

    async def list_paginated(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
        batch_date: date | None = None,
    ) -> tuple[list[TicketProposal], int]:
        """List proposals with pagination and optional filters.

        Args:
            skip: Number of proposals to skip (offset).
            limit: Maximum number of proposals to return.
            status: Optional status filter.
            batch_date: Optional batch date filter (reviews aggregated on that day).

        Returns:
            A tuple of (items, total) where total is the full match count.
        """
        filters: dict[str, Any] = {}
        if status is not None:
            filters["status"] = status
        if batch_date is not None:
            filters["batch_date"] = batch_date

        items = await self.get_many(
            skip=skip,
            limit=limit,
            filters=filters or None,
            order_by="created_at",
            descending=False,
        )
        total = await self.count(filters=filters or None)
        return items, total
