"""
Hybrid search service.

Combines dense vector search (Qdrant) with sparse keyword search (BM25)
using Reciprocal Rank Fusion (RRF) to produce a single ranked result set.

Pipeline:
    Query → Embed → Vector Search → BM25 Search → RRF Merge → Top K → Return

RRF formula:
    score(d) = weight_vector * Σ(1 / (rrf_k + rank_vector(d)))
             + weight_bm25 * Σ(1 / (rrf_k + rank_bm25(d)))
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import RetrievalError
from app.services.bm25.indexer import BM25Indexer
from app.services.embedding.service import EmbeddingService
from app.services.qdrant.schemas import SearchQuery
from app.services.qdrant.service import QdrantService
from app.services.retrieval.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
)

logger = logging.getLogger(__name__)


class HybridSearchService:
    """Hybrid search combining vector similarity and BM25 keyword search.

    Orchestrates the full hybrid search pipeline:
    1. Embed the query text into a vector
    2. Search the Qdrant vector store for similar vectors
    3. Search the BM25 keyword index
    4. Merge results using Reciprocal Rank Fusion (RRF)
    5. Return the top-k fused results

    Attributes:
        embedding_service: Service for generating query embeddings.
        qdrant_service: Service for vector store operations.
        bm25_indexer: BM25 keyword indexer.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        bm25_indexer: BM25Indexer | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.qdrant_service = qdrant_service or QdrantService()
        self.bm25_indexer = bm25_indexer or BM25Indexer()

    async def search(self, request: HybridSearchRequest) -> HybridSearchResponse:
        """Execute a hybrid search with RRF fusion.

        Args:
            request: Full hybrid search parameters including query,
                     weights, limits, and filters.

        Returns:
            HybridSearchResponse with fused and ranked results.

        Raises:
            RetrievalError: If any step of the pipeline fails.
        """
        try:
            # Step 1: Embed the query
            logger.debug("Step 1: Embedding query '%s'", request.query[:100])
            embedding_result = await self.embedding_service.embed_query(request.query)
            query_vector = embedding_result.vector

            # Step 2: Vector search in Qdrant
            logger.debug("Step 2: Vector search in '%s' (top_k=%d)", request.collection, request.top_k_vector)
            vector_results = await self._vector_search(
                collection=request.collection,
                query_vector=query_vector,
                top_k=request.top_k_vector,
                score_threshold=request.score_threshold,
                filter_conditions=request.filter_conditions,
            )

            # Step 3: BM25 search
            logger.debug("Step 3: BM25 search (top_k=%d)", request.top_k_bm25)
            bm25_results = await self._bm25_search(
                query=request.query,
                top_k=request.top_k_bm25,
            )

            # Step 4: Reciprocal Rank Fusion
            logger.debug(
                "Step 4: RRF fusion (vector=%d, bm25=%d, top_k=%d)",
                len(vector_results),
                len(bm25_results),
                request.top_k,
            )
            fused = self._rrf_fuse(
                vector_results=vector_results,
                bm25_results=bm25_results,
                weight_vector=request.weight_vector,
                weight_bm25=request.weight_bm25,
                rrf_k=request.rrf_k,
            )

            # Step 5: Take top_k
            top_results = fused[: request.top_k]

            return HybridSearchResponse(
                results=top_results,
                query=request.query,
                total_vector=len(vector_results),
                total_bm25=len(bm25_results),
            )

        except RetrievalError:
            raise
        except Exception as e:
            raise RetrievalError(
                message=f"Hybrid search failed: {e}",
                error_code="HYBRID_SEARCH_FAILED",
                details={"query": request.query[:200]},
            ) from e

    async def _vector_search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[HybridSearchResultItem]:
        """Execute a vector search against Qdrant.

        Args:
            collection: Qdrant collection name.
            query_vector: The query embedding vector.
            top_k: Number of results to retrieve.
            score_threshold: Optional minimum score.
            filter_conditions: Optional filter conditions.

        Returns:
            A list of HybridSearchResultItem from vector search.
        """
        search_query = SearchQuery(
            collection=collection,
            vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            filter_conditions=filter_conditions,
        )

        response = await self.qdrant_service.search(search_query)

        results: list[HybridSearchResultItem] = []
        for point in response.results:
            payload: dict[str, Any] = point.payload or {}
            results.append(
                HybridSearchResultItem(
                    id=point.id,
                    score=0.0,  # Will be set during RRF
                    vector_score=point.score,
                    bm25_score=None,
                    payload=payload,
                    text=payload.get("text"),
                ),
            )

        return results

    async def _bm25_search(
        self,
        query: str,
        top_k: int,
    ) -> list[HybridSearchResultItem]:
        """Execute a BM25 keyword search.

        Args:
            query: The search query text.
            top_k: Number of results to retrieve.

        Returns:
            A list of HybridSearchResultItem from BM25 search.
        """
        if not self.bm25_indexer.is_built:
            # Try to load the persisted index (built by the chunking/scheduler process)
            await self.bm25_indexer.load()

        if not self.bm25_indexer.is_built:
            logger.debug("BM25 index not built — skipping BM25 branch")
            return []

        bm25_results = await self.bm25_indexer.search(query, top_k=top_k)

        results: list[HybridSearchResultItem] = []
        for bm25_result in bm25_results:
            results.append(
                HybridSearchResultItem(
                    id=bm25_result.doc_id,
                    score=0.0,  # Will be set during RRF
                    vector_score=None,
                    bm25_score=bm25_result.score,
                    payload={},
                    text=bm25_result.text,
                ),
            )

        return results

    @staticmethod
    def _rrf_fuse(
        vector_results: list[HybridSearchResultItem],
        bm25_results: list[HybridSearchResultItem],
        weight_vector: float = 0.5,
        weight_bm25: float = 0.5,
        rrf_k: int = 60,
    ) -> list[HybridSearchResultItem]:
        """Fuse two ranked result lists using Reciprocal Rank Fusion.

        Each result gets an RRF score based on its rank position in each
        list. The final fused score is a weighted combination:

            rrf_score(d) = w_v * 1/(k + rank_v(d)) + w_b * 1/(k + rank_b(d))

        Args:
            vector_results: Ranked results from vector search.
            bm25_results: Ranked results from BM25 search.
            weight_vector: Weight for vector search contributions.
            weight_bm25: Weight for BM25 search contributions.
            rrf_k: RRF constant (higher = more emphasis on top ranks).

        Returns:
            A list of HybridSearchResultItem sorted by fused score descending,
            with duplicates merged.
        """
        # Accumulate RRF scores keyed by result ID
        fusion_map: dict[str | int, HybridSearchResultItem] = {}

        # Process vector search results
        for rank, item in enumerate(vector_results):
            rrf_score = weight_vector * (1.0 / (rrf_k + rank + 1))
            existing = fusion_map.get(item.id)
            if existing:
                existing.score += rrf_score
            else:
                fusion_map[item.id] = HybridSearchResultItem(
                    id=item.id,
                    score=rrf_score,
                    vector_score=item.vector_score,
                    bm25_score=None,
                    payload=item.payload,
                    text=item.text,
                )

        # Process BM25 results
        for rank, item in enumerate(bm25_results):
            rrf_score = weight_bm25 * (1.0 / (rrf_k + rank + 1))
            existing = fusion_map.get(item.id)
            if existing:
                existing.score += rrf_score
                existing.bm25_score = item.bm25_score
                # Merge text if empty
                if not existing.text and item.text:
                    existing.text = item.text
            else:
                fusion_map[item.id] = HybridSearchResultItem(
                    id=item.id,
                    score=rrf_score,
                    vector_score=None,
                    bm25_score=item.bm25_score,
                    payload={},
                    text=item.text,
                )

        # Sort by fused score descending
        fused = list(fusion_map.values())
        fused.sort(key=lambda x: x.score, reverse=True)

        return fused
