"""
LiteLLM unified LLM service.

Provides a unified interface for multiple LLM providers (Gemini, OpenAI,
Anthropic) through the LiteLLM library. Supports:

- Chat completion (sync & async)
- Streaming completion
- Model routing based on task type
- Automatic fallback when the primary model fails
- Retry with exponential backoff
- Token usage parsing
- Timeout protection

Provider chính là Gemini, fallback có thể là OpenAI-compatible hoặc Anthropic.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

import litellm
from litellm import Router
from litellm.exceptions import (
    RateLimitError as LiteLLMRateLimitError,
    Timeout as LiteLLMTimeoutError,
    ServiceUnavailableError as LiteLLMServiceUnavailableError,
)

from app.core.config import settings
from app.core.exceptions import (
    LLMError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of LLM tasks for model routing."""

    CHAT = "chat"
    REVIEW_REPLY = "review_reply"
    QUERY_REWRITE = "query_rewrite"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"


class LLMMessage:
    """A single message in a chat conversation.

    Attributes:
        role: The role of the message sender (system, user, assistant).
        content: The text content of the message.
    """

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content

    def to_dict(self) -> dict[str, str]:
        """Convert to LiteLLM-compatible dict."""
        return {"role": self.role, "content": self.content}


class LLMResponse:
    """Response from an LLM call.

    Attributes:
        content: The generated text content.
        model: The model used for generation.
        usage: Token usage information (prompt_tokens, completion_tokens, total_tokens).
        finish_reason: Reason the generation finished.
    """

    def __init__(
        self,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.finish_reason = finish_reason


class LiteLLMService:
    """Unified LLM service using LiteLLM with routing, fallback, and retry.

    Configures a LiteLLM Router with primary and fallback models,
    and provides a clean async interface for chat completion.

    Attributes:
        router: LiteLLM Router instance for multi-model routing.
        primary_model: Main model to use (default: LITELLM_MODEL).
        fallback_models: List of fallback models if primary fails.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
    """

    # ── Model routing config per task type ────────────────────────────
    TASK_MODEL_MAP: dict[TaskType, str] = {}

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_models: list[str] | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.primary_model = primary_model or settings.LITELLM_MODEL
        fallback_str = settings.LITELLM_FALLBACK_MODELS
        self.fallback_models = fallback_models or (
            [m.strip() for m in fallback_str.split(",") if m.strip()]
            if fallback_str
            else []
        )
        self.timeout = timeout or settings.LITELLM_TIMEOUT
        self.max_retries = max_retries or settings.LITELLM_MAX_RETRIES

        # Configure LiteLLM
        litellm.drop_params = True
        if settings.LITELLM_API_KEY:
            litellm.api_key = settings.LITELLM_API_KEY
        if settings.LITELLM_API_BASE:
            litellm.api_base = settings.LITELLM_API_BASE

        # Build model list for router
        all_models = [self.primary_model] + self.fallback_models
        model_list = [
            {
                "model_name": f"model_{i}",
                "litellm_params": {"model": model, "timeout": self.timeout},
            }
            for i, model in enumerate(all_models)
        ]

        self.router = Router(
            model_list=model_list if model_list else None,
            fallbacks=[(self.primary_model, self.fallback_models)] if self.fallback_models else [],
            num_retries=self.max_retries,
            allowed_fails=3,
            context_length_fallback=True,
        )

        logger.info(
            "LiteLLMService initialized: primary=%s, fallbacks=%s",
            self.primary_model,
            self.fallback_models or "none",
        )

    # ── Public API ───────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        task_type: TaskType | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of conversation messages.
            model: Override the model to use.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response.
            task_type: Optional task type for model routing.
            **kwargs: Additional parameters passed to LiteLLM.

        Returns:
            LLMResponse with generated content and metadata.

        Raises:
            LLMError: If the LLM call fails after all retries.
        """
        model_name = model or self._resolve_model(task_type)
        dict_messages = [m.to_dict() if isinstance(m, LLMMessage) else m for m in messages]

        try:
            response = await self.router.acompletion(
                model=model_name,
                messages=dict_messages,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
                timeout=self.timeout,
                **kwargs,
            )

            return self._parse_response(response, model_name)

        except LiteLLMTimeoutError as e:
            raise LLMTimeoutError(timeout=self.timeout) from e
        except LiteLLMRateLimitError as e:
            raise LLMRateLimitError() from e
        except LiteLLMServiceUnavailableError as e:
            raise LLMServiceUnavailableError() from e
        except Exception as e:
            # If fallback succeeded but primary failed, response is in exception
            if hasattr(e, "status_code") and e.status_code == 429:
                raise LLMRateLimitError() from e
            raise LLMError(
                message=f"LLM chat completion failed: {e}",
                error_code="LLM_CHAT_FAILED",
                details={"model": model_name},
            ) from e

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        task_type: TaskType | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stream a chat completion response.

        Args:
            messages: List of conversation messages.
            model: Override the model to use.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response.
            task_type: Optional task type for model routing.
            **kwargs: Additional parameters passed to LiteLLM.

        Yields:
            Chunks of text as they are generated.
        """
        model_name = model or self._resolve_model(task_type)
        dict_messages = [m.to_dict() if isinstance(m, LLMMessage) else m for m in messages]

        try:
            stream = await self.router.acompletion(
                model=model_name,
                messages=dict_messages,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
                stream=True,
                timeout=self.timeout,
                **kwargs,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

        except LiteLLMTimeoutError as e:
            raise LLMTimeoutError(timeout=self.timeout) from e
        except LiteLLMRateLimitError as e:
            raise LLMRateLimitError() from e
        except Exception as e:
            raise LLMError(
                message=f"LLM streaming failed: {e}",
                error_code="LLM_STREAM_FAILED",
                details={"model": model_name},
            ) from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        task_type: TaskType | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate text from a simple prompt (convenience wrapper).

        Args:
            prompt: The user prompt text.
            system_prompt: Optional system instruction.
            model: Override the model to use.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response.
            task_type: Optional task type for model routing.
            **kwargs: Additional parameters passed to LiteLLM.

        Returns:
            LLMResponse with generated content.
        """
        messages: list[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))

        return await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
            **kwargs,
        )

    async def chat_with_fallback(
        self,
        messages: list[LLMMessage],
        models: list[str] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Try multiple models in sequence, falling back on failure.

        Args:
            messages: List of conversation messages.
            models: Ordered list of models to try. Defaults to primary + fallbacks.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response.
            **kwargs: Additional parameters passed to LiteLLM.

        Returns:
            LLMResponse from the first successful model.
        """
        models_to_try = models or [self.primary_model] + self.fallback_models
        last_error: Exception | None = None

        for model_name in models_to_try:
            try:
                logger.info("Trying model: %s", model_name)
                return await self.chat(
                    messages=messages,
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except (LLMError, LLMTimeoutError, LLMRateLimitError) as e:
                last_error = e
                logger.warning("Model %s failed: %s", model_name, e)
                continue

        raise LLMError(
            message=f"All fallback models failed. Last error: {last_error}",
            error_code="LLM_ALL_FALLBACKS_FAILED",
            details={"models_attempted": models_to_try},
        )

    def register_task_model(self, task_type: TaskType, model: str) -> None:
        """Register a specific model for a task type.

        Args:
            task_type: The task type enum.
            model: The model name to use for this task.
        """
        self.TASK_MODEL_MAP[task_type] = model

    # ── Internal helpers ─────────────────────────────────────────────

    def _resolve_model(self, task_type: TaskType | None) -> str:
        """Resolve which model to use based on task type.

        Args:
            task_type: Optional task type for custom routing.

        Returns:
            The model name to use.
        """
        if task_type and task_type in self.TASK_MODEL_MAP:
            return self.TASK_MODEL_MAP[task_type]
        return self.primary_model

    def _parse_response(self, response: Any, model_name: str) -> LLMResponse:  # noqa: ANN401
        """Parse a LiteLLM response into an LLMResponse.

        Args:
            response: Raw LiteLLM response object.
            model_name: The model that generated the response.

        Returns:
            A normalized LLMResponse.
        """
        content = ""
        finish_reason = None

        if response.choices:
            choice = response.choices[0]
            content = getattr(choice.message, "content", "") or ""
            finish_reason = getattr(choice, "finish_reason", None)

        usage: dict[str, int] = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
            }

        return LLMResponse(
            content=content,
            model=model_name,
            usage=usage,
            finish_reason=finish_reason,
        )
