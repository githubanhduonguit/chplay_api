"""
Ticket provider abstraction and factory.

Providers implement the ``create_ticket`` contract for external ticket
systems (generic REST IT Helpdesk, Trello, ...). The factory reads
``settings.TICKET_PROVIDER`` and returns the matching provider instance.
"""

from __future__ import annotations

import abc

from app.core.config import settings
from app.services.tickets.schemas import CreateTicketRequest, CreateTicketResult


class TicketProvider(abc.ABC):
    """Abstract interface for creating tickets at an external provider.

    Implementations must handle retries, timeouts, and raise
    ``TicketCreationError`` when the ticket cannot be created.
    """

    @abc.abstractmethod
    async def create_ticket(self, request: CreateTicketRequest) -> CreateTicketResult:
        """Create a ticket at the provider.

        Args:
            request: Ticket payload (title, description, metadata).

        Returns:
            The created ticket with its id and URL.

        Raises:
            TicketCreationError: If the provider rejects or cannot process
                the request.
        """


def get_ticket_provider() -> TicketProvider:
    """Get the configured ticket provider instance.

    Reads ``settings.TICKET_PROVIDER`` ("http" or "trello"). Imported lazily
    inside the function to avoid circular imports with the concrete providers.

    Returns:
        The configured TicketProvider.

    Raises:
        ValueError: If the provider name is unknown.
    """
    provider_name = settings.TICKET_PROVIDER

    if provider_name == "http":
        from app.services.tickets.http_provider import HttpTicketProvider

        return HttpTicketProvider()

    if provider_name == "trello":
        from app.services.tickets.trello_provider import TrelloTicketProvider

        return TrelloTicketProvider()

    raise ValueError(
        f"Unknown ticket provider '{provider_name}'. "
        "Supported providers: http, trello."
    )
