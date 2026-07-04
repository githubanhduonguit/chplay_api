"""
Hybrid search schemas.

Defines the data contracts for hybrid search (vector + BM25 + RRF)
and reranking operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HybridSearchRequest(BaseModel):
    """Request to perform a hybrid search.

    Attributes:
        query: The search query text.
        collection: The Qdrant collection name for vector search.
        top_k: Maximum number of final results to return after fusion.
        top_k_vector: Number of results to fetch from vector search per method.
        top_k_bm25: Number of results to fetch from BM25 search.
        weight_vector: Weight for vector search scores in RRF (default 0.5).
        weight_bm25: Weight for BM25 scores in RRF (default 0.5).
        rrf_k: RRF constant (default 60).
        score_threshold: Minimum score threshold for vector search.
        filter_conditions: Optional filter for vector search.
    """

    query: str = Field(..., description="Search query text", min_length=1)
    collection: str = Field(default="documents", description="Qdrant collection name")
    top_k: int = Field(default=10, description="Final number of results after fusion", ge=1)
    top_k_vector: int = Field(default=20, description="Results from vector search", ge=1)
    top_k_bm25: int = Field(default=20, description="Results from BM25 search", ge=1)
    weight_vector: float = Field(default=0.5, description="RRF weight for vector scores", ge=0.0, le=1.0)
    weight_bm25: float = Field(default=0.5, description="RRF weight for BM25 scores", ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, description="RRF constant for score fusion")
    score_threshold: float | None = Field(default=None, description="Minimum vector score threshold")
    filter_conditions: dict[str, Any] | None = Field(default=None, description="Vector search filter")


class HybridSearchResultItem(BaseModel):
    """A single result from a hybrid search.

    Attributes:
        id: Unique identifier (point ID or document ID).
        score: Combined RRF score.
        vector_score: Original vector similarity score.
        bm25_score: Original BM25 relevance score.
        payload: Metadata payload from the vector store.
        text: Text content (from payload or BM25).
    """

    id: str | int = Field(..., description="Result identifier")
    score: float = Field(..., description="Combined RRF fusion score")
    vector_score: float | None = Field(default=None, description="Original vector similarity score")
    bm25_score: float | None = Field(default=None, description="Original BM25 relevance score")
    payload: dict[str, Any] = Field(default_factory=dict, description="Result metadata payload")
    text: str | None = Field(default=None, description="Text content")


class HybridSearchResponse(BaseModel):
    """Response from a hybrid search operation.

    Attributes:
        results: Ranked list of search results.
        query: The original query.
        total_vector: Number of results from vector search.
        total_bm25: Number of results from BM25 search.
    """

    results: list[HybridSearchResultItem] = Field(default_factory=list, description="Ranked results")
    query: str = Field(..., description="Original query")
    total_vector: int = Field(default=0, description="Vector search result count")
    total_bm25: int = Field(default=0, description="BM25 search result count")


class RerankRequest(BaseModel):
    """Request to rerank a list of candidate results.

    Attributes:
        query: The original search query.
        candidates: List of candidate result items to rerank.
        top_k: Maximum number of results after reranking.
    """

    query: str = Field(..., description="Original search query")
    candidates: list[HybridSearchResultItem] = Field(..., description="Candidates to rerank")
    top_k: int = Field(default=10, description="Number of results to keep after reranking", ge=1)


class RerankResponse(BaseModel):
    """Response from a reranking operation.

    Attributes:
        results: Reranked list of results.
        query: The original query.
    """

    results: list[HybridSearchResultItem] = Field(default_factory=list, description="Reranked results")
    query: str = Field(..., description="Original query")


class SearchQuery(BaseModel):
    """API-level search query combining all retrieval parameters.

    Used as the top-level request schema by the API layer.
    Converts internally to HybridSearchRequest for the service layer.
    """

    query: str = Field(..., description="Search query text", min_length=1)
    collection: str = Field(default="documents", description="Collection to search in")
    top_k: int = Field(default=10, description="Final number of results", ge=1)
    top_k_vector: int = Field(default=20, description="Vector search pool size", ge=1)
    top_k_bm25: int = Field(default=20, description="BM25 search pool size", ge=1)
    weight_vector: float = Field(default=0.5, description="Vector search weight in RRF")
    weight_bm25: float = Field(default=0.5, description="BM25 weight in RRF")
    rrf_k: int = Field(default=60, description="RRF constant")
    score_threshold: float | None = Field(default=None, description="Vector score threshold")
    filter_conditions: dict[str, Any] | None = Field(default=None, description="Search filters")

    def to_hybrid_request(self) -> HybridSearchRequest:
        """Convert to the internal HybridSearchRequest."""
        return HybridSearchRequest(
            query=self.query,
            collection=self.collection,
            top_k=self.top_k,
            top_k_vector=self.top_k_vector,
            top_k_bm25=self.top_k_bm25,
            weight_vector=self.weight_vector,
            weight_bm25=self.weight_bm25,
            rrf_k=self.rrf_k,
            score_threshold=self.score_threshold,
            filter_conditions=self.filter_conditions,
        )


class SearchResult(BaseModel):
    """API-level search result returned to clients.

    A simplified view of HybridSearchResultItem with source tracking.
    """

    id: str | int = Field(..., description="Result identifier")
    score: float = Field(..., description="Combined relevance score")
    vector_score: float | None = Field(default=None, description="Vector similarity score")
    bm25_score: float | None = Field(default=None, description="BM25 relevance score")
    payload: dict[str, Any] = Field(default_factory=dict, description="Metadata")
    text: str | None = Field(default=None, description="Content text")
    source: str = Field(default="hybrid", description="Result source (vector, bm25, hybrid)")

    @classmethod
    def from_hybrid_item(cls, item: HybridSearchResultItem) -> SearchResult:
        """Create an API result from a hybrid search result item."""
        return cls(
            id=item.id,
            score=item.score,
            vector_score=item.vector_score,
            bm25_score=item.bm25_score,
            payload=item.payload,
            text=item.text,
        )


class RerankedResult(BaseModel):
    """A reranked search result with its reranker score."""

    item: SearchResult = Field(..., description="The original result")
    rerank_score: float = Field(..., description="Reranker relevance score")
