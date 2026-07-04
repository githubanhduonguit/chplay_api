"""
Reranker service.

Provides reranking capabilities for search results. Currently
implements a pass-through reranker that preserves existing scores.
This can be replaced with a cross-encoder model (e.g., BGE-reranker)
or a more sophisticated reranking algorithm in the future.

Planned integrations:
- BAAI/bge-reranker-v2-m3 (cross-encoder via API)
- Cohere Rerank API
- Custom fine-tuned reranker
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import RetrievalError
from app.services.retrieval.schemas import (
    HybridSearchResultItem,
    RerankRequest,
    RerankResponse,
)

logger = logging.getLogger(__name__)


class RerankerService:
    """Service for reranking search results.

    Currently implements a pass-through reranker that returns
    results in their original order. When a reranker model API
    becomes available, this service can be extended to call it.

    The reranker accepts any list of result items and returns
    them with a rerank_score that can be used alongside the
    original search scores.
    """

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        """Rerank a list of candidate results.

        Current implementation: pass-through with identity scoring.
        Future: send candidates to a cross-encoder reranker model.

        Args:
            request: Rerank request containing query and candidates.

        Returns:
            RerankResponse with (re)ranked results.
        """
        if not request.candidates:
            return RerankResponse(results=[], query=request.query)

        try:
            # Pass-through: preserve original order with rerank_score = original score
            reranked = list(request.candidates[: request.top_k])
            return RerankResponse(results=reranked, query=request.query)

        except Exception as e:
            raise RetrievalError(
                message=f"Reranking failed: {e}",
                error_code="RERANK_FAILED",
                details={"query": request.query[:200], "candidate_count": len(request.candidates)},
            ) from e

    async def rerank_with_scores(
        self,
        query: str,
        candidates: list[HybridSearchResultItem],
        top_k: int = 10,
    ) -> list[HybridSearchResultItem]:
        """Rerank candidates and return the top-k items.

        Current implementation: pass-through that preserves the
        existing order and scores.

        Args:
            query: The original search query.
            candidates: List of candidate results to rerank.
            top_k: Maximum number of results to return.

        Returns:
            The top-k candidate items (reranked ordering in future).
        """
        if not candidates:
            return []

        return list(candidates[:top_k])
