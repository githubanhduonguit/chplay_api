"""Web search package.

Provides web search capabilities for the AI agent using a
provider-neutral interface. Currently uses Google Custom Search API
via httpx.AsyncClient.

The package exposes:
- WebSearchService: High-level service for performing web searches.
- WebSearchRequest: Input schema for search queries.
- WebSearchResult: Individual search result item.
- WebSearchResponse: Search response with metadata.
"""

from app.services.web_search.client import GoogleCustomSearchClient
from app.services.web_search.schemas import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)
from app.services.web_search.service import WebSearchService

__all__ = [
    "GoogleCustomSearchClient",
    "WebSearchRequest",
    "WebSearchResponse",
    "WebSearchResult",
    "WebSearchService",
]
