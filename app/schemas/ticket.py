"""Schemas for AI-generated ticket proposals."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TicketProposalSchema(BaseModel):
    """Single ticket proposal response.

    Fields are snake_case so ``from_attributes`` maps directly onto the
    ``TicketProposal`` ORM model; serialization uses camelCase aliases
    (``appId``, ``topicL1``, ...) to match the rest of the API.
    """

    id: int
    app_id: int
    title: str
    description: Optional[str] = None
    status: str
    source: str
    topic_l1: Optional[str] = None
    topic_l2: Optional[str] = None
    review_ids: list[int] = Field(default_factory=list)
    batch_date: Optional[date] = None
    ticket_id: Optional[str] = None
    ticket_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class TicketProposalListResponse(BaseModel):
    """Paginated list of ticket proposals."""

    total: int
    page: int
    pageSize: int
    items: list[TicketProposalSchema]


class ApproveProposalRequest(BaseModel):
    """Request schema for approving a ticket proposal."""

    note: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional note from the admin when approving",
    )


class RejectProposalRequest(BaseModel):
    """Request schema for rejecting a ticket proposal."""

    reason: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional reason for rejecting the proposal",
    )


class ProposalActionResponse(BaseModel):
    """Response after an approve/reject action on a proposal."""

    id: int
    status: str
    message: str
