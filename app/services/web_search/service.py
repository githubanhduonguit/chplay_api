"""
Web search service.

High-level service for performing web searches. Wraps the provider-specific
client (Google Custom Search) with a provider-neutral interface.

Handles:
- Checking if web search is enabled/configured.
- Normalizing requests and responses.
- Logging and error handling (never crashes the caller).
- Returning empty response when disabled or misconfigured.

Usage:
    service = WebSearchService(api_key="...", engine_id="...")
    response = await service.search(WebSearchRequest(query="..."))
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.web_search.client import GoogleCustomSearchClient
from app.services.web_search.schemas import (
    WebSearchRequest,
    WebSearchResponse,
)

logger = logging.getLogger(__name__)


class WebSearchService:
    """High-level web search service.

    Provides a clean async interface for web search with built-in
    configuration checks, error handling, and logging.

    Args:
        api_key: Google API key (overrides settings).
        engine_id: Google Custom Search Engine ID (overrides settings).
        enabled: Whether web search is enabled (overrides settings).
        timeout: Request timeout in seconds (overrides settings).
        top_k: Default number of results (overrides settings).
        client: Optional pre-configured client instance.
    """

    def __init__(
        self,
        api_key: str | None = None,
        engine_id: str | None = None,
        enabled: bool | None = None,
        timeout: int | None = None,
        top_k: int | None = None,
        client: GoogleCustomSearchClient | None = None,
    ) -> None:
        self._enabled = enabled if enabled is not None else settings.WEB_SEARCH_ENABLED
        self._timeout = timeout or settings.WEB_SEARCH_TIMEOUT
        self._top_k = top_k or settings.WEB_SEARCH_TOP_K

        self._client = client or GoogleCustomSearchClient(
            api_key=api_key or settings.WEB_SEARCH_API_KEY,
            engine_id=engine_id or settings.WEB_SEARCH_ENGINE_ID,
            timeout=self._timeout,
        )

        if not self._client.is_configured:
            logger.warning(
                "WebSearchService: Google Custom Search not configured. "
                "Set WEB_SEARCH_API_KEY and WEB_SEARCH_ENGINE_ID env vars."
            )

    @property
    def enabled(self) -> bool:
        """Check if web search is enabled."""
        return self._enabled

    @property
    def is_ready(self) -> bool:
        """Check if the service is ready to perform searches.

        Returns True only if enabled AND properly configured.
        """
        return self._enabled and self._client.is_configured

    async def search(
        self,
        request: WebSearchRequest,
    ) -> WebSearchResponse:
        """Perform a web search.

        Args:
            request: Web search parameters.

        Returns:
            WebSearchResponse with results or empty on error/disabled.
            Never raises an exception.
        """
        # Check if web search is enabled
        if not self._enabled:
            logger.debug("Web search is disabled (WEB_SEARCH_ENABLED=False)")
            return WebSearchResponse(
                query=request.query,
                error="Web search is disabled.",
            )

        # Check if properly configured
        if not self._client.is_configured:
            logger.warning("Web search not configured — skipping search")
            return WebSearchResponse(
                query=request.query,
                error="Web search not configured. Set WEB_SEARCH_API_KEY and WEB_SEARCH_ENGINE_ID.",
            )

        # Merge defaults
        effective_request = WebSearchRequest(
            query=request.query,
            top_k=request.top_k if request.top_k else self._top_k,
            language=request.language or settings.WEB_SEARCH_LANGUAGE,
            region=request.region,
            safe_search=request.safe_search or settings.WEB_SEARCH_SAFE_SEARCH,
            timeout=request.timeout or self._timeout,
        )

        try:
            logger.debug(
                "Web search query='%s' top_k=%d provider=%s",
                effective_request.query[:100],
                effective_request.top_k,
                "google_custom_search",
            )

            response = await self._client.search(effective_request)

            if response.is_error:
                logger.warning(
                    "Web search error for '%s': %s",
                    effective_request.query[:100],
                    response.error,
                )
            else:
                logger.debug(
                    "Web search returned %d results in %dms",
                    len(response.results),
                    response.elapsed_ms,
                )

            return response

        except Exception as e:
            logger.error(
                "Unexpected web search error for '%s': %s",
                request.query[:100],
                e,
                exc_info=True,
            )
            return WebSearchResponse(
                query=request.query,
                error=f"Unexpected error: {e}",
            )

    async def search_simple(
        self,
        query: str,
        top_k: int | None = None,
    ) -> WebSearchResponse:
        """Convenience method for simple web search queries.

        Args:
            query: The search query text.
            top_k: Number of results (defaults to configured value).

        Returns:
            WebSearchResponse with results.
        """
        request = WebSearchRequest(
            query=query,
            top_k=top_k or self._top_k,
            timeout=self._timeout,
        )
        return await self.search(request)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    async def __aenter__(self) -> WebSearchService:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
