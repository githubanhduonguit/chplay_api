"""
BM25 index schemas.

Defines the data contracts for BM25 indexing and search operations.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BM25Document(BaseModel):
    """A document to be indexed by BM25.

    Attributes:
        doc_id: Unique identifier for the document (string or integer).
        text: The text content to index.
    """

    doc_id: str | int = Field(..., description="Unique document identifier")
    text: str = Field(..., description="Document text content to index")


class BM25SearchQuery(BaseModel):
    """A search query against the BM25 index.

    Attributes:
        query: The search query string.
        top_k: Maximum number of results to return.
    """

    query: str = Field(..., description="Search query string")
    top_k: int = Field(default=10, description="Number of top results to return", ge=1)


class BM25SearchResult(BaseModel):
    """A single BM25 search result.

    Attributes:
        doc_id: Document identifier.
        score: BM25 relevance score.
        text: Document text content (optional, included when available).
    """

    doc_id: str | int = Field(..., description="Document identifier")
    score: float = Field(..., description="BM25 relevance score")
    text: str | None = Field(default=None, description="Document text content")


class BM25IndexConfig(BaseModel):
    """Configuration for the BM25 index.

    Attributes:
        k1: BM25 k1 parameter (term saturation factor).
        b: BM25 b parameter (length normalization factor).
        epsilon: BM25 epsilon parameter (add-one smoothing).
        index_path: Path to persist the index on disk (empty = memory-only).
    """

    k1: float = Field(default=1.5, description="BM25 k1 term saturation parameter")
    b: float = Field(default=0.75, description="BM25 b length normalization parameter")
    epsilon: float = Field(default=0.25, description="BM25 epsilon add-one smoothing parameter")
    index_path: str = Field(default="data/bm25_index", description="Path to persist the BM25 index")


class BM25Stats(BaseModel):
    """Statistics about the current BM25 index state.

    Attributes:
        num_documents: Total number of documents indexed.
        avg_doc_length: Average document length in tokens.
        vocabulary_size: Number of unique terms in the index.
        index_path: Path where the index is persisted (if any).
    """

    num_documents: int = Field(default=0, description="Number of indexed documents")
    avg_doc_length: float = Field(default=0.0, description="Average document length (tokens)")
    vocabulary_size: int = Field(default=0, description="Number of unique terms")
    index_path: str | None = Field(default=None, description="Disk persistence path")
