"""
LangGraph pipeline nodes.

Each function is a LangGraph node that receives the current GraphState
and returns an updated state dict with the node's results.

All nodes are async and accept injected service dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import GraphState
from app.services.bm25.indexer import BM25Indexer
from app.services.embedding.service import EmbeddingService
from app.services.llm.litellm import LLMMessage, LiteLLMService, TaskType
from app.services.phobert.client import PhoBERTClient
from app.services.qdrant.service import QdrantService
from app.services.retrieval.hybrid import HybridSearchService
from app.services.retrieval.schemas import HybridSearchRequest, HybridSearchResultItem
from app.services.retrieval.reranker import RerankerService

logger = logging.getLogger(__name__)


def create_rewrite_query_node(llm_service: LiteLLMService) -> callable:
    """Create a node that rewrites the user query for better retrieval.

    Uses LLM to reformulate the query to be more search-friendly.

    Args:
        llm_service: LiteLLM service instance.

    Returns:
        An async function that takes GraphState and returns updated state.
    """

    async def rewrite_query(state: GraphState) -> dict[str, Any]:
        """Rewrite the user query for improved retrieval quality.

        Uses a lightweight LLM call to rephrase the query while
        preserving the original intent.

        Args:
            state: Current graph state with the original query.

        Returns:
            Updated state with rewritten_query set.
        """
        query = state.get("query", "")
        if not query:
            return {"rewritten_query": None, "error": "Empty query"}

        try:
            system_prompt = (
                "You are a query rewriting assistant. Your task is to rewrite "
                "the user's question into a more effective search query for "
                "retrieving relevant documents. Keep the rewrite concise and "
                "faithful to the original meaning."
            )

            response = await llm_service.generate_text(
                prompt=f"Original query: {query}\n\nRewritten query:",
                system_prompt=system_prompt,
                task_type=TaskType.QUERY_REWRITE,
                temperature=0.3,
                max_tokens=256,
            )

            rewritten = response.content.strip()
            if not rewritten:
                rewritten = query  # Fallback to original

            logger.debug("Query rewritten: '%s' → '%s'", query[:100], rewritten[:100])
            return {"rewritten_query": rewritten}

        except Exception as e:
            logger.warning("Query rewrite failed, using original: %s", e)
            return {"rewritten_query": query}

    return rewrite_query


def create_hybrid_search_node(
    hybrid_service: HybridSearchService | None = None,
    embedding_service: EmbeddingService | None = None,
    qdrant_service: QdrantService | None = None,
    bm25_indexer: BM25Indexer | None = None,
    collection: str | None = None,
) -> callable:
    """Create a node that performs hybrid search.

    Args:
        hybrid_service: Injected HybridSearchService.
        embedding_service: Injected EmbeddingService (used if hybrid_service is None).
        qdrant_service: Injected QdrantService (used if hybrid_service is None).
        bm25_indexer: Injected BM25Indexer (used if hybrid_service is None).
        collection: Qdrant collection name.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    search_service = hybrid_service or HybridSearchService(
        embedding_service=embedding_service or EmbeddingService(),
        qdrant_service=qdrant_service or QdrantService(),
        bm25_indexer=bm25_indexer or BM25Indexer(),
    )
    collection_name = collection or "documents"

    async def hybrid_search(state: GraphState) -> dict[str, Any]:
        """Execute hybrid search using the (rewritten) query.

        Args:
            state: Current graph state with query or rewritten_query.

        Returns:
            Updated state with search_results.
        """
        query = state.get("rewritten_query") or state.get("query", "")
        if not query:
            return {"search_results": [], "error": "Empty query for search"}

        try:
            request = HybridSearchRequest(
                query=query,
                collection=collection_name,
                top_k=10,
                top_k_vector=20,
                top_k_bm25=20,
            )

            response = await search_service.search(request)

            # Convert results to serializable dicts for graph state
            results = [
                {
                    "id": str(item.id),
                    "score": item.score,
                    "vector_score": item.vector_score,
                    "bm25_score": item.bm25_score,
                    "text": item.text,
                    "payload": item.payload,
                }
                for item in response.results
            ]

            logger.debug("Hybrid search returned %d results", len(results))
            return {"search_results": results}

        except Exception as e:
            logger.error("Hybrid search failed: %s", e)
            return {"search_results": [], "error": str(e)}

    return hybrid_search


