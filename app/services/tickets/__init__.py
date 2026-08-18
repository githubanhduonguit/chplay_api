"""Ticket provider package: create tickets at external systems (IT Helpdesk / Trello)."""

from app.services.tickets.provider import TicketProvider, get_ticket_provider
from app.services.tickets.schemas import CreateTicketRequest, CreateTicketResult

__all__ = [
    "TicketProvider",
    "get_ticket_provider",
    "CreateTicketRequest",
    "CreateTicketResult",
]
