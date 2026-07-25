"""
LangGraph RAG pipeline graph builder.

Constructs the complete RAG pipeline graph with:
    START → Rewrite Query → Hybrid Search → PhoBERT Classification
    → Rerank → Context Builder → LLM Answer → END

Each node is injected with its required service dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    create_context_builder_node,
    create_hybrid_search_node,
    create_llm_answer_node,
    create_phobert_classify_node,
    create_rerank_node,
    create_rewrite_query_node,
)
from app.graph.state import GraphState
from app.services.bm25.indexer import BM25Indexer
from app.services.embedding.service import EmbeddingService
from app.services.llm.litellm import LiteLLMService
from app.services.phobert.client import PhoBERTClient
from app.services.qdrant.service import QdrantService
from app.services.retrieval.hybrid import HybridSearchService
from app.services.retrieval.reranker import RerankerService

logger = logging.getLogger(__name__)


# ── Node name constants ──────────────────────────────────────────────

NODE_REWRITE_QUERY = "rewrite_query"
NODE_HYBRID_SEARCH = "hybrid_search"
NODE_PHOBERT_CLASSIFY = "phobert_classify"
NODE_RERANK = "rerank"
NODE_CONTEXT_BUILDER = "context_builder"
NODE_LLM_ANSWER = "llm_answer"


class GraphBuilder:
    """Builds and compiles the LangGraph RAG pipeline.

    Injects service dependencies into each node so the graph
    is self-contained and testable with mock services.

    Attributes:
        llm_service: LiteLLM service for query rewrite and answer generation.
        hybrid_service: HybridSearchService for retrieval.
        embedding_service: EmbeddingService (fallback for hybrid search).
        qdrant_service: QdrantService (fallback for hybrid search).
        bm25_indexer: BM25Indexer (fallback for hybrid search).
        phobert_client: PhoBERT client for classification.
        reranker_service: RerankerService for result reranking.
        collection: Qdrant collection name for search.
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
        self.llm_service = llm_service or LiteLLMService()
        self.hybrid_service = hybrid_service
        self.embedding_service = embedding_service or EmbeddingService()
        self.qdrant_service = qdrant_service or QdrantService()
        self.bm25_indexer = bm25_indexer or BM25Indexer()
        self.phobert_client = phobert_client
        self.reranker_service = reranker_service or RerankerService()
        self.collection = collection

        self._graph: StateGraph | None = None
        self._compiled: Any = None

    def build(self) -> Any:
        """Build the LangGraph state graph with all nodes and edges.

        Returns:
            The compiled graph application ready for invocation.
        """
        # Create nodes with injected dependencies
        nodes = {
            NODE_REWRITE_QUERY: create_rewrite_query_node(self.llm_service),
            NODE_HYBRID_SEARCH: create_hybrid_search_node(
                hybrid_service=self.hybrid_service,
                embedding_service=self.embedding_service,
                qdrant_service=self.qdrant_service,
                bm25_indexer=self.bm25_indexer,
                collection=self.collection,
            ),
            NODE_PHOBERT_CLASSIFY: create_phobert_classify_node(self.phobert_client),
            NODE_RERANK: create_rerank_node(self.reranker_service),
            NODE_CONTEXT_BUILDER: create_context_builder_node(),
            NODE_LLM_ANSWER: create_llm_answer_node(self.llm_service),
        }

        # Build graph
        workflow = StateGraph(GraphState)

        # Add all nodes
        for name, node_fn in nodes.items():
            workflow.add_node(name, node_fn)

        # Define edges
        workflow.set_entry_point(NODE_REWRITE_QUERY)

        workflow.add_edge(NODE_REWRITE_QUERY, NODE_HYBRID_SEARCH)
        workflow.add_edge(NODE_HYBRID_SEARCH, NODE_PHOBERT_CLASSIFY)
        workflow.add_edge(NODE_PHOBERT_CLASSIFY, NODE_RERANK)
        workflow.add_edge(NODE_RERANK, NODE_CONTEXT_BUILDER)
        workflow.add_edge(NODE_CONTEXT_BUILDER, NODE_LLM_ANSWER)
        workflow.add_edge(NODE_LLM_ANSWER, END)

        self._graph = workflow
        self._compiled = workflow.compile()

        logger.info(
            "LangGraph RAG pipeline built: "
            "%s → %s → %s → %s → %s → %s → END",
            NODE_REWRITE_QUERY,
            NODE_HYBRID_SEARCH,
            NODE_PHOBERT_CLASSIFY,
            NODE_RERANK,
            NODE_CONTEXT_BUILDER,
            NODE_LLM_ANSWER,
        )

        return self._compiled

    def get_graph(self) -> StateGraph | None:
        """Get the uncompiled StateGraph (useful for visualization)."""
        return self._graph

    def get_compiled_graph(self) -> Any:
        """Get the compiled graph application.

        Returns:
            The compiled graph if built, otherwise None.
        """
        return self._compiled


# ── Convenience factory ──────────────────────────────────────────────


def create_rag_pipeline(
    llm_service: LiteLLMService | None = None,
    hybrid_service: HybridSearchService | None = None,
    embedding_service: EmbeddingService | None = None,
    qdrant_service: QdrantService | None = None,
    bm25_indexer: BM25Indexer | None = None,
    phobert_client: PhoBERTClient | None = None,
    reranker_service: RerankerService | None = None,
    collection: str | None = None,
) -> Any:
    """Create a compiled RAG pipeline graph.

    Convenience function that builds the full LangGraph pipeline
    with default or injected service dependencies.

    Args:
        llm_service: LiteLLM service instance.
        hybrid_service: HybridSearchService instance.
        embedding_service: EmbeddingService instance.
        qdrant_service: QdrantService instance.
        bm25_indexer: BM25Indexer instance.
        phobert_client: PhoBERTClient instance.
        reranker_service: RerankerService instance.
        collection: Qdrant collection name.

    Returns:
        A compiled LangGraph application.
    """
    builder = GraphBuilder(
        llm_service=llm_service,
        hybrid_service=hybrid_service,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
        bm25_indexer=bm25_indexer,
        phobert_client=phobert_client,
        reranker_service=reranker_service,
        collection=collection,
    )
    return builder.build()
