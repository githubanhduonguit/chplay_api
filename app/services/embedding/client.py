"""
HTTP client for the embedding service.

Communicates with an external embedding API. Supports two provider formats:
- "openai": OpenAI-compatible endpoint (e.g., a local TEI deployment, Ollama,
  or a custom FastAPI service serving BAAI/bge-m3).
- "gemini": Google Gemini embedContent API (generativelanguage.googleapis.com).

Features:
- Synchronous and async requests
- Custom timeout and retry
- Authentication via API key (Bearer header for OpenAI, ?key= for Gemini)
"""

from __future__ import annotations

import logging
import socket
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


# ── Network workaround: force IPv4 resolution ─────────────────────────
# This dev machine's IPv6 route is broken: hosts that advertise AAAA
# records (e.g. Google APIs) make Python hang for 8-20s per blackholed
# IPv6 address before falling back to IPv4, and some requests never
# complete at all. curl is unaffected because it implements Happy
# Eyeballs; Python's anyio/httpx does not race the attempts here.
# Filtering getaddrinfo results to IPv4 (when available) avoids the hang
# for every outbound connection in the process.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_first_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
    """Resolve hostnames to IPv4 addresses first, falling back to IPv6."""
    results = _orig_getaddrinfo(*args, **kwargs)
    ipv4_results = [r for r in results if r[0] == socket.AF_INET]
    return ipv4_results or results


socket.getaddrinfo = _ipv4_first_getaddrinfo


class EmbeddingHTTPClient:
    """HTTP client for the external embedding API.

    Supports OpenAI-compatible endpoints and the Google Gemini
    embedContent API (auto-detected via EMBEDDING_PROVIDER or the URL).
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

    @property
    def is_gemini(self) -> bool:
        """Whether the client targets the Google Gemini embedContent API."""
        return (
            settings.EMBEDDING_PROVIDER.lower() == "gemini"
            or "generativelanguage.googleapis.com" in self.base_url
        )

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
        url = self._request_url(input_texts)
        params = {"key": self.api_key} if self.is_gemini and self.api_key else None

        logger.debug(
            "Sending embedding request: %d texts, model=%s, provider=%s",
            len(input_texts) if isinstance(input_texts, list) else 1,
            payload.get("model") or payload.get("requests", [{}])[0].get("model"),
            "gemini" if self.is_gemini else "openai",
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    params=params,
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

    def _request_url(self, input_texts: str | list[str]) -> str:
        """Pick the endpoint URL for the current request.

        Gemini single embeds go to the configured :embedContent URL;
        multi-text batches use the sibling :batchEmbedContents endpoint.
        """
        if (
            self.is_gemini
            and isinstance(input_texts, list)
            and len(input_texts) > 1
        ):
            return self.base_url.replace(":embedContent", ":batchEmbedContents")
        return self.base_url

    def _build_payload(
        self,
        input_texts: str | list[str],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Build the JSON payload for the embedding API."""
        if self.is_gemini:
            model_name = self._gemini_model_name(model)
            texts = input_texts if isinstance(input_texts, list) else [input_texts]
            if len(texts) == 1:
                # Single embed → :embedContent endpoint
                return {
                    "model": model_name,
                    "content": {"parts": [{"text": texts[0]}]},
                    "outputDimensionality": settings.EMBEDDING_DIMENSION,
                }
            # Multi-text batch → :batchEmbedContents endpoint.
            # Note: this v1beta endpoint only accepts outputDimensionality
            # per request item, not at the top level.
            return {
                "requests": [
                    {
                        "model": model_name,
                        "content": {"parts": [{"text": text}]},
                        "outputDimensionality": settings.EMBEDDING_DIMENSION,
                    }
                    for text in texts
                ],
            }

        # OpenAI-compatible format
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
        if self.api_key and not self.is_gemini:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_response(self, raw: dict[str, Any]) -> EmbeddingResponse:
        """Parse the raw API response into an EmbeddingResponse.

        Supports:
        - Gemini embedContent: {"embedding": {"values": [...]}}
        - Gemini batchEmbedContents: {"embeddings": [{"values": [...]}, ...]}
        - OpenAI-compatible: {"data": [{"embedding": [...]}, ...]}
        - A simplified format where the response is a list of vectors directly.
        """
        # Gemini single-embed response
        if self.is_gemini and "embedding" in raw and isinstance(raw.get("embedding"), dict):
            values = raw["embedding"].get("values") or []
            return EmbeddingResponse(
                data=[EmbeddingData(index=0, embedding=values)],
                model=settings.EMBEDDING_MODEL,
            )

        # Gemini batch response
        if self.is_gemini and "embeddings" in raw and isinstance(raw["embeddings"], list):
            data_list = [
                EmbeddingData(index=i, embedding=item.get("values") or [])
                for i, item in enumerate(raw["embeddings"])
            ]
            return EmbeddingResponse(
                data=data_list,
                model=settings.EMBEDDING_MODEL,
            )

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

    @staticmethod
    def _gemini_model_name(model: str | None) -> str:
        """Normalize the model name to the full Gemini 'models/...' path."""
        name = model or settings.EMBEDDING_MODEL
        return name if name.startswith("models/") else f"models/{name}"
