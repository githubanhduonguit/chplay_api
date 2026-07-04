"""
BM25 indexer service.

Provides a keyword-based retrieval index using the BM25Okapi algorithm
from the rank_bm25 library. Supports:

- Building an index from a collection of documents
- Incremental update and deletion of documents
- Fast search with configurable top-k
- Persistent storage on disk via pickle

The index maintains an internal mapping of doc_id → text so that
updates and deletions trigger a full rebuild as needed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pickle
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.exceptions import BM25Error
from app.services.bm25.schemas import (
    BM25Document,
    BM25IndexConfig,
    BM25SearchResult,
    BM25Stats,
)

logger = logging.getLogger(__name__)

# Default tokenization pattern: split on non-alphanumeric characters
_TOKEN_PATTERN = re.compile(r"[^\w]+")


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase tokens.

    Splits on non-alphanumeric characters and converts to lowercase.

    Args:
        text: Raw text to tokenize.

    Returns:
        A list of lowercase tokens.
    """
    return [t.lower() for t in _TOKEN_PATTERN.split(text) if t]


class BM25Indexer:
    """BM25 keyword indexer with persistence support.

    Wraps the rank_bm25 BM25Okapi implementation with:
    - A doc_id → text mapping for incremental updates
    - Pickle-based persistence to disk
    - Async-compatible interface (runs CPU work in thread pool)

    Attributes:
        config: BM25 configuration (k1, b, epsilon, index_path).
        _documents: Internal mapping of doc_id → original text content.
        _index: The BM25Okapi index instance (None until built).
    """

    def __init__(self, config: BM25IndexConfig | None = None) -> None:
        self.config = config or BM25IndexConfig(
            index_path=str(settings.data_path / "bm25_index"),
        )
        self._documents: dict[str | int, str] = {}
        self._tokenized_corpus: list[list[str]] = []
        self._index: BM25Okapi | None = None

    # ── Public API ───────────────────────────────────────────────────

    async def build_index(self, documents: list[BM25Document]) -> BM25Stats:
        """Build a new BM25 index from a list of documents.

        Any existing index is replaced.

        Args:
            documents: List of documents to index (doc_id + text).

        Returns:
            BM25Stats with index statistics.

        Raises:
            BM25Error: If the index build fails.
        """
        if not documents:
            self._documents = {}
            self._tokenized_corpus = []
            self._index = None
            await self._persist()
            return BM25Stats(index_path=self.config.index_path)

        doc_map: dict[str | int, str] = {}
        for doc in documents:
            doc_map[doc.doc_id] = doc.text

        self._documents = doc_map
        await self._rebuild()

        logger.info(
            "BM25 index built: %d documents, avg_doc_length=%.2f, vocab=%d",
            self.stats.num_documents,
            self.stats.avg_doc_length,
            self.stats.vocabulary_size,
        )

        return self.stats

    async def update_index(self, doc_id: str | int, text: str) -> BM25Stats:
        """Add or update a single document in the index.

        If the document already exists, it is replaced. The index
        is rebuilt from scratch to reflect the change.

        Args:
            doc_id: Unique document identifier.
            text: Document text content.

        Returns:
            Updated BM25Stats.

        Raises:
            BM25Error: If the update fails.
        """
        self._documents[doc_id] = text
        await self._rebuild()

        logger.debug("BM25 index updated: doc_id=%s", doc_id)
        return self.stats

    async def delete_from_index(self, doc_id: str | int) -> BM25Stats:
        """Remove a document from the index.

        Args:
            doc_id: Document identifier to remove.

        Returns:
            Updated BM25Stats.

        Raises:
            BM25Error: If the document is not found or deletion fails.
        """
        if doc_id not in self._documents:
            raise BM25Error(
                message=f"Document '{doc_id}' not found in BM25 index",
                error_code="BM25_DOCUMENT_NOT_FOUND",
                details={"doc_id": str(doc_id)},
            )

        del self._documents[doc_id]

        if not self._documents:
            self._tokenized_corpus = []
            self._index = None
            await self._persist()
            return BM25Stats(index_path=self.config.index_path)

        await self._rebuild()

        logger.debug("BM25 index: deleted doc_id=%s", doc_id)
        return self.stats

    async def search(self, query: str, top_k: int = 10) -> list[BM25SearchResult]:
        """Search the BM25 index for the most relevant documents.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            A list of BM25SearchResult sorted by relevance (highest score first).

        Raises:
            BM25Error: If the index has not been built or the search fails.
        """
        if self._index is None:
            raise BM25Error(
                message="BM25 index has not been built yet",
                error_code="BM25_NOT_BUILT",
            )

        if not query.strip():
            return []

        try:
            tokenized_query = _tokenize(query)
            scores = await asyncio.to_thread(
                self._index.get_scores,
                tokenized_query,
            )
        except Exception as e:
            raise BM25Error(
                message=f"BM25 search failed: {e}",
                error_code="BM25_SEARCH_FAILED",
                details={"query": query[:200]},
            ) from e

        # Pair doc_ids with scores and sort by score descending
        doc_ids = list(self._documents.keys())
        scored: list[tuple[int, str | int, float]] = [
            (i, doc_ids[i], float(scores[i]))
            for i in range(len(scores))
        ]
        scored.sort(key=lambda x: x[2], reverse=True)

        # Take top_k
        top_results = scored[:top_k]

        return [
            BM25SearchResult(
                doc_id=doc_id,
                score=score,
                text=self._documents.get(doc_id),
            )
            for _, doc_id, score in top_results
        ]

    # ── Persistence ──────────────────────────────────────────────────

    async def load(self) -> bool:
        """Load the BM25 index from disk.

        Returns:
            True if the index was successfully loaded, False if no
            persisted index exists.
        """
        path = Path(self.config.index_path)
        if not path.exists():
            logger.debug("No persisted BM25 index found at '%s'", path)
            return False

        try:
            data = await asyncio.to_thread(path.read_bytes)
            state: dict[str, Any] = pickle.loads(data)

            self._documents = state["documents"]
            self.config = state["config"]

            # Rebuild the BM25Okapi instance from the tokenized corpus
            self._tokenized_corpus = state["tokenized_corpus"]
            self._index = BM25Okapi(
                self._tokenized_corpus,
                k1=self.config.k1,
                b=self.config.b,
                epsilon=self.config.epsilon,
            )

            logger.info(
                "Loaded BM25 index from '%s': %d documents",
                path,
                len(self._documents),
            )
            return True

        except Exception as e:
            logger.warning("Failed to load BM25 index: %s", e)
            self._documents = {}
            self._tokenized_corpus = []
            self._index = None
            return False

    @property
    def stats(self) -> BM25Stats:
        """Get current index statistics.

        Returns:
            BM25Stats with counts and configuration details.
        """
        if self._index is None:
            return BM25Stats(index_path=self.config.index_path)

        avg_doc_length = (
            sum(len(doc) for doc in self._tokenized_corpus) / len(self._tokenized_corpus)
            if self._tokenized_corpus
            else 0.0
        )
        vocabulary: set[str] = set()
        for doc in self._tokenized_corpus:
            vocabulary.update(doc)

        return BM25Stats(
            num_documents=len(self._documents),
            avg_doc_length=avg_doc_length,
            vocabulary_size=len(vocabulary),
            index_path=self.config.index_path,
        )

    @property
    def is_built(self) -> bool:
        """Check whether the index has been built."""
        return self._index is not None

    # ── Internal Helpers ─────────────────────────────────────────────

    async def _rebuild(self) -> None:
        """Rebuild the BM25Okapi index from the current document mapping.

        Tokenizes all documents and constructs a new BM25Okapi instance.
        Persists the result to disk after building.

        Raises:
            BM25Error: If the rebuild operation fails.
        """
        if not self._documents:
            self._tokenized_corpus = []
            self._index = None
            await self._persist()
            return

        try:
            texts = list(self._documents.values())
            self._tokenized_corpus = await asyncio.to_thread(
                BM25Indexer._tokenize_corpus,
                texts,
            )
            self._index = await asyncio.to_thread(
                BM25Okapi,
                self._tokenized_corpus,
                k1=self.config.k1,
                b=self.config.b,
                epsilon=self.config.epsilon,
            )
        except Exception as e:
            raise BM25Error(
                message=f"Failed to rebuild BM25 index: {e}",
                error_code="BM25_REBUILD_FAILED",
                details={"document_count": len(self._documents)},
            ) from e

        await self._persist()

    async def _persist(self) -> None:
        """Save the current index state to disk.

        Stores the configuration, document mapping, and tokenized corpus
        so the index can be reloaded without re-tokenizing.
        """
        if not self.config.index_path:
            return  # Memory-only mode

        path = Path(self.config.index_path)
        if self._index is None:
            # Remove the persisted file if the index is empty
            if path.exists():
                await asyncio.to_thread(os.remove, str(path))
            return

        try:
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            state: dict[str, Any] = {
                "config": self.config,
                "documents": self._documents,
                "tokenized_corpus": self._tokenized_corpus,
            }

            data = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
            await asyncio.to_thread(path.write_bytes, data)

            logger.debug("Persisted BM25 index to '%s' (%d bytes)", path, len(data))

        except Exception as e:
            logger.error("Failed to persist BM25 index: %s", e)
            # Don't raise — persistence failure shouldn't break the application

    @staticmethod
    def _tokenize_corpus(texts: list[str]) -> list[list[str]]:
        """Tokenize a list of texts into a list of token lists.

        Args:
            texts: Raw text strings to tokenize.

        Returns:
            A list of token lists, one per input text.
        """
        return [_tokenize(t) for t in texts]
