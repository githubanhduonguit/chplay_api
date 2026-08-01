"""
LangGraph pipeline nodes.

Each function is a LangGraph node that receives the current GraphState
and returns an updated state dict with the node's results.

All nodes are async and accept injected service dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.graph.state import GraphState
from app.services.bm25.indexer import BM25Indexer
from app.services.embedding.service import EmbeddingService
from app.services.llm.litellm import LLMMessage, LiteLLMService, TaskType
from app.services.phobert.client import PhoBERTClient
from app.services.qdrant.service import QdrantService
from app.services.retrieval.hybrid import HybridSearchService
from app.services.retrieval.schemas import HybridSearchRequest, HybridSearchResultItem
from app.services.retrieval.reranker import RerankerService
from app.services.web_search.schemas import WebSearchRequest, WebSearchResult
from app.services.web_search.service import WebSearchService

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


# ── Web Search Nodes ──────────────────────────────────────────────────


def create_web_search_decision_node(
    min_rag_score: float | None = None,
) -> callable:
    """Create a node that decides whether web search is needed.

    The decision is based on:
    1. RAG search results are empty → need web search.
    2. Context builder returned "No relevant documents found." → need web search.
    3. Top RAG result score is below min_rag_score → need web search.
    4. Query explicitly needs external/real-time info (detected by certain keywords).

    Args:
        min_rag_score: Minimum RAG score threshold (default from settings).

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    threshold = min_rag_score if min_rag_score is not None else settings.WEB_SEARCH_MIN_RAG_SCORE

    async def decide_web_search(state: GraphState) -> dict[str, Any]:
        """Decide if web search is needed based on RAG results.

        Args:
            state: Current graph state with search_results, reranked_results,
                   context, classification, and metadata.

        Returns:
            Updated state with web_search_needed and web_search_reason.
        """
        query = state.get("query", "")
        reranked = state.get("reranked_results") or state.get("search_results", [])
        context = state.get("context", "")
        classification = state.get("classification", {})
        metadata = state.get("metadata", {}) or {}

        # Skip web search for internal/ticket-specific queries
        if _should_skip_web_search(query, classification, metadata):
            return {
                "web_search_needed": False,
                "web_search_reason": "Query relates to internal data (reviews, tickets, DB).",
            }

        # Case 1: No RAG results at all
        if not reranked:
            logger.debug("Web search decision: NEEDED (no RAG results)")
            return {
                "web_search_needed": True,
                "web_search_reason": "RAG search returned no results.",
            }

        # Case 2: Context builder found nothing relevant
        if context == "No relevant documents found.":
            logger.debug("Web search decision: NEEDED (RAG context empty)")
            return {
                "web_search_needed": True,
                "web_search_reason": "RAG context builder found no relevant documents.",
            }

        # Case 3: Top score below threshold
        top_scores = [r.get("score", 0.0) for r in reranked[:3] if r.get("score") is not None]
        if top_scores and max(top_scores) < threshold:
            logger.debug(
                "Web search decision: NEEDED (top RAG score %.3f < threshold %.3f)",
                max(top_scores),
                threshold,
            )
            return {
                "web_search_needed": True,
                "web_search_reason": f"Top RAG score ({max(top_scores):.3f}) below threshold ({threshold:.3f}).",
            }

        # Case 4: RAG has good results — no web search needed
        logger.debug(
            "Web search decision: NOT needed (RAG has %d results with sufficient scores)",
            len(reranked),
        )
        return {
            "web_search_needed": False,
            "web_search_reason": "RAG search has sufficient results.",
        }

    return decide_web_search


