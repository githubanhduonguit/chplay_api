"""
Trello ticket provider.

Creates cards on a Trello board via the Trello REST API
(``POST /1/cards``) using the configured API key, token, and target list.
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

TRELLO_CARDS_ENDPOINT = "https://api.trello.com/1/cards"


class TrelloTicketProvider(TicketProvider):
    """Create tickets (cards) on a Trello board.

    Args:
        api_key: Trello API key.
        api_token: Trello API token.
        list_id: idList where new cards are created.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries on transient failures.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_token: str | None = None,
        list_id: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.TRELLO_API_KEY
        self.api_token = api_token if api_token is not None else settings.TRELLO_API_TOKEN
        self.list_id = list_id if list_id is not None else settings.TRELLO_LIST_ID
        self.timeout = timeout if timeout is not None else settings.TICKET_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else settings.TICKET_MAX_RETRIES
        )

    async def create_ticket(self, request: CreateTicketRequest) -> CreateTicketResult:
        """Create a card on the configured Trello list.

        Args:
            request: Ticket payload (title → card name, description → card desc).

        Returns:
            The created card result (id + shortUrl).

        Raises:
            TicketCreationError: If Trello credentials are missing or the card
                could not be created after retries.
        """
        if not self.api_key or not self.api_token:
            raise TicketCreationError(
                "Trello is not configured. Set TRELLO_API_KEY and TRELLO_API_TOKEN."
            )
        if not self.list_id:
            raise TicketCreationError(
                "Trello list is not configured. Set TRELLO_LIST_ID."
            )

        params: dict[str, Any] = {
            "key": self.api_key,
            "token": self.api_token,
            "idList": self.list_id,
            "name": request.title,
            "desc": request.description or "",
        }
        if request.metadata:
            params["labels"] = str(request.metadata)

        last_error: str | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        TRELLO_CARDS_ENDPOINT,
                        params=params,
                    )
                except httpx.TimeoutException as e:
                    last_error = f"Trello API timed out: {e}"
                    logger.warning(
                        "Trello API timeout (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        e,
                    )
                    if attempt < self.max_retries:
                        await self._wait_retry(attempt)
                    continue
                except httpx.RequestError as e:
                    last_error = f"Trello API request error: {e}"
                    logger.warning(
                        "Trello API request error (attempt %d/%d): %s",
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
                    # Client errors (bad key/token/list) are not transient.
                    raise TicketCreationError(
                        f"Trello API rejected request with HTTP {response.status_code}: "
                        f"{response.text[:300]}"
                    )

                last_error = (
                    f"Trello API returned HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
                logger.warning(
                    "Trello API HTTP %d (attempt %d/%d): %s",
                    response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                    response.text[:200],
                )
                if attempt < self.max_retries:
                    await self._wait_retry(attempt)

        raise TicketCreationError(
            f"Failed to create Trello card after {self.max_retries + 1} attempts: "
            f"{last_error or 'unknown error'}"
        )

    def _parse_response(self, response: httpx.Response) -> CreateTicketResult:
        """Parse a successful Trello card response.

        Args:
            response: The successful HTTP response.

        Returns:
            The parsed card result.

        Raises:
            TicketCreationError: If the response is not valid JSON or is
                missing the card id.
        """
        try:
            data = response.json()
        except ValueError as e:
            raise TicketCreationError(
                f"Trello API returned invalid JSON: {response.text[:300]}"
            ) from e

        if not isinstance(data, dict):
            raise TicketCreationError(
                f"Trello API returned unexpected payload: {str(data)[:300]}"
            )

        card_id = data.get("id")
        if card_id is None:
            raise TicketCreationError(
                f"Trello API response missing 'id': {str(data)[:300]}"
            )

        card_url = data.get("shortUrl") or data.get("url")
        return CreateTicketResult(
            ticket_id=str(card_id),
            ticket_url=str(card_url) if card_url is not None else None,
            raw=data,
        )

    async def _wait_retry(self, attempt: int) -> None:
        """Wait with exponential backoff before retrying.

        Args:
            attempt: Current attempt index (0-based).
        """
        delay = 1.0 * (2**attempt)
        logger.debug("Retrying Trello card creation in %.1fs...", delay)
        await asyncio.sleep(delay)
