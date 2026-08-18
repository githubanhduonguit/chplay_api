"""Admin REST API for ticket proposals (Human-In-The-Loop).

Endpoints:
- GET  /tickets/proposals              — list proposals (page, status, batchDate)
- GET  /tickets/proposals/{id}         — proposal detail
- POST /tickets/proposals/{id}/approve — approve → enqueue async ticket creation
- POST /tickets/proposals/{id}/reject  — reject (no ticket created)

Approval commits the PROPOSED → APPROVED transition and enqueues the
proposal id into the in-app task queue; the background
``TicketProposalQueueWorker`` creates the external ticket (Trello /
IT Helpdesk) asynchronously — no polling scheduler involved.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas import (
    ApproveProposalRequest,
    ProposalActionResponse,
    RejectProposalRequest,
    TicketProposalListResponse,
    TicketProposalSchema,
)
from app.services.ticket_service import TicketProposalService

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("/proposals", response_model=TicketProposalListResponse)
async def list_proposals(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    pageSize: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(
        None,
        description="Filter by status (PROPOSED, APPROVED, REJECTED, CREATING, CREATED, FAILED)",
    ),
    batchDate: date | None = Query(
        None,
        description="Filter by batch date (YYYY-MM-DD) — reviews aggregated on that day",
    ),
    db: AsyncSession = Depends(get_db),
) -> TicketProposalListResponse:
    """List ticket proposals with pagination and optional filters."""
    service = TicketProposalService(db)
    items, total = await service.list_proposals(
        page=page,
        page_size=pageSize,
        status=status,
        batch_date=batchDate,
    )
    return TicketProposalListResponse(
        total=total,
        page=page,
        pageSize=pageSize,
        items=list(items),
    )


@router.get("/proposals/{proposal_id}", response_model=TicketProposalSchema)
async def get_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
) -> TicketProposalSchema:
    """Get a single ticket proposal by id.

    Args:
        proposal_id: Proposal id.

    Returns:
        The proposal details.

    Raises:
        404: If the proposal does not exist.
    """
    service = TicketProposalService(db)
    return await service.get_proposal(proposal_id)


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ProposalActionResponse,
)
async def approve_proposal(
    proposal_id: int,
    request: ApproveProposalRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProposalActionResponse:
    """Approve a PROPOSED proposal.

    The transition is committed and the proposal id is enqueued so the
    background queue worker creates the external ticket (Trello /
    IT Helpdesk) asynchronously.

    Args:
        proposal_id: Proposal id.
        request: Optional admin note.
        db: Database session.

    Returns:
        ProposalActionResponse with the new status.

    Raises:
        404: If the proposal does not exist.
        422: If the proposal is not in PROPOSED status.
    """
    service = TicketProposalService(db)
    proposal = await service.approve(
        proposal_id,
        note=request.note if request else None,
    )
    return ProposalActionResponse(
        id=proposal.id,
        status=proposal.status,
        message=f"Proposal {proposal.id} approved; ticket creation enqueued.",
    )


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalActionResponse,
)
async def reject_proposal(
    proposal_id: int,
    request: RejectProposalRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ProposalActionResponse:
    """Reject a PROPOSED proposal (no ticket is created).

    Args:
        proposal_id: Proposal id.
        request: Optional rejection reason.
        db: Database session.

    Returns:
        ProposalActionResponse with the new status.

    Raises:
        404: If the proposal does not exist.
        422: If the proposal is not in PROPOSED status.
    """
    service = TicketProposalService(db)
    proposal = await service.reject(
        proposal_id,
        reason=request.reason if request else None,
    )
    return ProposalActionResponse(
        id=proposal.id,
        status=proposal.status,
        message=f"Proposal {proposal.id} rejected.",
    )
