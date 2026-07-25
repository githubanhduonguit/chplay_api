"""
Graph service — high-level entry point for the RAG pipeline.

Provides a clean API for running the full LangGraph pipeline:
    GraphService.run(query) → answer

Handles graph construction (lazy build), state initialization,
and result extraction.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.graph.graph import GraphBuilder
from app.graph.state import GraphState
from app.services.bm25.indexer import BM25Indexer
from app.services.embedding.service import EmbeddingService
from app.services.llm.litellm import LiteLLMService
from app.services.phobert.client import PhoBERTClient
from app.services.qdrant.service import QdrantService
from app.services.retrieval.hybrid import HybridSearchService
from app.services.retrieval.reranker import RerankerService

logger = logging.getLogger(__name__)


class GraphQueryResult:
    """Result from running the RAG pipeline.

    Attributes:
        query: The original user query.
        answer: The generated answer.
        context: The context used for generation.
        classification: PhoBERT classification result (if available).
        metadata: Run metadata (duration, node timings, etc.).
        error: Error message if the pipeline failed.
    """

    def __init__(
        self,
        query: str,
        answer: str | None = None,
        context: str | None = None,
        classification: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.query = query
        self.answer = answer
        self.context = context
        self.classification = classification
        self.metadata = metadata or {}
        self.error = error


class GraphService:
    """High-level service for running the RAG pipeline.

    Lazy-builds the LangGraph on first use and provides a simple
    run(query) interface for external callers.

    Args:
        llm_service: LiteLLM service for LLM calls.
        hybrid_service: HybridSearchService for retrieval.
        embedding_service: EmbeddingService for query embedding.
        qdrant_service: QdrantService for vector search.
        bm25_indexer: BM25Indexer for keyword search.
        phobert_client: PhoBERT client for classification.
        reranker_service: RerankerService for result reranking.
        collection: Qdrant collection name.
    """

    def __init__(
        self,
        llm_service: LiteLLMService | None = None,
        hybrid_service: HybridSearchService | None = None,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        bm25_indexer: BM25Indexer | None = None,
        phobert_client: PhoBERTClient | None = None,
        reranker_service: RerankerService | None = None,
        collection: str | None = None,
    ) -> None:
        self.graph_builder = GraphBuilder(
            llm_service=llm_service,
            hybrid_service=hybrid_service,
            embedding_service=embedding_service,
            qdrant_service=qdrant_service,
            bm25_indexer=bm25_indexer,
            phobert_client=phobert_client,
            reranker_service=reranker_service,
            collection=collection,
        )
        self._compiled_graph: Any = None

    async def run(
        self,
        query: str,
        metadata: dict[str, Any] | None = None,
    ) -> GraphQueryResult:
        """Run the full RAG pipeline for a user query.

        Args:
            query: The user's question or search query.
            metadata: Optional metadata for tracing/logging.

        Returns:
            A GraphQueryResult with the answer and pipeline metadata.
        """
        start_time = time.monotonic()

        if not query or not query.strip():
            return GraphQueryResult(
                query=query,
                answer="Vui lòng nhập câu hỏi.",
                error="Empty query",
            )

        # Lazy-build on first run
        if self._compiled_graph is None:
            self._compiled_graph = self.graph_builder.build()

        # Initialize state
        initial_state: GraphState = {
            "query": query,
            "rewritten_query": None,
            "search_results": None,
            "classification": None,
            "reranked_results": None,
            "context": None,
            "answer": None,
            "error": None,
            "metadata": metadata,
        }

        try:
            # Run the graph
            result_state = await self._compiled_graph.ainvoke(initial_state)

            duration = time.monotonic() - start_time
            logger.info(
                "RAG pipeline completed in %.2fs for query: '%s'",
                duration,
                query[:100],
            )

            return GraphQueryResult(
                query=query,
                answer=result_state.get("answer"),
                context=result_state.get("context"),
                classification=result_state.get("classification"),
                metadata={
                    "duration_seconds": round(duration, 3),
                    "rewritten_query": result_state.get("rewritten_query"),
                    "num_results": len(result_state.get("reranked_results") or result_state.get("search_results") or []),
                    **({"custom": metadata} if metadata else {}),
                },
                error=result_state.get("error"),
            )

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(
                "RAG pipeline failed after %.2fs: %s",
                duration,
                e,
                exc_info=True,
            )

            return GraphQueryResult(
                query=query,
                answer=f"Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi: {e}",
                error=f"Pipeline error: {e}",
                metadata={"duration_seconds": round(duration, 3)},
            )
