"""GLM-powered service for generating review replies.

Provides a clean interface for calling Z.AI GLM models (e.g. glm-4.7-flash)
through LiteLLM to generate Vietnamese responses to user reviews. Handles
prompt building, empty-response validation, and reply length limiting.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.llm.litellm import LiteLLMService

logger = logging.getLogger(__name__)


class GLMReplyError(Exception):
    """Raised when GLM fails to generate a reply."""


class GLMReviewReplyService:
    """Service for generating review replies using GLM via LiteLLM.

    Args:
        model_name: GLM model name (LiteLLM format, e.g. ``zai/glm-4.7-flash``).
            Defaults to ``settings.LITELLM_MODEL``.
        reply_max_length: Max characters for the generated reply.
            Defaults to ``settings.REVIEW_REPLY_MAX_LENGTH``.
        llm_service: Optional ``LiteLLMService`` instance (for injection/tests).
    """

    SYSTEM_PROMPT = (
        "Bạn là trợ lý hỗ trợ khách hàng chuyên nghiệp của một ứng dụng trên CH Play. "
        "Nhiệm vụ của bạn là trả lời các đánh giá của người dùng bằng tiếng Việt.\n\n"
        "NGUYÊN TẮC:\n"
        "1. Luôn lịch sự, chuyên nghiệp và thân thiện.\n"
        "2. Trả lời ngắn gọn, đúng trọng tâm, không quá 500 ký tự.\n"
        "3. KHÔNG bịa đặt thông tin kỹ thuật hoặc tính năng không có thật.\n"
        "4. KHÔNG hứa hẹn quá mức (ví dụ: 'chúng tôi sẽ sửa ngay' nếu không chắc chắn).\n"
        "5. KHÔNG đổ lỗi cho người dùng, luôn giữ thái độ cầu thị.\n"
        "6. Nếu đánh giá quá ngắn, mơ hồ hoặc chỉ phàn nàn chung chung: "
        "hãy cảm ơn và hỏi cụ thể họ gặp vấn đề gì để được hỗ trợ tốt hơn.\n"
        "7. Nếu đánh giá tích cực: cảm ơn và bày tỏ vui mừng.\n"
        "8. Xưng hô: 'chúng tôi' (ứng dụng) và 'bạn' (người dùng).\n\n"
        "Hãy trả lời trực tiếp, không thêm lời dẫn dắt."
    )

    def __init__(
        self,
        model_name: str | None = None,
        reply_max_length: int | None = None,
        llm_service: LiteLLMService | None = None,
    ) -> None:
        self.model_name = model_name or settings.LITELLM_MODEL
        self.reply_max_length = reply_max_length or settings.REVIEW_REPLY_MAX_LENGTH
        self.llm_service = llm_service or LiteLLMService(primary_model=self.model_name)

    async def generate_reply(
        self,
        review_content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Generate a reply to a user review using GLM.

        Args:
            review_content: The content of the user review.
            metadata: Optional metadata dict (e.g., rating, app_version, sentiment).

        Returns:
            The generated reply text.

        Raises:
            GLMReplyError: If the API call fails or returns an empty response.
        """
        try:
            user_prompt = self._build_prompt(review_content, metadata)
            response = await self.llm_service.generate_text(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.7,
                # glm-4.x uses hidden reasoning tokens which can consume a
                # small max_tokens budget entirely, leaving content empty.
                max_tokens=4096,
            )
            reply = response.content.strip()

            if not reply:
                raise GLMReplyError("GLM returned an empty response.")

            if len(reply) > self.reply_max_length:
                logger.warning(
                    "Generated reply too long (%d chars), truncating to %d.",
                    len(reply),
                    self.reply_max_length,
                )
                reply = reply[: self.reply_max_length].rsplit(" ", 1)[0] + "..."

            return reply

        except GLMReplyError:
            raise
        except Exception as e:
            logger.error("Unexpected error calling GLM: %s", str(e), exc_info=True)
            raise GLMReplyError(f"Failed to generate reply: {str(e)}") from e

    def _build_prompt(
        self,
        review_content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Build the user prompt from review content and optional metadata.

        Args:
            review_content: The user review text.
            metadata: Optional metadata (rating, app_version, sentiment).

        Returns:
            A formatted prompt string.
        """
        parts = [f"Nội dung đánh giá: {review_content}"]

        if metadata:
            if metadata.get("rating") is not None:
                parts.append(f"Số sao: {metadata['rating']}/5")
            if metadata.get("app_version"):
                parts.append(f"Phiên bản: {metadata['app_version']}")
            if metadata.get("overall_sentiment"):
                parts.append(f"Cảm xúc chung: {metadata['overall_sentiment']}")

        rag_context = (metadata or {}).get("rag_context")
        if rag_context:
            parts.append(
                "\nThông tin tham khảo (chỉ dùng khi liên quan, KHÔNG bịa đặt "
                "thông tin ngoài nguồn này):\n" + str(rag_context)
            )

        parts.append(
            "\nHãy viết phản hồi cho đánh giá này bằng tiếng Việt, "
            "tuân thủ các nguyên tắc đã nêu."
        )

        return "\n".join(parts)