def create_phobert_classify_node(
    phobert_client: PhoBERTClient | None = None,
) -> callable:
    """Create a node that classifies the query using PhoBERT.

    Args:
        phobert_client: Injected PhoBERT client.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    client = phobert_client or PhoBERTClient()

    async def phobert_classify(state: GraphState) -> dict[str, Any]:
        """Classify the query or search results using PhoBERT.

        Args:
            state: Current graph state with query and search results.

        Returns:
            Updated state with classification result.
        """
        query = state.get("query", "")
        if not query:
            return {"classification": None}

        try:
            classification = await client.predict(query)
            logger.debug("PhoBERT classification: %s", classification)
            return {"classification": classification}

        except Exception as e:
            logger.warning("PhoBERT classification failed (may not be deployed): %s", e)
            return {"classification": None}

    return phobert_classify


def create_rerank_node(
    reranker_service: RerankerService | None = None,
) -> callable:
    """Create a node that reranks the search results.

    Args:
        reranker_service: Injected RerankerService.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    reranker = reranker_service or RerankerService()

    async def rerank(state: GraphState) -> dict[str, Any]:
        """Rerank the hybrid search results.

        Args:
            state: Current graph state with search_results.

        Returns:
            Updated state with reranked_results.
        """
        search_results = state.get("search_results", [])
        if not search_results:
            return {"reranked_results": []}

        query = state.get("query", "")

        try:
            candidates = [
                HybridSearchResultItem(
                    id=item["id"],
                    score=item.get("score", 0.0),
                    vector_score=item.get("vector_score"),
                    bm25_score=item.get("bm25_score"),
                    text=item.get("text"),
                    payload=item.get("payload", {}),
                )
                for item in search_results
            ]

            reranked = await reranker.rerank_with_scores(
                query=query,
                candidates=candidates,
                top_k=10,
            )

            results = [
                {
                    "id": str(item.id),
                    "score": item.score,
                    "vector_score": item.vector_score,
                    "bm25_score": item.bm25_score,
                    "text": item.text,
                    "payload": item.payload,
                }
                for item in reranked
            ]

            return {"reranked_results": results}

        except Exception as e:
            logger.warning("Reranking failed, using original order: %s", e)
            return {"reranked_results": search_results}

    return rerank


def create_context_builder_node(
    max_chars: int = 8000,
) -> callable:
    """Create a node that builds context from search results for the LLM.

    Args:
        max_chars: Maximum characters for the context string.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    async def build_context(state: GraphState) -> dict[str, Any]:
        """Format search results into a context string for the LLM.

        Args:
            state: Current graph state with reranked_results.

        Returns:
            Updated state with context string.
        """
        results = state.get("reranked_results") or state.get("search_results", [])
        if not results:
            return {"context": "No relevant documents found."}

        context_parts: list[str] = []
        char_count = 0

        for i, result in enumerate(results, 1):
            text = result.get("text") or ""
            if not text:
                continue

            snippet = f"[{i}] {text.strip()}"
            if char_count + len(snippet) > max_chars:
                # Truncate to fit
                remaining = max_chars - char_count
                if remaining > 50:
                    context_parts.append(snippet[:remaining] + "...")
                break

            context_parts.append(snippet)
            char_count += len(snippet)

        context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."
        return {"context": context}

    return build_context


def create_llm_answer_node(
    llm_service: LiteLLMService,
    system_prompt: str | None = None,
) -> callable:
    """Create a node that generates the final answer using LLM.

    Args:
        llm_service: LiteLLM service instance.
        system_prompt: Optional custom system prompt for answer generation.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    default_system_prompt = (
        "Bạn là trợ lý AI chuyên nghiệp. Dựa vào ngữ cảnh được cung cấp, "
        "hãy trả lời câu hỏi của người dùng một cách chính xác và hữu ích.\n\n"
        "NGUYÊN TẮC:\n"
        "1. Chỉ trả lời dựa trên thông tin trong ngữ cảnh được cung cấp.\n"
        "2. Nếu ngữ cảnh không có đủ thông tin, hãy nói rõ là không tìm thấy.\n"
        "3. KHÔNG bịa đặt thông tin hoặc suy luận quá xa.\n"
        "4. Trả lời bằng tiếng Việt, ngắn gọn và đúng trọng tâm.\n"
        "5. Trích dẫn nguồn nếu có thể (ví dụ: [1], [2])."
    )

    prompt_template = default_system_prompt if system_prompt is None else system_prompt

    async def llm_answer(state: GraphState) -> dict[str, Any]:
        """Generate the final answer using the LLM.

        Args:
            state: Current graph state with context and query.

        Returns:
            Updated state with the final answer.
        """
        query = state.get("query", "")
        context = state.get("context", "")

        if not query:
            return {"answer": "No question provided.", "error": None}

        messages = [
            LLMMessage(
                role="system",
                content=prompt_template,
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Ngữ cảnh:\n{context}\n\n"
                    f"Câu hỏi: {query}\n\n"
                    f"Trả lời:"
                ),
            ),
        ]

        try:
            response = await llm_service.chat(
                messages=messages,
                task_type=TaskType.CHAT,
                temperature=0.7,
                max_tokens=2048,
            )

            answer = response.content.strip()

            if not answer:
                answer = "Xin lỗi, tôi không thể tạo câu trả lời cho câu hỏi này."

            return {"answer": answer}

        except Exception as e:
            error_msg = f"Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời: {e}"
            logger.error("LLM answer generation failed: %s", e)
            return {"answer": error_msg, "error": str(e)}

    return llm_answer
