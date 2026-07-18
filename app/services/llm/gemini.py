"""Gemini-powered service for generating review replies.

Provides a clean interface for calling Google Gemini API to generate
Vietnamese responses to user reviews. Handles API key validation,
async wrapping of sync SDK, and error normalization.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiReplyError(Exception):
    """Raised when Gemini fails to generate a reply."""


class GeminiReviewReplyService:
    """Service for generating review replies using Google Gemini.

    Args:
        api_key: Gemini API key. Defaults to settings.GEMINI_API_KEY.
        model_name: Gemini model name. Defaults to settings.GEMINI_MODEL.
        reply_max_length: Max characters for the generated reply.
            Defaults to settings.REVIEW_REPLY_MAX_LENGTH.
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
        api_key: str | None = None,
        model_name: str | None = None,
        reply_max_length: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")
        self.reply_max_length = reply_max_length or getattr(
            settings, "REVIEW_REPLY_MAX_LENGTH", 1000
        )

        if not self.api_key:
            raise GeminiReplyError(
                "GEMINI_API_KEY is not configured. "
                "Set it in your .env file or pass it to the constructor."
            )

    async def generate_reply(
        self,
        review_content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Generate a reply to a user review using Gemini.

        Args:
            review_content: The content of the user review.
            metadata: Optional metadata dict (e.g., rating, app_version, sentiment).

        Returns:
            The generated reply text.

        Raises:
            GeminiReplyError: If the API call fails or returns an empty response.
        """
        try:
            user_prompt = self._build_prompt(review_content, metadata)
            raw_reply = await self._call_gemini(user_prompt)
            reply = raw_reply.strip()

            if not reply:
                raise GeminiReplyError("Gemini returned an empty response.")

            if len(reply) > self.reply_max_length:
                logger.warning(
                    "Generated reply too long (%d chars), truncating to %d.",
                    len(reply),
                    self.reply_max_length,
                )
                reply = reply[: self.reply_max_length].rsplit(" ", 1)[0] + "..."

            return reply

        except GeminiReplyError:
            raise
        except Exception as e:
            logger.error("Unexpected error calling Gemini: %s", str(e), exc_info=True)
            raise GeminiReplyError(f"Failed to generate reply: {str(e)}") from e

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

        parts.append(
            "\nHãy viết phản hồi cho đánh giá này bằng tiếng Việt, "
            "tuân thủ các nguyên tắc đã nêu."
        )

        return "\n".join(parts)

    async def _call_gemini(self, prompt: str) -> str:
        """Call the Gemini API with the given prompt.

        Uses asyncio.to_thread to avoid blocking the event loop
        since the google-generativeai SDK is synchronous.

        Args:
            prompt: The full prompt to send.

        Returns:
            The raw text response from Gemini.
        """
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.SYSTEM_PROMPT,
        )

        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
        )

        return response.text
