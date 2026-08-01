"""
Application exception hierarchy.

Provides a consistent error structure for all business,
infrastructure, and validation errors across the application.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base exception for all application errors.

    Attributes:
        message: Human-readable error description.
        status_code: HTTP status code for the error response.
        error_code: Machine-readable error code for debugging.
        details: Additional error context (e.g., validation errors).
    """

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


# ── 4xx Client Errors ───────────────────────────────────────────────


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    def __init__(
        self,
        message: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=404,
            error_code=error_code,
            details=details,
        )


class ValidationError(AppError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=422,
            error_code=error_code,
            details=details,
        )


class ConflictError(AppError):
    """Raised when a resource already exists."""

    def __init__(
        self,
        message: str = "Resource already exists",
        error_code: str = "CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=409,
            error_code=error_code,
            details=details,
        )


# ── Business Errors ──────────────────────────────────────────────────


class DocumentError(AppError):
    """Base error for document-related operations."""

    def __init__(
        self,
        message: str = "Document operation failed",
        status_code: int = 400,
        error_code: str = "DOCUMENT_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )


class FileTooLargeError(DocumentError):
    """Raised when the uploaded file exceeds the size limit."""

    def __init__(
        self,
        max_size_mb: int = 100,
        actual_size_mb: float | None = None,
    ) -> None:
        detail = f"File size limit is {max_size_mb}MB"
        if actual_size_mb is not None:
            detail += f", got {actual_size_mb:.1f}MB"
        super().__init__(
            message=detail,
            status_code=413,
            error_code="FILE_TOO_LARGE",
        )


class UnsupportedFileTypeError(DocumentError):
    """Raised when the uploaded file type is not allowed."""

    def __init__(self, mime_type: str | None = None) -> None:
        msg = f"Unsupported file type: {mime_type}" if mime_type else "Unsupported file type"
        super().__init__(
            message=msg,
            status_code=415,
            error_code="UNSUPPORTED_FILE_TYPE",
        )


# ── Infrastructure Errors ────────────────────────────────────────────


class DatabaseError(AppError):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str = "Database operation failed",
        error_code: str = "DATABASE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=500,
            error_code=error_code,
            details=details,
        )


class StorageError(AppError):
    """Raised when a file storage operation fails."""

    def __init__(
        self,
        message: str = "File storage operation failed",
        error_code: str = "STORAGE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=500,
            error_code=error_code,
            details=details,
        )


class EmbeddingError(AppError):
    """Raised when an embedding operation fails."""

    def __init__(
        self,
        message: str = "Embedding operation failed",
        error_code: str = "EMBEDDING_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


class EmbeddingTimeoutError(EmbeddingError):
    """Raised when an embedding request times out."""

    def __init__(
        self,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            message=f"Embedding request timed out after {timeout}s",
            error_code="EMBEDDING_TIMEOUT",
        )


class EmbeddingServiceUnavailableError(EmbeddingError):
    """Raised when the embedding service is unreachable."""

    def __init__(self) -> None:
        super().__init__(
            message="Embedding service is unavailable",
            error_code="EMBEDDING_SERVICE_UNAVAILABLE",
        )


# ── Vector Database Errors ───────────────────────────────────────────


class VectorDBError(AppError):
    """Raised when a vector database operation fails."""

    def __init__(
        self,
        message: str = "Vector database operation failed",
        error_code: str = "VECTOR_DB_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


class CollectionNotFoundError(VectorDBError):
    """Raised when a Qdrant collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection '{collection_name}' not found",
            error_code="COLLECTION_NOT_FOUND",
            details={"collection": collection_name},
        )


class CollectionAlreadyExistsError(VectorDBError):
    """Raised when trying to create a collection that already exists."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(
            message=f"Collection '{collection_name}' already exists",
            status_code=409,
            error_code="COLLECTION_ALREADY_EXISTS",
            details={"collection": collection_name},
        )


# ── BM25 Errors ──────────────────────────────────────────────────────


class BM25Error(AppError):
    """Raised when a BM25 index operation fails."""

    def __init__(
        self,
        message: str = "BM25 index operation failed",
        error_code: str = "BM25_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


# ── Retrieval Errors ─────────────────────────────────────────────────


class RetrievalError(AppError):
    """Raised when a retrieval (hybrid search / rerank) operation fails."""

    def __init__(
        self,
        message: str = "Retrieval operation failed",
        error_code: str = "RETRIEVAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


# ── LLM Errors ───────────────────────────────────────────────────────


class LLMError(AppError):
    """Raised when an LLM operation fails."""

    def __init__(
        self,
        message: str = "LLM operation failed",
        error_code: str = "LLM_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


class LLMTimeoutError(LLMError):
    """Raised when an LLM request times out."""

    def __init__(self, timeout: int = 30) -> None:
        super().__init__(
            message=f"LLM request timed out after {timeout}s",
            error_code="LLM_TIMEOUT",
        )


class LLMServiceUnavailableError(LLMError):
    """Raised when the LLM service is unreachable."""

    def __init__(self) -> None:
        super().__init__(
            message="LLM service is unavailable",
            error_code="LLM_SERVICE_UNAVAILABLE",
        )


class LLMRateLimitError(LLMError):
    """Raised when the LLM API rate limit is exceeded."""

    def __init__(self, retry_after: int | None = None) -> None:
        msg = "LLM rate limit exceeded"
        if retry_after:
            msg += f", retry after {retry_after}s"
        super().__init__(
            message=msg,
            status_code=429,
            error_code="LLM_RATE_LIMIT",
        )


# ── PhoBERT Errors ───────────────────────────────────────────────────


class PhoBERTError(AppError):
    """Raised when a PhoBERT operation fails."""

    def __init__(
        self,
        message: str = "PhoBERT operation failed",
        error_code: str = "PHOBERT_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )


class PhoBERTTimeoutError(PhoBERTError):
    """Raised when a PhoBERT request times out."""

    def __init__(self, timeout: int = 30) -> None:
        super().__init__(
            message=f"PhoBERT request timed out after {timeout}s",
            error_code="PHOBERT_TIMEOUT",
        )


class PhoBERTServiceUnavailableError(PhoBERTError):
    """Raised when the PhoBERT service is unreachable."""

    def __init__(self) -> None:
        super().__init__(
            message="PhoBERT service is unavailable",
            error_code="PHOBERT_SERVICE_UNAVAILABLE",
        )


# ── Chunking Errors ──────────────────────────────────────────────────


class ChunkingError(AppError):
    """Raised when a chunking operation fails."""

    def __init__(
        self,
        message: str = "Chunking operation failed",
        error_code: str = "CHUNKING_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=500,
            error_code=error_code,
            details=details,
        )


class TextExtractionError(ChunkingError):
    """Raised when text extraction from a file fails."""

    def __init__(
        self,
        message: str = "Text extraction failed",
        error_code: str = "TEXT_EXTRACTION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
        )


class UnsupportedFileFormatError(ChunkingError):
    """Raised when the file format is not supported for text extraction."""

    def __init__(self, extension: str) -> None:
        super().__init__(
            message=f"Unsupported file format: '{extension}'",
            status_code=415,
            error_code="UNSUPPORTED_FILE_FORMAT",
            details={"extension": extension},
        )


# ── Spark Errors ─────────────────────────────────────────────────────


class SparkJobError(AppError):
    """Raised when a Spark job operation fails."""

    def __init__(
        self,
        message: str = "Spark job operation failed",
        error_code: str = "SPARK_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=502,
            error_code=error_code,
            details=details,
        )
