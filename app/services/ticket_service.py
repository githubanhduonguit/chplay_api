"""
TicketProposalService — business logic for the AI ticket feature.

Handles:
- Creating proposals from clustered negative reviews (job detect).
- Approving / rejecting proposals (REST API admin).
- Processing approved proposals → create external ticket (job worker).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.comment import Comment
from app.db.models.ticket_proposal import TicketProposal
from app.db.repository.ticket_proposal import TicketProposalRepository
from app.services.tickets.policy import TicketPolicy
from app.services.tickets.provider import TicketProvider
from app.services.tickets.schemas import CreateTicketRequest

logger = logging.getLogger(__name__)


class TicketProposalService:
    """Service for the ticket proposal flow.

    Args:
        session: Async DB session.
        provider: Ticket provider (defaults to the configured one).
        policy: Ticket creation policy.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: TicketProvider | None = None,
        policy: TicketPolicy | None = None,
    ) -> None:
        self.session = session
        self.repo = TicketProposalRepository(session)
        self.provider = provider
        self.policy = policy or TicketPolicy()

    # ── Read ─────────────────────────────────────────────────────────

    async def list_proposals(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        batch_date: date | None = None,
    ) -> tuple[list[TicketProposal], int]:
        """List proposals with pagination and optional filters.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            status: Optional status filter (e.g. "PROPOSED").
            batch_date: Optional batch date filter (case daily — admin xem
                ticket đề xuất cho 1 ngày, vd hôm qua).

        Returns:
            A tuple of (items, total).
        """
        skip = (page - 1) * page_size
        return await self.repo.list_paginated(
            skip=skip, limit=page_size, status=status, batch_date=batch_date
        )

    async def get_proposal(self, proposal_id: int) -> TicketProposal:
        """Get a proposal by id.

        Args:
            proposal_id: Proposal id.

        Returns:
            The TicketProposal.

        Raises:
            NotFoundError: If the proposal does not exist.
        """
        proposal = await self.repo.get(proposal_id)
        if proposal is None:
            raise NotFoundError(
                message=f"Ticket proposal {proposal_id} not found",
                error_code="TICKET_PROPOSAL_NOT_FOUND",
            )
        return proposal

    # ── HITL actions ─────────────────────────────────────────────────

    async def approve(self, proposal_id: int, note: str | None = None) -> TicketProposal:
        """Approve a PROPOSED proposal (transition PROPOSED → APPROVED).

        The approval is committed first, then the proposal id is enqueued so
        the background queue worker creates the external ticket (Trello /
        IT Helpdesk) asynchronously — no polling/interval scheduler needed.
        The enqueue is best-effort: a queue failure must not fail the
        approval itself (the proposal stays APPROVED and can be re-enqueued).

        Args:
            proposal_id: Proposal id.
            note: Optional admin note (stored in description log or ignored).

        Returns:
            The updated proposal.

        Raises:
            NotFoundError: If proposal not found.
            ValidationError: If status is not PROPOSED.
        """
        proposal = await self.get_proposal(proposal_id)
        if proposal.status != "PROPOSED":
            raise ValidationError(
                message=(
                    f"Cannot approve proposal {proposal_id} with status "
                    f"'{proposal.status}'; only 'PROPOSED' can be approved."
                ),
                error_code="INVALID_PROPOSAL_STATUS",
            )
        proposal.status = "APPROVED"
        await self.session.flush()
        # Commit BEFORE enqueueing: the queue worker runs in its own session
        # and must observe the APPROVED status, otherwise the policy check in
        # process_approved_proposal would reject the job.
        await self.session.commit()
        logger.info("Proposal %s approved (note=%s)", proposal_id, note)
        await self._enqueue_ticket_job(proposal_id)
        return proposal

    @staticmethod
    async def _enqueue_ticket_job(proposal_id: int) -> None:
        """Best-effort enqueue of an approved proposal for async ticket creation.

        Args:
            proposal_id: The approved proposal id.
        """
        # Lazy import to avoid coupling the service to the queue package at
        # import time (the queue worker lazily imports this service).
        try:
            from app.services.queue.schemas import TicketProposalJob
            from app.services.queue.ticket_queue import ticket_proposal_queue

            await ticket_proposal_queue.enqueue(
                TicketProposalJob(proposal_id=proposal_id)
            )
            logger.info(
                "Enqueued ticket proposal %s (queue size=%s)",
                proposal_id,
                ticket_proposal_queue.size(),
            )
        except Exception as e:
            logger.warning(
                "Failed to enqueue ticket proposal %s: %s",
                proposal_id,
                str(e),
                exc_info=True,
            )

    async def reject(self, proposal_id: int, reason: str | None = None) -> TicketProposal:
        """Reject a PROPOSED proposal (transition PROPOSED → REJECTED).

        Args:
            proposal_id: Proposal id.
            reason: Optional rejection reason.

        Returns:
            The updated proposal.

        Raises:
            NotFoundError: If proposal not found.
            ValidationError: If status is not PROPOSED.
        """
        proposal = await self.get_proposal(proposal_id)
        if proposal.status != "PROPOSED":
            raise ValidationError(
                message=(
                    f"Cannot reject proposal {proposal_id} with status "
                    f"'{proposal.status}'; only 'PROPOSED' can be rejected."
                ),
                error_code="INVALID_PROPOSAL_STATUS",
            )
        proposal.status = "REJECTED"
        await self.session.flush()
        logger.info("Proposal %s rejected (reason=%s)", proposal_id, reason)
        return proposal

    # ── Create proposals from reviews (AI analysis) ─────────────────

    def _review_topics(self, review: Comment) -> list[tuple[str, str | None]]:
        """Extract (topic_l1, topic_l2) pairs from a labeled review.

        Args:
            review: The Comment with loaded `aspects` relationship.

        Returns:
            List of (topic_l1, topic_l2) tuples (topic_l2 may be None).
        """
        topics: list[tuple[str, str | None]] = []
        for aspect in review.aspects or []:
            if not aspect.topic_l1:
                continue
            topics.append((aspect.topic_l1, aspect.topic_l2))
        # Fallback: review chưa có aspect nhưng đã label → dùng sentiment label
        if not topics:
            topics.append(("general", None))
        return topics

    async def create_proposals_from_reviews(
        self,
        reviews: list[Comment],
        *,
        min_reviews: int = 1,
        batch_date: date | None = None,
    ) -> list[TicketProposal]:
        """Cluster negative reviews by topic and create/merge proposals.

        Case daily: ``batch_date`` là ngày của review được tổng hợp (vd hôm
        qua). Nếu topic đã có proposal MỞ (PROPOSED/APPROVED/CREATING) từ
        batch trước → GỘP review mới vào proposal đó (thêm review_ids + cập
        nhật description/title). Chỉ tạo proposal mới khi topic chưa có
        proposal mở.

        Args:
            reviews: List of negative labeled reviews (của ngày hôm qua).
            min_reviews: Số review tối thiểu để tạo proposal MỚI (đã chốt = 1:
                mỗi cụm topic dù chỉ 1 review vẫn tạo 1 ticket đề xuất).
            batch_date: Ngày của batch (gắn vào proposal MỚI).

        Returns:
            List of created TicketProposal instances (status PROPOSED).
            (Proposal được gộp KHÔNG nằm trong list này.)
        """
        # Gom cụm: key = (app_id, topic_l1, topic_l2) → list review
        clusters: dict[tuple[int, str, str | None], list[Comment]] = {}
        for review in reviews:
            for topic_l1, topic_l2 in self._review_topics(review):
                key = (review.app_id, topic_l1, topic_l2)
                clusters.setdefault(key, []).append(review)

        created: list[TicketProposal] = []
        merged: list[int] = []  # proposal ids được gộp thêm review
        for (app_id, topic_l1, topic_l2), group in clusters.items():
            # MERGE: topic đã có proposal MỞ từ batch trước → gộp review mới vào
            existing = await self.repo.get_open_by_topic(
                app_id=app_id, topic_l1=topic_l1, topic_l2=topic_l2
            )
            if existing is not None:
                # Chỉ gộp review CHƯA có trong proposal (tránh trùng id)
                existing_ids = set(existing.review_ids or [])
                new_reviews = [r for r in group if r.id not in existing_ids]
                if new_reviews:
                    existing.review_ids = (existing.review_ids or []) + [
                        r.id for r in new_reviews
                    ]
                    existing.description = self._append_description(
                        existing.description, new_reviews
                    )
                    existing.title = (
                        f"[{topic_l1}] {topic_l2 or 'issue'} "
                        f"({len(existing.review_ids)} reviews)"
                    )
                    merged.append(existing.id)
                    logger.info(
                        "Merged %d reviews into open proposal %s (topic %s/%s).",
                        len(new_reviews), existing.id, topic_l1, topic_l2,
                    )
                continue

            # Tạo mới: cụm phải đủ min_reviews mới tạo proposal
            if len(group) < min_reviews:
                logger.info(
                    "Cluster %s/%s has only %d reviews (< %d), skipping.",
                    topic_l1, topic_l2, len(group), min_reviews,
                )
                continue

            proposal = TicketProposal(
                app_id=app_id,
                title=f"[{topic_l1}] {topic_l2 or 'issue'} ({len(group)} reviews)",
                description=self._build_description(group),
                status="PROPOSED",
                source="ai_agent",
                topic_l1=topic_l1,
                topic_l2=topic_l2,
                review_ids=[r.id for r in group],
                batch_date=batch_date,
            )
            self.session.add(proposal)
            created.append(proposal)
            logger.info(
                "Created proposal for %s/%s (batch %s) with %d reviews.",
                topic_l1, topic_l2, batch_date, len(group),
            )

        await self.session.flush()
        logger.info("Detect result: created=%d, merged_into=%s", len(created), merged)
        return created

    @staticmethod
    def _append_description(
        description: str | None, new_reviews: list[Comment]
    ) -> str:
        """Append new review excerpts to an existing proposal description.

        Args:
            description: Existing description (may be None).
            new_reviews: New reviews to append.

        Returns:
            Updated description text.
        """
        parts = [description] if description else []
        for review in new_reviews:
            excerpt = (review.content or "").strip().replace("\n", " ")[:200]
            parts.append(f"- (rating {review.rating}) {excerpt}")
        return "\n".join(parts)

    @staticmethod
    def _build_description(reviews: list[Comment]) -> str:
        """Build a human-readable description from clustered reviews.

        Args:
            reviews: Reviews in the cluster.

        Returns:
            Description text with review excerpts.
        """
        lines = [f"Phát hiện {len(reviews)} review phản ánh vấn đề:", ""]
        for i, review in enumerate(reviews[:10], 1):
            excerpt = (review.content or "").strip().replace("\n", " ")[:200]
            lines.append(f"{i}. (rating {review.rating}) {excerpt}")
        if len(reviews) > 10:
            lines.append(f"... và {len(reviews) - 10} review khác.")
        return "\n".join(lines)

    # ── Process approved → create ticket (worker) ────────────────────

    async def process_approved_proposal(
        self, proposal_id: int
    ) -> TicketProposal:
        """Turn an APPROVED proposal into an external ticket.

        Steps (match sequence diagram):
        1. Fetch proposal.
        2. Policy check → must be APPROVED.
        3. Update status → CREATING.
        4. Call provider.create_ticket().
        5. Success → CREATED + save ticket_id/ticket_url.
           Failure → FAILED + save error_message.

        Args:
            proposal_id: Proposal id.

        Returns:
            The updated proposal.

        Raises:
            NotFoundError: If proposal not found.
            ValidationError: If policy forbids creation.
        """
        proposal = await self.get_proposal(proposal_id)

        # Policy check (HITL)
        allowed, reason = self.policy.can_create(proposal)
        if not allowed:
            raise ValidationError(
                message=reason,
                error_code="TICKET_POLICY_DENIED",
            )

        # CREATING
        proposal.status = "CREATING"
        proposal.error_message = None
        await self.session.flush()

        # Execute tool
        provider = self.provider or self._default_provider()
        try:
            result = await provider.create_ticket(
                CreateTicketRequest(
                    title=proposal.title,
                    description=proposal.description or "",
                    metadata={
                        "app_id": proposal.app_id,
                        "topic_l1": proposal.topic_l1,
                        "topic_l2": proposal.topic_l2,
                        "review_ids": proposal.review_ids,
                    },
                )
            )
        except Exception as e:
            proposal.status = "FAILED"
            proposal.error_message = str(e)
            await self.session.flush()
            logger.error("Ticket creation failed for proposal %s: %s", proposal_id, e)
            return proposal

        # CREATED
        proposal.status = "CREATED"
        proposal.ticket_id = result.ticket_id
        proposal.ticket_url = result.ticket_url
        await self.session.flush()
        logger.info(
            "Proposal %s → CREATED (ticket_id=%s, url=%s)",
            proposal_id, result.ticket_id, result.ticket_url,
        )
        return proposal

    def _default_provider(self) -> TicketProvider:
        """Build the configured provider (lazy import to avoid cycles)."""
        from app.services.tickets import get_ticket_provider

        return get_ticket_provider()
