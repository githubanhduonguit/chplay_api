"""
Google Custom Search API client.

Provides a thin async client for the Google Custom Search JSON API
using httpx.AsyncClient. The client is provider-specific; the
WebSearchService wraps it with a provider-neutral interface.

Documentation: https://developers.google.com/custom-search/v1/reference/rest/v1/cse/list

API endpoint:
    GET https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={ENGINE_ID}&q={QUERY}

Note: Google Custom Search has a free tier of 100 queries/day.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from app.services.web_search.schemas import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 15

# Google Custom Search API endpoint
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class GoogleCustomSearchClient:
    """Async client for Google Custom Search JSON API.

    Args:
        api_key: Google API key.
        engine_id: Custom Search Engine ID (cx parameter).
        timeout: Default request timeout in seconds.
        max_retries: Maximum number of retry attempts on failure.
    """

    def __init__(
        self,
        api_key: str | None = None,
        engine_id: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or ""
        self.engine_id = engine_id or ""
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if the client has valid credentials."""
        return bool(self.api_key and self.engine_id)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.timeout,
                    read=self.timeout,
                    write=self.timeout,
                    pool=self.timeout,
                ),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    async def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Execute a web search using Google Custom Search API.

        Args:
            request: Web search parameters.

        Returns:
            WebSearchResponse with normalized results.
        """
        if not self.is_configured:
            logger.warning("Google Custom Search not configured (missing API key or engine ID)")
            return WebSearchResponse(
                query=request.query,
                error="Google Custom Search not configured. Set WEB_SEARCH_API_KEY and WEB_SEARCH_ENGINE_ID.",
            )

        start_time = time.monotonic()
        last_error: str | None = None

        for attempt in range(1 + self.max_retries):
            try:
                client = await self._get_client()

                params: dict[str, Any] = {
                    "key": self.api_key,
                    "cx": self.engine_id,
                    "q": request.query,
                    "num": min(request.top_k, 10),  # Max 10 per request
                    "safe": request.safe_search,
                }

                if request.language:
                    params["lr"] = request.language
                if request.region:
                    params["gl"] = request.region

                response = await client.get(
                    GOOGLE_CSE_ENDPOINT,
                    params=params,
                )

                elapsed = int((time.monotonic() - start_time) * 1000)

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(data, request, elapsed)

                elif response.status_code == 429:
                    logger.warning("Google CSE rate limited (attempt %d/%d)", attempt + 1, self.max_retries + 1)
                    last_error = "Rate limited by Google Custom Search API"
                    if attempt < self.max_retries:
                        await self._wait_retry(attempt)
                    continue

                elif response.status_code == 403:
                    logger.error("Google CSE forbidden — check API key and billing: %s", response.text[:200])
                    return WebSearchResponse(
                        query=request.query,
                        error="Google Custom Search API access denied. Check API key and billing.",
                    )

                else:
                    logger.error("Google CSE HTTP %d: %s", response.status_code, response.text[:200])
                    last_error = f"Google CSE returned HTTP {response.status_code}"
                    if attempt < self.max_retries:
                        await self._wait_retry(attempt)
                    continue

            except httpx.TimeoutException:
                logger.warning("Google CSE timeout (attempt %d/%d)", attempt + 1, self.max_retries + 1)
                last_error = "Request timed out"
                if attempt < self.max_retries:
                    await self._wait_retry(attempt)
                continue

            except httpx.RequestError as e:
                logger.warning("Google CSE request error (attempt %d/%d): %s", attempt + 1, self.max_retries + 1, e)
                last_error = f"Request error: {e}"
                if attempt < self.max_retries:
                    await self._wait_retry(attempt)
                continue

        # All retries exhausted
        elapsed = int((time.monotonic() - start_time) * 1000)
        return WebSearchResponse(
            query=request.query,
            error=last_error or "Unknown error",
            elapsed_ms=elapsed,
        )

    def _parse_response(
        self,
        data: dict[str, Any],
        request: WebSearchRequest,
        elapsed_ms: int,
    ) -> WebSearchResponse:
        """Parse Google CSE JSON response into normalized schema.

        Args:
            data: Raw JSON response from Google CSE API.
            request: Original search request.
            elapsed_ms: Elapsed time in milliseconds.

        Returns:
            Normalized WebSearchResponse.
        """
        items = data.get("items", [])
        search_info = data.get("searchInformation", {})
        total_results_str = search_info.get("totalResults", "0")
        try:
            total_results = int(total_results_str)
        except (ValueError, TypeError):
            total_results = None

        results: list[WebSearchResult] = []
        for i, item in enumerate(items):
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            display_link = item.get("displayLink", "")

            # Skip results without URL or snippet
            if not link or (not title and not snippet):
                continue

            score = max(0.0, 1.0 - (i * 0.1))  # Position-based score

            # Parse published date if available
            pagemap = item.get("pagemap", {}) or {}
            metatags = pagemap.get("metatags", [{}])[0] if pagemap.get("metatags") else {}
            article_dates = []
            for tag_key in ["article:published_time", "datePublished", "date", "pubdate"]:
                val = metatags.get(tag_key)
                if val:
                    article_dates.append(val)
            for news_key in ["date", "datePublished"]:
                news_article = pagemap.get("newsarticle", [{}])[0] if pagemap.get("newsarticle") else {}
                val = news_article.get(news_key)
                if val:
                    article_dates.append(val)

            published_at: datetime | None = None
            for date_str in article_dates:
                try:
                    published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    break
                except (ValueError, TypeError):
                    continue

            results.append(
                WebSearchResult(
                    title=title,
                    url=link,
                    snippet=snippet,
                    source=display_link,
                    published_at=published_at,
                    score=score,
                    raw={"position": i + 1, "cache_id": item.get("cacheId")},
                )
            )

        # Trim to requested top_k
        results = results[: request.top_k]

        return WebSearchResponse(
            results=results,
            query=request.query,
            provider="google_custom_search",
            elapsed_ms=elapsed_ms,
            total_results=total_results,
        )

    async def _wait_retry(self, attempt: int) -> None:
        """Wait with exponential backoff before retrying.

        Args:
            attempt: Current attempt index (0-based).
        """
        delay = 1.0 * (2 ** attempt)
        logger.debug("Retrying in %.1fs...", delay)
        await asyncio.sleep(delay)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GoogleCustomSearchClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
