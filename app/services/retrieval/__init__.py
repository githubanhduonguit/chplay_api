"""Retrieval / hybrid search package.

Provides hybrid search combining dense vector search (Qdrant)
with sparse keyword search (BM25) using Reciprocal Rank Fusion (RRF),
and reranking capabilities for search results.
"""

from app.services.retrieval.hybrid import HybridSearchService
from app.services.retrieval.reranker import RerankerService
from app.services.retrieval.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
    RerankRequest,
    RerankResponse,
    RerankedResult,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "HybridSearchService",
    "RerankerService",
    "HybridSearchRequest",
    "HybridSearchResponse",
    "HybridSearchResultItem",
    "RerankRequest",
    "RerankResponse",
    "RerankedResult",
    "SearchQuery",
    "SearchResult",
]
