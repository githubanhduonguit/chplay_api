"""
Embedding service.

Provides the main embedding operations:
- embed: embed a single string or list of strings
- embed_query: embed a query string (with special prefix for BGE models)
- embed_batch: batch embedding with automatic chunking
- All operations available in async variants
- Retry + timeout applied automatically
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.exceptions import EmbeddingError
from app.services.embedding.client import EmbeddingHTTPClient
from app.services.embedding.retry import default_retry_strategy, with_timeout
from app.services.embedding.schemas import EmbeddingResult

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings using BAAI/bge-m3.

    Features:
    - Single text and batch embedding
    - Query-specific embedding with BGE instruction prefix
    - Automatic batch splitting for large inputs
    - Retry with exponential backoff
    - Timeout protection
    - Async-first design
    """

    def __init__(self, client: EmbeddingHTTPClient | None = None) -> None:
        self.client = client or EmbeddingHTTPClient()

    # ── Public API ───────────────────────────────────────────────────

    @with_timeout()
    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            An EmbeddingResult containing the vector and metadata.

        Raises:
            EmbeddingError: If the embedding operation fails after retries.
        """
        results = await self._embed_with_retry([text])
        return results[0]

    @with_timeout()
    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a query string with the BGE instruction prefix.

        For BAAI/bge-m3, the query is prefixed with an instruction
        to improve retrieval quality: 'Represent this sentence for searching relevant passages: '

        Args:
            query: The query text to embed.

        Returns:
            An EmbeddingResult containing the query vector.

        Raises:
            EmbeddingError: If the embedding operation fails.
        """
        prefixed_query = self._apply_query_prefix(query)
        results = await self._embed_with_retry([prefixed_query])
        return results[0]

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[EmbeddingResult]:
        """Embed multiple texts in batches.

        Automatically splits large lists into smaller batches
        to avoid overwhelming the embedding service.
        Each batch has its own timeout budget.

        Args:
            texts: List of texts to embed.
            batch_size: Maximum number of texts per batch.
                       Defaults to EMBEDDING_BATCH_SIZE setting.

        Returns:
            A list of EmbeddingResult objects, one per input text.

        Raises:
            EmbeddingError: If the embedding operation fails.
        """
        if not texts:
            return []

        batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        all_results: list[EmbeddingResult] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.debug("Embedding batch %d/%d (size=%d)", i // batch_size + 1, (len(texts) + batch_size - 1) // batch_size, len(batch))  # fmt: skip
            # Each batch has its own timeout
            result = await self._embed_batch_with_timeout(batch)
            all_results.extend(result)

        return all_results

    @with_timeout()
    async def _embed_batch_with_timeout(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a single batch with timeout protection."""
        return await self._embed_with_retry(texts)

    # ── Internal API ─────────────────────────────────────────────────

    async def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
        """Call the embedding API with retry logic.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of EmbeddingResult objects.

        Raises:
            EmbeddingError: If all retry attempts fail.
        """
        try:
            async for attempt in default_retry_strategy():
                with attempt:
                    response = await self.client.embed(texts)
                    return self._convert_response(response, texts)
        except Exception as e:
            if isinstance(e, EmbeddingError):
                raise
            raise EmbeddingError(
                message=f"Embedding failed after retries: {e}",
                error_code="EMBEDDING_FAILED",
                details={"text_count": len(texts)},
            ) from e

    def _convert_response(
        self,
        response: Any,  # noqa: ANN401
        original_texts: list[str],
    ) -> list[EmbeddingResult]:
        """Convert the API response to a list of EmbeddingResult.

        Args:
            response: The EmbeddingResponse from the API.
            original_texts: The original texts sent (for count validation).

        Returns:
            A list of EmbeddingResult objects.

        Raises:
            EmbeddingError: If the response has a mismatched count.
        """
        from app.services.embedding.schemas import EmbeddingResponse as ER

        if not isinstance(response, ER):
            raise EmbeddingError(
                message="Invalid embedding response type",
                error_code="EMBEDDING_INVALID_RESPONSE",
            )

        data_list = response.data
        if len(data_list) != len(original_texts):
            raise EmbeddingError(
                message=(
                    f"Embedding response count mismatch: "
                    f"expected {len(original_texts)}, got {len(data_list)}"
                ),
                error_code="EMBEDDING_COUNT_MISMATCH",
            )

        results = []
        for item in data_list:
            results.append(
                EmbeddingResult(
                    vector=item.embedding,
                    index=item.index,
                    tokens_used=response.usage.total_tokens,
                ),
            )

        return results

    def _apply_query_prefix(self, query: str) -> str:
        """Apply the BGE query instruction prefix.

        BAAI/bge-m3 uses a specific instruction prefix for queries
        to distinguish them from documents during retrieval:
        'Represent this sentence for searching relevant passages: '.

        The prefix is BGE-specific and skipped for other providers
        (e.g. Google Gemini embeddings), where query and document
        embeddings are compared directly.

        Args:
            query: The raw query string.

        Returns:
            The query string with the BGE instruction prefix (if applicable).
        """
        if self.client.is_gemini:
            return query
        return (
            "Represent this sentence for searching relevant passages: " + query
        )
