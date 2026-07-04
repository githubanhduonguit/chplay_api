"""
HTTP client for the embedding service.

Communicates with an external embedding API (OpenAI-compatible format)
that serves the BAAI/bge-m3 model. Supports:
- Synchronous and async requests
- Custom timeout and retry
- Authentication via API key
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.core.exceptions import (
    EmbeddingError,
    EmbeddingServiceUnavailableError,
)
from app.services.embedding.schemas import (
    EmbeddingData,
    EmbeddingResponse,
    EmbeddingUsage,
)

logger = logging.getLogger(__name__)


class EmbeddingHTTPClient:
    """HTTP client for the external embedding API.

    Communicates with an OpenAI-compatible embedding endpoint
    (e.g., a local TEI deployment, Ollama, or custom FastAPI service).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        health_url: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.EMBEDDING_API_URL).rstrip("/")
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.timeout = timeout or settings.EMBEDDING_TIMEOUT
        self.health_url = health_url

    # ── Public API ───────────────────────────────────────────────────

    async def embed(
        self,
        input_texts: str | list[str],
        model: str | None = None,
    ) -> EmbeddingResponse:
        """Send an embedding request to the API.

        Args:
            input_texts: A single string or list of strings to embed.
            model: Override the default model name.

        Returns:
            The parsed EmbeddingResponse from the API.

        Raises:
            EmbeddingServiceUnavailableError: If the API is unreachable.
            EmbeddingError: If the API returns a non-200 status.
        """
        payload = self._build_payload(input_texts, model)
        headers = self._build_headers()

        logger.debug(
            "Sending embedding request: %d texts, model=%s",
            len(input_texts) if isinstance(input_texts, list) else 1,
            payload.get("model"),
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )
        except httpx.ConnectError as e:
            raise EmbeddingServiceUnavailableError() from e
        except httpx.TimeoutException as e:
            raise EmbeddingError(
                message=f"Embedding request timed out after {self.timeout}s",
                error_code="EMBEDDING_TIMEOUT",
            ) from e

        if response.status_code != 200:
            raise EmbeddingError(
                message=f"Embedding API returned status {response.status_code}: {response.text}",
                error_code="EMBEDDING_API_ERROR",
                details={"status_code": response.status_code, "body": response.text},
            )

        return self._parse_response(response.json())

    async def health_check(self) -> bool:
        """Check if the embedding service is reachable.

        Attempts to reach the health endpoint by:
        1. Using an explicitly configured health_url
        2. Deriving from base_url (replacing the last path segment with /health)

        Returns:
            True if the service responds, False otherwise.
        """
        url = self.health_url or urljoin(self.base_url.rsplit("/", 1)[0] + "/", "health")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False

    # ── Internal helpers ─────────────────────────────────────────────

    def _build_payload(
        self,
        input_texts: str | list[str],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Build the JSON payload for the embedding API."""
        return {
            "model": model or settings.EMBEDDING_MODEL,
            "input": input_texts,
            "encoding_format": "float",
        }

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers, including auth if configured."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_response(self, raw: dict[str, Any]) -> EmbeddingResponse:
        """Parse the raw API response into an EmbeddingResponse.

        Supports both OpenAI-compatible format and a simplified
        format where the response is a list of vectors directly.
        """
        # OpenAI-compatible format
        if "data" in raw and isinstance(raw["data"], list):
            data_list = []
            for item in raw["data"]:
                data_list.append(
                    EmbeddingData(
                        object=item.get("object", "embedding"),
                        index=item.get("index", 0),
                        embedding=item["embedding"],
                    ),
                )

            usage_raw = raw.get("usage", {})
            usage = EmbeddingUsage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                total_tokens=usage_raw.get("total_tokens", 0),
            )

            return EmbeddingResponse(
                object=raw.get("object", "list"),
                data=data_list,
                model=raw.get("model", settings.EMBEDDING_MODEL),
                usage=usage,
            )

        # Fallback: assume response is a list of vectors
        if isinstance(raw, list):
            data_list = [
                EmbeddingData(index=i, embedding=vec)
                for i, vec in enumerate(raw)
            ]
            return EmbeddingResponse(
                data=data_list,
                model=settings.EMBEDDING_MODEL,
            )

        raise EmbeddingError(
            message="Unexpected embedding API response format",
            error_code="EMBEDDING_PARSE_ERROR",
            details={"raw": str(raw)[:500]},
        )
