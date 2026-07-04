"""Embedding service package.

Provides text embedding using BAAI/bge-m3 via an external API.
Supports async, batch, retry, and timeout.
"""

from app.services.embedding.client import EmbeddingHTTPClient
from app.services.embedding.schemas import (
    EmbeddingData,
    EmbeddingQueryRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingResult,
    EmbeddingUsage,
)
from app.services.embedding.service import EmbeddingService

__all__ = [
    "EmbeddingService",
    "EmbeddingHTTPClient",
    "EmbeddingRequest",
    "EmbeddingQueryRequest",
    "EmbeddingResponse",
    "EmbeddingData",
    "EmbeddingUsage",
    "EmbeddingResult",
]
