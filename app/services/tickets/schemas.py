"""Schemas for ticket provider operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateTicketRequest(BaseModel):
    """Request to create a ticket at the external provider (IT Helpdesk / Trello).

    Attributes:
        title: Ticket title (short summary of the issue).
        description: Detailed ticket description.
        metadata: Extra provider-specific metadata (e.g. app_id, review count).
    """

    title: str = Field(..., min_length=1, max_length=512)
    description: str | None = Field(None, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateTicketResult(BaseModel):
    """Result of a successful ticket creation.

    Attributes:
        ticket_id: External ticket/card id returned by the provider.
        ticket_url: URL to open the ticket at the provider.
        raw: Full raw response payload from the provider.
    """

    ticket_id: str
    ticket_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
