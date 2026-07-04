"""BM25 keyword indexing package.

Provides a BM25Okapi-based keyword search index with:
- Index building from document collections
- Incremental update and deletion
- Fast keyword search
- Optional disk persistence via pickle

Uses the rank_bm25 library under the hood.
"""

from app.services.bm25.indexer import BM25Indexer
from app.services.bm25.schemas import (
    BM25Document,
    BM25IndexConfig,
    BM25SearchQuery,
    BM25SearchResult,
    BM25Stats,
)

__all__ = [
    "BM25Indexer",
    "BM25Document",
    "BM25IndexConfig",
    "BM25SearchQuery",
    "BM25SearchResult",
    "BM25Stats",
]
