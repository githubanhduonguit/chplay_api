"""
Embedding schemas.

Defines the data contracts for embedding requests and responses.
Uses OpenAI-compatible format for embedding API interoperability.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────


class EmbeddingRequest(BaseModel):
    """Request body for the embedding API (OpenAI-compatible format)."""

    model: str = Field(default="BAAI/bge-m3", description="The embedding model name")
    input: str | list[str] = Field(..., description="Text or list of texts to embed")
    encoding_format: str = Field(
        default="float",
        description="Encoding format (float or base64)",
    )


class EmbeddingQueryRequest(BaseModel):
    """Request body specifically for query embedding (may use different pooling)."""

    model: str = Field(default="BAAI/bge-m3", description="The embedding model name")
    input: str = Field(..., description="Query text to embed")
    encoding_format: str = Field(default="float", description="Encoding format")


# ── Response Schemas ─────────────────────────────────────────────────


class EmbeddingData(BaseModel):
    """A single embedding vector result."""

    object: str = Field(default="embedding", description="Object type")
    index: int = Field(..., description="Index of the input in the batch")
    embedding: list[float] = Field(..., description="The embedding vector")


class EmbeddingUsage(BaseModel):
    """Token usage information for the embedding request."""

    prompt_tokens: int = Field(default=0, description="Number of input tokens")
    total_tokens: int = Field(default=0, description="Total tokens used")


class EmbeddingResponse(BaseModel):
    """Response from the embedding API (OpenAI-compatible format)."""

    object: str = Field(default="list", description="Object type")
    data: list[EmbeddingData] = Field(..., description="List of embedding results")
    model: str = Field(..., description="Model used for embedding")
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


# ── Internal Domain Schemas ──────────────────────────────────────────


class EmbeddingResult(BaseModel):
    """Internal representation of an embedding result."""

    vector: list[float] = Field(..., description="The embedding vector")
    index: int = Field(..., description="Index of the input")
    tokens_used: int = Field(default=0, description="Tokens consumed")
