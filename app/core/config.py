"""
Application configuration.

All configuration values are loaded from environment variables
using Pydantic Settings for type safety and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All values can be overridden via environment variables or a .env file.
    """

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "chplay-api"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://neondb_owner:npg_yeTS1N6jgDaz@ep-blue-math-aorankzj-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb"

    # ── Qdrant ───────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "documents"
    QDRANT_TIMEOUT: int = 30

    # ── LLM / AI ─────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    LITELLM_API_KEY: str = ""
    LITELLM_API_BASE: str = "https://api.litellm.ai"

    # ── PhoBERT ──────────────────────────────────────────────────────
    PHOBERT_API_URL: str = ""
    PHOBERT_API_KEY: str = ""
    PHOBERT_TIMEOUT: int = 30
    PHOBERT_MAX_RETRIES: int = 3
    PHOBERT_BATCH_SIZE: int = 32

    # ── Embedding ────────────────────────────────────────────────────
    EMBEDDING_API_URL: str = "http://localhost:8001/v1/embeddings"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_TIMEOUT: int = 60

    # ── Hybrid Search ────────────────────────────────────────────────
    HYBRID_SEARCH_WEIGHT_VECTOR: float = 0.5
    HYBRID_SEARCH_WEIGHT_BM25: float = 0.5
    HYBRID_SEARCH_TOP_K: int = 10

    # ── Retry & Timeout ──────────────────────────────────────────────
    RETRY_ATTEMPTS: int = 3
    TIMEOUT_SECONDS: int = 30

    # ── Gemini / LLM ─────────────────────────────────────────────────
    GEMINI_MODEL: str = "gemini-3.5-flash"
    LITELLM_MODEL: str = "gemini/gemini-3.5-flash"
    LITELLM_FALLBACK_MODELS: str = ""  # comma-separated: "gemini/gemini-1.5-flash,openai/gpt-4o-mini"
    LITELLM_TIMEOUT: int = 60
    LITELLM_MAX_RETRIES: int = 3
    REVIEW_REPLY_BATCH_SIZE: int = 20
    REVIEW_REPLY_MAX_LENGTH: int = 1000

    # ── Spark ────────────────────────────────────────────────────────
    SPARK_MASTER: str = "local[*]"
    SPARK_APP_NAME: str = "chplay-api"

    # ── Chunking ─────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # ── Scheduler ────────────────────────────────────────────────────
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # ── Paths ────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    DATA_DIR: str = "data"

    # ── Internal ─────────────────────────────────────────────────────
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url_async(self) -> str:
        """Get the async database URL."""
        return self.DATABASE_URL

    @property
    def upload_path(self) -> Path:
        """Get the upload directory as a Path object."""
        return Path(self.UPLOAD_DIR)

    @property
    def data_path(self) -> Path:
        """Get the data directory as a Path object."""
        return Path(self.DATA_DIR)


settings = Settings()
