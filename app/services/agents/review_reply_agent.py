"""Agent for orchestrating review reply generation.

Acts as the middle layer between the job and the LLM service:
1. Normalizes and validates input.
2. Calls Gemini via GeminiReviewReplyService.
3. Validates the generated output.
4. Provides RAG + Web search context retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.db.models.comment import Comment
from app.services.llm.gemini import (
    GeminiReplyError,
    GeminiReviewReplyService,
)
from app.services.web_search.schemas import WebSearchRequest
from app.services.web_search.service import WebSearchService

logger = logging.getLogger(__name__)


@dataclass
class ReviewReplyInput:
    """Normalized input for the review reply agent."""

    content: str
    rating: int | None = None
    app_version: str | None = None
    overall_sentiment: str | None = None
    review_id: int | None = None


@dataclass
class ReviewReplyResult:
    """Result of the review reply generation."""

    success: bool
    reply: str | None = None
    error: str | None = None
    web_search_used: bool = False
    source_mode: str | None = None


class ReviewReplyAgent:
    """Agent that orchestrates review reply generation.

    Args:
        llm_service: The Gemini review reply service instance.
        reply_max_length: Maximum allowed reply length in characters.
        web_search_service: WebSearchService for web context retrieval.
            If None, web search is disabled for review replies.
    """

    def __init__(
        self,
        llm_service: GeminiReviewReplyService | None = None,
        reply_max_length: int | None = None,
        web_search_service: WebSearchService | None = None,
    ) -> None:
        self.llm_service = llm_service or GeminiReviewReplyService()
        self.reply_max_length = reply_max_length or getattr(
            self.llm_service, "reply_max_length", 1000
        )
        self.web_search_service = web_search_service or WebSearchService()

    async def run(self, review: Comment) -> ReviewReplyResult:
        """Process a review and generate a bot reply.

        Args:
            review: The Comment instance representing the user review.

        Returns:
            A ReviewReplyResult indicating success or failure.
        """
        try:
            # Step 1: Normalize input
            input_data = self._normalize_review(review)

            # Step 2: Validate content
            validation_error = self._validate_input(input_data)
            if validation_error:
                return ReviewReplyResult(
                    success=False, error=validation_error
                )

            # Step 3: Prepare metadata
            metadata = self._prepare_metadata(input_data)

            # Step 4: Get retrieval context (RAG + Web search)
            rag_context = await self.get_retrieval_context(input_data)
            web_context = await self.get_web_context(input_data)

            # Step 5: Build merged context if web results exist
            merged_context = self._build_merged_context(rag_context, web_context)
            if merged_context:
                metadata["rag_context"] = merged_context

            # Step 6: Generate reply via LLM
            reply = await self.llm_service.generate_reply(
                review_content=input_data.content,
                metadata=metadata,
            )

            # Step 7: Validate the generated reply
            validation_error = self._validate_reply(reply)
            if validation_error:
                return ReviewReplyResult(
                    success=False, error=validation_error
                )

            logger.info(
                "Successfully generated reply for review %s (web_search=%s).",
                input_data.review_id,
                bool(web_context),
            )
            return ReviewReplyResult(
                success=True,
                reply=reply,
                web_search_used=bool(web_context),
                source_mode="rag_plus_web" if rag_context and web_context else "rag_only",
            )

        except GeminiReplyError as e:
            logger.error(
                "Gemini error generating reply for review %s: %s",
                review.id,
                str(e),
            )
            return ReviewReplyResult(
                success=False,
                error=f"LLM error: {str(e)}",
            )
        except Exception as e:
            logger.error(
                "Unexpected error in agent for review %s: %s",
                review.id,
                str(e),
                exc_info=True,
            )
            return ReviewReplyResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    def _normalize_review(self, review: Comment) -> ReviewReplyInput:
        """Normalize a Comment instance into a ReviewReplyInput.

        Args:
            review: The Comment instance.

        Returns:
            A ReviewReplyInput with trimmed and cleaned fields.
        """
        content = review.content.strip() if review.content else ""
        return ReviewReplyInput(
            content=content,
            rating=review.rating,
            app_version=review.app_version,
            overall_sentiment=review.overall_sentiment,
            review_id=review.id,
        )

    def _validate_input(self, input_data: ReviewReplyInput) -> str | None:
        """Validate the normalized input.

        Args:
            input_data: The normalized input.

        Returns:
            An error string if invalid, otherwise None.
        """
        if not input_data.content:
            return "Review content is empty."
        if len(input_data.content) > 10000:
            return f"Review content too long ({len(input_data.content)} chars)."
        return None

    def _prepare_metadata(
        self, input_data: ReviewReplyInput
    ) -> dict[str, Any]:
        """Prepare metadata dict for the LLM service.

        Args:
            input_data: The normalized input.

        Returns:
            A dict with available metadata fields.
        """
        metadata: dict[str, Any] = {}
        if input_data.rating is not None:
            metadata["rating"] = input_data.rating
        if input_data.app_version:
            metadata["app_version"] = input_data.app_version
        if input_data.overall_sentiment:
            metadata["overall_sentiment"] = input_data.overall_sentiment
        return metadata

    async def get_retrieval_context(
        self, input_data: ReviewReplyInput
    ) -> list[str]:
        """Retrieve relevant context for the reply (RAG hook).

        This is a placeholder for future retrieval-augmented generation.
        Override this method or inject a retriever to enable RAG.

        Args:
            input_data: The normalized input.

        Returns:
            A list of context strings. Currently returns empty list.
        """
        return []

    async def get_web_context(
        self, input_data: ReviewReplyInput
    ) -> list[str]:
        """Retrieve web context for the reply.

        Uses web search to find relevant information when
        RAG context is insufficient and web search is enabled.

        For review replies, web search is conservative:
        - Only searches if query is informative (not just complaints).
        - Only returns top 3 results max.
        - Useful for answering "how to" or "when" questions.

        Args:
            input_data: The normalized input.

        Returns:
            A list of web context strings. Empty if disabled or not needed.
        """
        if not self.web_search_service.is_ready:
            return []

        content = input_data.content.lower()

        # Check if the review might benefit from web search
        web_search_triggers = [
            "how to", "cách", "làm sao", "khi nào", "when",
            "version mới", "new version", "update", "cập nhật",
            "tính năng", "feature", "tại sao", "why",
            "khắc phục", "fix", "hướng dẫn", "guide",
        ]

        if not any(trigger in content for trigger in web_search_triggers):
            return []

        try:
            request = WebSearchRequest(
                query=input_data.content[:300],
                top_k=3,
                language="lang_vi",
                safe_search="active",
            )

            response = await self.web_search_service.search(request)

            if not response.has_results:
                return []

            # Format context
            web_results: list[str] = []
            for i, result in enumerate(response.results, 1):
                if result.title or result.snippet:
                    web_results.append(
                        f"[W{i}] {result.title}\n"
                        f"URL: {result.url}\n"
                        f"{result.snippet}"
                    )

            return web_results

        except Exception as e:
            logger.warning("Web search context retrieval failed: %s", e)
            return []

    def _build_merged_context(
        self,
        rag_context: list[str],
        web_context: list[str],
    ) -> str | None:
        """Build merged context from RAG and web sources.

        Args:
            rag_context: Context strings from RAG retrieval.
            web_context: Context strings from web search.

        Returns:
            A merged context string, or None if both are empty.
        """
        parts: list[str] = []

        if rag_context:
            parts.append("=== NGUỒN NỘI BỘ ===")
            parts.extend(rag_context)

        if web_context:
            if parts:
                parts.append("")
            parts.append("=== NGUỒN WEB ===")
            parts.extend(web_context)

        return "\n".join(parts) if parts else None

    def _validate_reply(self, reply: str) -> str | None:
        """Validate the generated reply.

        Args:
            reply: The generated reply text.

        Returns:
            An error string if invalid, otherwise None.
        """
        if not reply or not reply.strip():
            return "Generated reply is empty."
        if len(reply) > self.reply_max_length:
            return (
                f"Generated reply too long "
                f"({len(reply)} > {self.reply_max_length} chars)."
            )
        return None