def _should_skip_web_search(
    query: str,
    classification: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> bool:
    """Check if web search should be skipped for this query.

    Skips web search for queries that are clearly about internal data
    such as app reviews, tickets, or database-specific information.

    Args:
        query: The user's query.
        classification: PhoBERT classification result.
        metadata: Additional metadata from the caller.

    Returns:
        True if web search should be skipped.
    """
    query_lower = query.lower()

    # Keywords indicating internal/ticket/review queries
    internal_keywords = [
        "review", "ticket", "bug", "app version", "phiên bản",
        "lỗi", "khiếu nại", "báo cáo", "rating", "đánh giá",
        "comment", "bình luận", "reply", "trả lời",
        "status", "trạng thái", "when will", "bao giờ",
    ]

    for keyword in internal_keywords:
        if keyword in query_lower:
            logger.debug("Skipping web search: query contains internal keyword '%s'", keyword)
            return True

    # Check classification if available
    if classification:
        label = classification.get("label", "")
        if label in ("bug_report", "feature_request", "complaint", "support_ticket"):
            logger.debug("Skipping web search: classified as '%s'", label)
            return True

    return False


def create_web_search_node(
    web_search_service: WebSearchService | None = None,
) -> callable:
    """Create a node that performs web search.

    Only calls the web search provider when:
    - web_search_needed is True
    - WEB_SEARCH_ENABLED is True

    Args:
        web_search_service: Injected WebSearchService.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    search_service = web_search_service or WebSearchService()

    async def web_search(state: GraphState) -> dict[str, Any]:
        """Execute web search if needed.

        Args:
            state: Current graph state with query/rewritten_query
                   and web_search_needed flag.

        Returns:
            Updated state with web_search_results.
        """
        web_search_needed = state.get("web_search_needed", False)
        if not web_search_needed:
            return {"web_search_results": []}

        # Check if service is ready
        if not search_service.is_ready:
            logger.warning("Web search requested but service is not enabled/configured")
            return {"web_search_results": []}

        query = state.get("rewritten_query") or state.get("query", "")
        if not query:
            logger.warning("Web search requested but no query available")
            return {"web_search_results": []}

        try:
            request = WebSearchRequest(
                query=query,
                top_k=settings.WEB_SEARCH_TOP_K,
                language=settings.WEB_SEARCH_LANGUAGE,
                safe_search=settings.WEB_SEARCH_SAFE_SEARCH,
                timeout=settings.WEB_SEARCH_TIMEOUT,
            )

            response = await search_service.search(request)

            # Convert to serializable dicts
            results = [
                {
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet,
                    "source": item.source,
                    "score": item.score,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                }
                for item in response.results
            ]

            logger.debug(
                "Web search returned %d results for '%s'",
                len(results),
                query[:100],
            )
            return {"web_search_results": results}

        except Exception as e:
            logger.error("Web search failed: %s", e)
            return {"web_search_results": []}

    return web_search


def create_web_context_builder_node(
    max_chars: int = 4000,
) -> callable:
    """Create a node that builds formatted web context from search results.

    Each result is formatted as:
        [W<N>] <title>
        URL: <url>
        <snippet>

    Args:
        max_chars: Maximum characters for web context.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    async def build_web_context(state: GraphState) -> dict[str, Any]:
        """Format web search results into a context string.

        Args:
            state: Current graph state with web_search_results.

        Returns:
            Updated state with web_context and citations.
        """
        results = state.get("web_search_results", [])
        if not results:
            return {"web_context": "", "citations": []}

        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        char_count = 0

        for i, result in enumerate(results, 1):
            title = result.get("title", "Không có tiêu đề")
            url = result.get("url", "")
            snippet = result.get("snippet", "")

            # Skip results without URL or very short snippets
            if not url or len(snippet.strip()) < 10:
                continue

            block = f"[W{i}] {title}\nURL: {url}\n{snippet}"

            if char_count + len(block) > max_chars:
                remaining = max_chars - char_count
                if remaining > 100:
                    context_parts.append(block[:remaining] + "...")
                    citations.append({"index": i, "title": title, "url": url})
                break

            context_parts.append(block)
            char_count += len(block)
            citations.append({"index": i, "title": title, "url": url})

        web_context = "\n\n".join(context_parts) if context_parts else ""

        logger.debug("Web context built with %d citations", len(citations))
        return {"web_context": web_context, "citations": citations}

    return build_web_context


def create_merge_context_node() -> callable:
    """Create a node that merges RAG context and web context.

    Priority: RAG context first, then web context.
    Sets source_mode to indicate which sources are used.

    Returns:
        An async function that takes GraphState and returns updated state.
    """
    async def merge_context(state: GraphState) -> dict[str, Any]:
        """Merge RAG and web context into a single context string.

        Args:
            state: Current graph state with context and web_context.

        Returns:
            Updated state with merged_context and source_mode.
        """
        rag_context = state.get("context", "")
        web_context = state.get("web_context", "")
        has_rag = bool(rag_context and rag_context != "No relevant documents found.")
        has_web = bool(web_context and web_context.strip())

        # Determine source mode
        if has_rag and has_web:
            source_mode = "rag_plus_web"
        elif has_rag:
            source_mode = "rag_only"
        elif has_web:
            source_mode = "web_only"
        else:
            source_mode = "none"

        # Build merged context
        merged_parts: list[str] = []

        if has_rag:
            merged_parts.append("=== NGUỒN NỘI BỘ (DỮ LIỆU APP) ===\n")
            merged_parts.append(rag_context)

        if has_web:
            merged_parts.append("\n\n=== NGUỒN WEB ===\n")
            merged_parts.append(web_context)

        if not merged_parts:
            merged_context = "Không tìm thấy thông tin liên quan từ cả nguồn nội bộ và web."
        else:
            merged_context = "\n".join(merged_parts)

        logger.debug(
            "Context merged: source_mode=%s, rag_len=%d, web_len=%d",
            source_mode,
            len(rag_context) if has_rag else 0,
            len(web_context) if has_web else 0,
        )

        return {
            "merged_context": merged_context,
            "source_mode": source_mode,
        }

    return merge_context


# ── LLM Answer Node ───────────────────────────────────────────────────


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
        "Bạn là trợ lý AI chuyên nghiệp hỗ trợ người dùng về ứng dụng trên CH Play. "
        "Dựa vào ngữ cảnh được cung cấp, hãy trả lời câu hỏi của người dùng một cách chính xác và hữu ích.\n\n"
        "NGUYÊN TẮC:\n"
        "1. Ưu tiên thông tin từ NGUỒN NỘI BỘ (dữ liệu app, review, ticket) nếu có.\n"
        "2. Chỉ dùng thông tin từ NGUỒN WEB khi nguồn nội bộ không đủ dữ liệu.\n"
        "3. Nếu cả hai nguồn đều không có thông tin đủ tin cậy, hãy nói rõ là không tìm thấy.\n"
        "4. KHÔNG bịa đặt thông tin hoặc suy luận quá xa.\n"
        "5. Trả lời bằng tiếng Việt, ngắn gọn và đúng trọng tâm.\n"
        "6. Trích dẫn nguồn rõ ràng:\n"
        "   - Dùng [1], [2] cho thông tin từ nguồn nội bộ (RAG).\n"
        "   - Dùng [W1], [W2] cho thông tin từ nguồn web.\n"
        "   - Khi trích dẫn nguồn web, luôn kèm URL đầy đủ.\n"
        "7. Nếu câu trả lời CHỈ dựa trên nguồn web, hãy nói rõ: "
        "'Lưu ý: Thông tin này được lấy từ nguồn web, không phải dữ liệu nội bộ của ứng dụng.'\n"
        "8. Nếu nguồn web mâu thuẫn với nguồn nội bộ, ưu tiên nguồn nội bộ và giải thích sự khác biệt."
    )

    prompt_template = default_system_prompt if system_prompt is None else system_prompt

    async def llm_answer(state: GraphState) -> dict[str, Any]:
        """Generate the final answer using the LLM.

        Args:
            state: Current graph state with merged_context (or context) and query.

        Returns:
            Updated state with the final answer.
        """
        query = state.get("query", "")
        # Use merged_context if available, otherwise fall back to regular context
        context = state.get("merged_context") or state.get("context", "")
        source_mode = state.get("source_mode", "rag_only")

        if not query:
            return {"answer": "No question provided.", "error": None}

        # Build user prompt with context
        if source_mode == "none":
            user_content = (
                f"Câu hỏi: {query}\n\n"
                f"Xin lỗi, không tìm thấy thông tin liên quan từ cả nguồn nội bộ và web. "
                f"Hãy trả lời rằng bạn không thể trả lời câu hỏi này vì thiếu thông tin."
            )
        else:
            user_content = (
                f"Ngữ cảnh:\n{context}\n\n"
                f"Câu hỏi: {query}\n\n"
                f"Trả lời:"
            )

        messages = [
            LLMMessage(
                role="system",
                content=prompt_template,
            ),
            LLMMessage(
                role="user",
                content=user_content,
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
