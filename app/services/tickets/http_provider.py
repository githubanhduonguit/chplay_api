"""
Generic REST HTTP ticket provider.

Posts ticket payloads to a generic IT Helpdesk REST endpoint. Retries
transient failures (network errors, timeouts, 5xx) with exponential
backoff; 4xx responses are not retried.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import TicketCreationError
from app.services.tickets.provider import TicketProvider
from app.services.tickets.schemas import CreateTicketRequest, CreateTicketResult

logger = logging.getLogger(__name__)

# Default response fields to extract the ticket id and URL from the payload.
DEFAULT_ID_FIELD = "id"
DEFAULT_URL_FIELD = "url"


class HttpTicketProvider(TicketProvider):
    """Create tickets via a generic REST HTTP endpoint.

    Args:
        api_url: Endpoint that creates the ticket.
        api_key: Optional bearer token sent as ``Authorization: Bearer <key>``.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries on transient failures.
        id_field: JSON key holding the ticket id in the response.
        url_field: JSON key holding the ticket URL in the response.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        id_field: str = DEFAULT_ID_FIELD,
        url_field: str = DEFAULT_URL_FIELD,
    ) -> None:
        self.api_url = api_url if api_url is not None else settings.TICKET_API_URL
        self.api_key = api_key if api_key is not None else settings.TICKET_API_KEY
        self.timeout = timeout if timeout is not None else settings.TICKET_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else settings.TICKET_MAX_RETRIES
        )
        self.id_field = id_field
        self.url_field = url_field

    async def create_ticket(self, request: CreateTicketRequest) -> CreateTicketResult:
        """Create a ticket via the configured REST endpoint.

        Args:
            request: Ticket payload to send.

        Returns:
            The created ticket result.

        Raises:
            TicketCreationError: If the endpoint is not configured or the
                ticket could not be created after retries.
        """
        if not self.api_url:
            raise TicketCreationError("TICKET_API_URL is not configured.")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "title": request.title,
            "description": request.description or "",
        }
        if request.metadata:
            payload["metadata"] = request.metadata

        last_error: str | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                    )
                except httpx.TimeoutException as e:
                    last_error = f"Ticket API timed out: {e}"
                    logger.warning(
                        "Ticket API timeout (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        e,
                    )
                    if attempt < self.max_retries:
                        await self._wait_retry(attempt)
                    continue
                except httpx.RequestError as e:
                    last_error = f"Ticket API request error: {e}"
                    logger.warning(
                        "Ticket API request error (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        e,
                    )
                    if attempt < self.max_retries:
                        await self._wait_retry(attempt)
                    continue

                if 200 <= response.status_code < 300:
                    return self._parse_response(response)

                if 400 <= response.status_code < 500:
                    # Client errors are not transient — do not retry.
                    raise TicketCreationError(
                        f"Ticket API rejected request with HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )

                # 5xx (and anything else) → retry.
                last_error = (
                    f"Ticket API returned HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
                logger.warning(
                    "Ticket API HTTP %d (attempt %d/%d): %s",
                    response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                    response.text[:200],
                )
                if attempt < self.max_retries:
                    await self._wait_retry(attempt)

        raise TicketCreationError(
            f"Failed to create ticket after {self.max_retries + 1} attempts: "
            f"{last_error or 'unknown error'}"
        )

    def _parse_response(self, response: httpx.Response) -> CreateTicketResult:
        """Parse a successful response into a CreateTicketResult.

        Args:
            response: The successful HTTP response.

        Returns:
            The parsed ticket result.

        Raises:
            TicketCreationError: If the response is not valid JSON or is
                missing the id field.
        """
        try:
            data = response.json()
        except ValueError as e:
            raise TicketCreationError(
                f"Ticket API returned invalid JSON: {response.text[:300]}"
            ) from e

        if not isinstance(data, dict):
            raise TicketCreationError(
                f"Ticket API returned unexpected payload: {str(data)[:300]}"
            )

        ticket_id = self._extract_field(data, self.id_field)
        if ticket_id is None:
            raise TicketCreationError(
                f"Ticket API response missing id field '{self.id_field}': "
                f"{str(data)[:300]}"
            )

        ticket_url = self._extract_field(data, self.url_field)
        return CreateTicketResult(
            ticket_id=str(ticket_id),
            ticket_url=str(ticket_url) if ticket_url is not None else None,
            raw=data,
        )

    def _extract_field(self, data: dict[str, Any], field: str) -> Any:
        """Extract a (possibly dotted) field from a response dict.

        Args:
            data: The response payload.
            field: Field key, e.g. "id" or "data.ticket.id".

        Returns:
            The field value, or None if not found.
        """
        current: Any = data
        for part in field.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    async def _wait_retry(self, attempt: int) -> None:
        """Wait with exponential backoff before retrying.

        Args:
            attempt: Current attempt index (0-based).
        """
        delay = 1.0 * (2**attempt)
        logger.debug("Retrying ticket creation in %.1fs...", delay)
        await asyncio.sleep(delay)
