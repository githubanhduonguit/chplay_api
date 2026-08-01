"""
Web search schemas.

Defines the data contracts for web search operations using a
provider-neutral format. All providers (Google, Tavily, Brave, etc.)
return results normalized into these schemas.

Attributes:
    WebSearchRequest: Input parameters for a web search query.
    WebSearchResult: A single search result from the web.
    WebSearchResponse: Complete search response with metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    """Request to perform a web search.

    Attributes:
        query: The search query text.
        top_k: Maximum number of results to return (1-10).
        language: Language restriction (e.g. "lang_vi", "lang_en").
        region: Geographic region (e.g. "vn", "us").
        safe_search: Safe search level ("active", "off").
        timeout: Request timeout in seconds.
    """

    query: str = Field(..., description="Search query text", min_length=1, max_length=500)
    top_k: int = Field(default=5, description="Number of results to return", ge=1, le=10)
    language: str | None = Field(default="lang_vi", description="Language restriction")
    region: str | None = Field(default=None, description="Geographic region")
    safe_search: str = Field(default="active", description="Safe search level")
    timeout: int = Field(default=15, description="Request timeout in seconds", ge=5, le=60)


class WebSearchResult(BaseModel):
    """A single search result from the web.

    Attributes:
        title: The page title.
        url: The full URL of the result.
        snippet: A short text excerpt from the page.
        source: The source/domain name (e.g. "google.com").
        published_at: When the page was published (if available).
        score: Relevance score from the provider (0.0-1.0).
        raw: Raw provider data for debugging.
    """

    title: str = Field(default="", description="Page title")
    url: str = Field(default="", description="Full URL")
    snippet: str = Field(default="", description="Text excerpt")
    source: str | None = Field(default=None, description="Source domain name")
    published_at: datetime | None = Field(default=None, description="Publication date")
    score: float = Field(default=0.0, description="Relevance score (0.0-1.0)", ge=0.0, le=1.0)
    raw: dict[str, Any] | None = Field(default=None, description="Raw provider data")


class WebSearchResponse(BaseModel):
    """Response from a web search operation.

    Attributes:
        results: List of search results.
        query: The original query.
        provider: The search provider used.
        elapsed_ms: Time taken for the search in milliseconds.
        total_results: Total number of results found (provider estimate).
        error: Error message if the search failed.
    """

    results: list[WebSearchResult] = Field(default_factory=list, description="Search results")
    query: str = Field(..., description="Original query")
    provider: str = Field(default="google_custom_search", description="Search provider")
    elapsed_ms: int = Field(default=0, description="Search duration in milliseconds")
    total_results: int | None = Field(default=None, description="Total results estimate")
    error: str | None = Field(default=None, description="Error message")

    @property
    def has_results(self) -> bool:
        """Check if the response contains any results."""
        return len(self.results) > 0

    @property
    def is_error(self) -> bool:
        """Check if the response contains an error."""
        return self.error is not None

    def format_context(self, max_chars: int = 4000) -> str:
        """Format results as a citation-ready context string.

        Each result is formatted as:
            [W<N>] <title>
            URL: <url>
            <snippet>

        Args:
            max_chars: Maximum characters for the formatted string.

        Returns:
            A formatted string with numbered web citations.
        """
        if not self.results:
            return ""

        parts: list[str] = []
        char_count = 0

        for i, result in enumerate(self.results, 1):
            title = result.title or "Không có tiêu đề"
            url = result.url or ""
            snippet = result.snippet or ""

            block = f"[W{i}] {title}\nURL: {url}\n{snippet}"

            if char_count + len(block) > max_chars:
                remaining = max_chars - char_count
                if remaining > 100:
                    parts.append(block[:remaining] + "...")
                break

            parts.append(block)
            char_count += len(block)

        return "\n\n".join(parts)
