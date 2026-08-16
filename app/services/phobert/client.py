"""
PhoBERT REST API client.

Provides an async HTTP client for interacting with a PhoBERT model
deployed on Google Colab (or any REST endpoint). Supports:

- Health check before batch jobs
- Single and batch prediction
- Retry with exponential backoff
- Timeout protection
- Response validation

The exact API contract (endpoints, request/response format) is configurable
via settings so the client works with different deployment setups.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import PhoBERTError, PhoBERTTimeoutError, PhoBERTServiceUnavailableError

logger = logging.getLogger(__name__)


class PhoBERTClient:
    """Async HTTP client for the PhoBERT REST API.

    Communicates with a PhoBERT model deployed on Google Colab or any
    REST endpoint. The API is expected to accept a list of texts and
    return predictions for each.

    Args:
        api_url: Base URL of the PhoBERT API.
        api_key: Optional API key for authentication.
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts for transient failures.
        batch_size: Maximum texts per batch request.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.api_url = (api_url or settings.PHOBERT_API_URL).rstrip("/")
        self.api_key = api_key or settings.PHOBERT_API_KEY
        self.timeout = timeout or settings.PHOBERT_TIMEOUT
        self.max_retries = max_retries or settings.PHOBERT_MAX_RETRIES
        self.batch_size = batch_size or settings.PHOBERT_BATCH_SIZE

        if not self.api_url:
            logger.warning(
                "PHOBERT_API_URL is not configured. "
                "PhoBERTClient will raise errors on predict calls."
            )

    # ── Public API ───────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Check if the PhoBERT API is reachable.

        Attempts to GET the health endpoint. If no explicit health
        endpoint is configured, tries the root URL.

        Returns:
            True if the service responds with 200, False otherwise.
        """
        if not self.api_url:
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def predict(self, text: str) -> dict[str, Any]:
        """Predict the label/sentiment for a single text.

        Args:
            text: The input text to classify.

        Returns:
            A dict with prediction results (label, confidence, etc.).

        Raises:
            PhoBERTError: If the prediction fails after retries.
        """
        results = await self.predict_batch([text])
        return results[0] if results else {}

    async def predict_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Predict labels for multiple texts in batches.

        Automatically splits large lists into smaller batches
        and aggregates the results.

        Args:
            texts: List of input texts to classify.

        Returns:
            A list of prediction dicts, one per input text.

        Raises:
            PhoBERTError: If the API is not configured or the call fails.
        """
        if not texts:
            return []

        if not self.api_url:
            raise PhoBERTError(
                message="PHOBERT_API_URL is not configured. "
                "Set it in your .env file to use PhoBERT predictions.",
                error_code="PHOBERT_NOT_CONFIGURED",
            )

        all_results: list[dict[str, Any]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_results = await self._predict_with_retry(batch)
            all_results.extend(batch_results)

        return all_results

    # ── Internal API with Retry ──────────────────────────────────────

    async def _predict_with_retry(self, texts: list[str]) -> list[dict[str, Any]]:
        """Call the PhoBERT API with retry logic.

        Args:
            texts: Batch of texts to predict.

        Returns:
            List of prediction dicts.

        Raises:
            PhoBERTError: If all retry attempts fail.
        """
        try:
            async for attempt in self._retry_strategy():
                with attempt:
                    response = await self._call_api(texts)
                    return self._parse_response(response)

        except Exception as e:
            raise PhoBERTError(
                message=f"PhoBERT prediction failed after retries: {e}",
                error_code="PHOBERT_PREDICTION_FAILED",
                details={"text_count": len(texts)},
            ) from e

    async def _call_api(self, texts: list[str]) -> dict[str, Any]:
        """Make the HTTP request to the PhoBERT API.

        Args:
            texts: Batch of texts to send.

        Returns:
            Raw JSON response from the API.

        Raises:
            PhoBERTError: On HTTP errors or connection issues.
        """
        payload = self._build_payload(texts)
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                )
        except httpx.ConnectError as e:
            raise PhoBERTError(
                message=f"Cannot connect to PhoBERT API at {self.api_url}: {e}",
                error_code="PHOBERT_CONNECTION_FAILED",
            ) from e
        except httpx.TimeoutException as e:
            raise PhoBERTTimeoutError(timeout=self.timeout) from e

        if response.status_code != 200:
            raise PhoBERTError(
                message=f"PhoBERT API returned status {response.status_code}: {response.text[:500]}",
                error_code="PHOBERT_API_ERROR",
                details={"status_code": response.status_code},
            )

        return response.json()

    # ── Payload / Response helpers ───────────────────────────────────

    def _build_payload(self, texts: list[str]) -> dict[str, Any]:
        """Build the request payload for the PhoBERT API.

        Supports multiple API formats via configurable keys.

        Args:
            texts: List of texts to send.

        Returns:
            A JSON-serializable dict payload.
        """
        return {
            "texts": texts,
            "include_confidence": True,
        }

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers including auth if configured.

        Returns:
            Dict of HTTP headers.
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_response(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse the API response into a list of prediction dicts.

        Supports multiple response formats:
        1. {"predictions": [...]}
        2. {"results": [...]}
        3. [{"label": "...", "confidence": ...}, ...]

        Args:
            raw: Raw JSON response from the API.

        Returns:
            A list of prediction dicts with at minimum a "label" key.
        """
        # Format 1: {"predictions": [{"label": "...", "confidence": ...}, ...]}
        if "predictions" in raw and isinstance(raw["predictions"], list):
            return self._normalize_predictions(raw["predictions"])

        # Format 2: {"results": [{"label": "...", "confidence": ...}, ...]}
        if "results" in raw and isinstance(raw["results"], list):
            return self._normalize_predictions(raw["results"])

        # Format 3: Direct list of dicts
        if isinstance(raw, list):
            return self._normalize_predictions(raw)

        # Format 4: {"label": "...", "confidence": ...} (single prediction)
        if isinstance(raw, dict) and "label" in raw:
            return [self._normalize_single(raw)]

        logger.warning("Unknown PhoBERT API response format: %s", str(raw)[:200])
        return [{"label": "unknown", "raw": str(raw)[:500]}]

    def _normalize_predictions(self, predictions: list[Any]) -> list[dict[str, Any]]:
        """Normalize a list of predictions to a consistent format.

        Args:
            predictions: Raw prediction list from the API.

        Returns:
            Normalized list of prediction dicts.
        """
        return [self._normalize_single(p) if isinstance(p, dict) else {"label": str(p)} for p in predictions]

    @staticmethod
    def _normalize_single(prediction: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single prediction dict.

        Ensures the response has at minimum a "label" key.

        Args:
            prediction: Raw prediction dict.

        Returns:
            Normalized prediction dict.
        """
        normalized: dict[str, Any] = {}
        # Copy all known fields
        for key in (
            "label",
            "confidence",
            "score",
            "sentiment",
            "aspect",
            "topic_l1",
            "topic_l2",
            "probability",
        ):
            if key in prediction:
                normalized[key] = prediction[key]
        # Ensure at least a label exists
        if "label" not in normalized:
            for key in ("predicted_label", "class", "category", "prediction"):
                if key in prediction:
                    normalized["label"] = prediction[key]
                    break
        if "label" not in normalized:
            normalized["label"] = "unknown"
        return normalized

    # ── Retry strategy ───────────────────────────────────────────────

    def _retry_strategy(self) -> AsyncRetrying:
        """Get the retry strategy for PhoBERT API calls.

        Retries on connection errors, timeouts, and 5xx responses.

        Returns:
            Configured AsyncRetrying instance.
        """
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    httpx.HTTPStatusError,
                ),
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
