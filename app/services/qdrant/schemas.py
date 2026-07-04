"""
Qdrant vector store schemas.

Defines the data contracts for Qdrant collection management
and point operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Collection Schemas ───────────────────────────────────────────────


class CollectionConfig(BaseModel):
    """Configuration for creating a new Qdrant collection."""

    name: str = Field(..., description="Collection name")
    vector_size: int = Field(default=1024, description="Dimension of the embedding vectors")
    distance: str = Field(default="Cosine", description="Distance metric: Cosine, Dot, Euclid")
    on_disk: bool = Field(default=False, description="Store vectors on disk")
    hnsw_m: int | None = Field(default=None, description="HNSW M parameter")
    hnsw_ef_construct: int | None = Field(default=None, description="HNSW ef_construct parameter")


class CollectionInfo(BaseModel):
    """Information about an existing Qdrant collection."""

    name: str = Field(..., description="Collection name")
    vector_size: int = Field(..., description="Vector dimension")
    distance: str = Field(..., description="Distance metric")
    points_count: int = Field(default=0, description="Number of points in the collection")
    status: str = Field(default="green", description="Collection status")


class CollectionListResponse(BaseModel):
    """List of collections."""

    collections: list[CollectionInfo]


# ── Point Schemas ────────────────────────────────────────────────────


class PointMetadata(BaseModel):
    """Metadata payload for a Qdrant point."""

    document_id: int | None = Field(default=None, description="Source document ID")
    chunk_id: int | None = Field(default=None, description="Source chunk ID")
    text: str | None = Field(default=None, description="Original text content")
    filename: str | None = Field(default=None, description="Source filename")
    chunk_index: int | None = Field(default=None, description="Chunk index in the document")
    additional: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


class PointUpsert(BaseModel):
    """A single point to upsert into Qdrant."""

    id: str | int = Field(..., description="Unique point ID (string or integer)")
    vector: list[float] = Field(..., description="Embedding vector")
    metadata: PointMetadata = Field(default_factory=PointMetadata, description="Point metadata payload")


class UpsertResponse(BaseModel):
    """Response from an upsert operation."""

    status: str = Field(default="ok", description="Operation status")
    points_count: int = Field(..., description="Number of points upserted")


class DeleteResponse(BaseModel):
    """Response from a delete operation."""

    status: str = Field(default="ok", description="Operation status")


# ── Search Schemas ───────────────────────────────────────────────────


class SearchQuery(BaseModel):
    """A search query against a Qdrant collection."""

    collection: str = Field(..., description="Collection name to search")
    vector: list[float] = Field(..., description="Query embedding vector")
    limit: int = Field(default=10, description="Number of results to return")
    score_threshold: float | None = Field(default=None, description="Minimum score threshold")
    filter_conditions: dict[str, Any] | None = Field(
        default=None,
        description="Filter conditions (Qdrant filter format)",
    )
    with_payload: bool = Field(default=True, description="Include payload in results")
    with_vector: bool = Field(default=False, description="Include vector in results")


class HybridSearchQuery(BaseModel):
    """A hybrid search query combining vector and keyword scores."""

    collection: str = Field(..., description="Collection name to search")
    vector: list[float] = Field(..., description="Query embedding vector")
    keyword_filter: dict[str, Any] | None = Field(
        default=None,
        description="Keyword-based filter for pre-filtering",
    )
    limit: int = Field(default=10, description="Number of results to return")
    score_threshold: float | None = Field(default=None, description="Minimum score threshold")
    with_payload: bool = Field(default=True, description="Include payload in results")


class ScoredPoint(BaseModel):
    """A search result point with score."""

    id: str | int = Field(..., description="Point ID")
    score: float = Field(..., description="Similarity score")
    payload: dict[str, Any] = Field(default_factory=dict, description="Point metadata payload")
    vector: list[float] | None = Field(default=None, description="Embedding vector")


class SearchResponse(BaseModel):
    """Response from a search operation."""

    results: list[ScoredPoint]
    collection: str = Field(..., description="Collection name")


# ── Scroll / Pagination ──────────────────────────────────────────────


class ScrollQuery(BaseModel):
    """Query for scrolling/paginating through points."""

    collection: str = Field(..., description="Collection name")
    limit: int = Field(default=100, description="Number of points to return")
    offset: str | int | None = Field(default=None, description="Offset point ID for pagination")
    filter_conditions: dict[str, Any] | None = Field(
        default=None,
        description="Filter conditions",
    )
    with_payload: bool = Field(default=True, description="Include payload in results")
    with_vector: bool = Field(default=False, description="Include vector in results")


class ScrollResponse(BaseModel):
    """Response from a scroll operation."""

    points: list[ScoredPoint]
    next_offset: str | int | None = Field(default=None, description="Offset for the next page")
