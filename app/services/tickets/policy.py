"""
Ticket creation policy.

Decides whether a proposal is allowed to create a ticket at the external
provider. Only proposals explicitly approved by an admin can create tickets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.ticket_proposal import TicketProposal


class TicketPolicy:
    """Business rules guarding ticket creation."""

    @staticmethod
    def can_create(proposal: TicketProposal) -> tuple[bool, str]:
        """Check whether a ticket may be created for the given proposal.

        Args:
            proposal: The proposal to evaluate.

        Returns:
            A tuple of (allowed, reason). ``(True, "ALLOWED")`` when the
            proposal is approved; otherwise ``(False, <reason>)``.
        """
        if proposal.status == "APPROVED":
            return True, "ALLOWED"

        if proposal.status == "REJECTED":
            return False, "Proposal was rejected by admin"

        if proposal.status == "CREATED":
            return False, "Ticket already created for this proposal"

        if proposal.status == "CREATING":
            return False, "Ticket creation already in progress"

        if proposal.status == "FAILED":
            return False, "Previous ticket creation failed"

        # PROPOSED (or any unknown status) — not yet approved.
        return False, f"Proposal status '{proposal.status}' is not APPROVED"
