"""
Chunking service.

Implements the chunking pipeline:
1. Accept cleaned text from TextCleanerService
2. Split into chunks by token count (with overlap)
3. Save chunks to PostgreSQL
4. Generate embeddings for each chunk
5. Upsert vectors to Qdrant
6. Update BM25 index
7. Update document status

Chunking is done by token count (using a simple whitespace-based tokenizer)
to stay aligned with LLM and embedding model token limits.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ChunkingError
from app.db.models.chunk import DocumentChunk
from app.db.models.document import Document
from app.db.repository.chunk import ChunkRepository
from app.db.repository.document import DocumentRepository
from app.services.bm25.indexer import BM25Indexer
from app.services.chunking.cleaner import TextCleanerService
from app.services.chunking.extractor import TextExtractorService
from app.services.embedding.service import EmbeddingService
from app.services.qdrant.schemas import PointMetadata, PointUpsert
from app.services.qdrant.service import QdrantService

logger = logging.getLogger(__name__)


class ChunkingService:
    """Orchestrates the complete chunking pipeline.

    Pipeline:
        Document File
        → Extract text (TextExtractorService)
        → Clean text (TextCleanerService)
        → Split into chunks (by token count)
        → Save chunks to PostgreSQL (ChunkRepository)
        → Generate embeddings (EmbeddingService)
        → Upsert vectors to Qdrant (QdrantService)
        → Update BM25 index (BM25Indexer)
        → Update document status

    Attributes:
        chunk_size: Maximum tokens per chunk.
        chunk_overlap: Overlap tokens between consecutive chunks.
        extractor: Service for extracting text from files.
        cleaner: Service for cleaning/normalizing text.
        embedding_service: Service for generating embeddings.
        qdrant_service: Service for vector store operations.
        bm25_indexer: BM25 keyword indexer.
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        extractor: TextExtractorService | None = None,
        cleaner: TextCleanerService | None = None,
        embedding_service: EmbeddingService | None = None,
        qdrant_service: QdrantService | None = None,
        bm25_indexer: BM25Indexer | None = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.extractor = extractor or TextExtractorService()
        self.cleaner = cleaner or TextCleanerService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.qdrant_service = qdrant_service or QdrantService()
        self.bm25_indexer = bm25_indexer or BM25Indexer()

    # ── Main pipeline ────────────────────────────────────────────────

    async def process_document(
        self,
        document: Document,
        session: AsyncSession,
    ) -> list[DocumentChunk]:
        """Process a document through the full chunking pipeline.

        Args:
            document: The Document record (must have file_path set).
            session: Async DB session for persistence.

        Returns:
            The list of created DocumentChunk instances.

        Raises:
            ChunkingError: If any step of the pipeline fails.
        """
        doc_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)
        start_time = time.monotonic()

        try:
            # 1. Update status to processing
            await doc_repo.update_status(document.id, "processing")
            await session.flush()

            # 2. Extract text
            logger.info("Extracting text from: %s", document.file_path)
            raw_text = await self.extractor.extract(document.file_path)

            if not raw_text.strip():
                raise ChunkingError(
                    message=f"No text could be extracted from document {document.id}",
                    error_code="EMPTY_DOCUMENT",
                    details={"document_id": document.id},
                )

            # 3. Clean text
            cleaned_text = self.cleaner.clean(raw_text)
            logger.info(
                "Text extracted and cleaned: %d chars → %d chars",
                len(raw_text),
                len(cleaned_text),
            )

            # 4. Split into chunks
            chunks = self._split_text(cleaned_text)
            logger.info("Document split into %d chunks", len(chunks))

            # 5. Save chunks to DB
            db_chunks = await self._save_chunks(
                chunk_repo, document.id, chunks, document.filename
            )

            # 6. Generate embeddings
            await self._embed_chunks(db_chunks, chunk_repo)

            # 7. Upsert vectors to Qdrant
            await self._upsert_to_qdrant(db_chunks, document)

            # 8. Update BM25 index
            await self._update_bm25(db_chunks)

            # 9. Update document status to indexed
            await doc_repo.update(
                document.id,
                status="indexed",
                processed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            await session.flush()

            duration = time.monotonic() - start_time
            logger.info(
                "Document %d processed successfully: %d chunks in %.2fs",
                document.id,
                len(db_chunks),
                duration,
            )

            return db_chunks

        except Exception as e:
            # Mark document as failed
            try:
                await doc_repo.update_status(
                    document.id,
                    "failed",
                    error_message=str(e)[:500],
                )
                await session.flush()
            except Exception as status_e:
                logger.error("Failed to update document status: %s", status_e)

            if isinstance(e, ChunkingError):
                raise
            raise ChunkingError(
                message=f"Document processing failed: {e}",
                error_code="PROCESSING_FAILED",
                details={"document_id": document.id},
            ) from e

    # ── Text splitting ───────────────────────────────────────────────

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks by estimated token count.

        Uses a simple whitespace-based token counter (word count ≈ token count
        for most Latin/CJK text). For precise token counting, use a proper
        tokenizer (e.g., tiktoken) in production.

        Args:
            text: Cleaned text to split.

        Returns:
            List of text chunks.
        """
        if not text:
            return []

        # Simple tokenization: split by whitespace
        words = text.split()
        num_words = len(words)

        if num_words <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < num_words:
            end = start + self.chunk_size
            chunk_words = words[start:end]
            chunks.append(" ".join(chunk_words))

            if end >= num_words:
                break

            # Move start with overlap
            start = end - self.chunk_overlap
            if start < 0:
                start = 0

        return chunks

    # ── DB persistence ───────────────────────────────────────────────

    async def _save_chunks(
        self,
        chunk_repo: ChunkRepository,
        document_id: int,
        chunks: list[str],
        filename: str,
    ) -> list[DocumentChunk]:
        """Save text chunks to the database.

        Args:
            chunk_repo: Chunk repository instance.
            document_id: Parent document ID.
            chunks: List of chunk texts.
            filename: Original filename for metadata.

        Returns:
            List of created DocumentChunk instances.
        """
        chunk_dicts = [
            {
                "document_id": document_id,
                "chunk_index": i,
                "content": chunk_text,
                "metadata_json": {
                    "filename": filename,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            }
            for i, chunk_text in enumerate(chunks)
        ]

        return await chunk_repo.bulk_create(chunk_dicts)

    # ── Embedding ────────────────────────────────────────────────────

    async def _embed_chunks(
        self,
        chunks: list[DocumentChunk],
        chunk_repo: ChunkRepository,
    ) -> None:
        """Generate embeddings for a list of chunks.

        Processes chunks in batches and updates the embedding field in DB.

        Args:
            chunks: List of DocumentChunk instances to embed.
            chunk_repo: Chunk repository for updating embeddings.
        """
        texts = [chunk.content for chunk in chunks]
        batch_size = settings.EMBEDDING_BATCH_SIZE

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_chunks = chunks[i : i + batch_size]

            try:
                results = await self.embedding_service.embed_batch(
                    batch_texts,
                    batch_size=batch_size,
                )

                for chunk, result in zip(batch_chunks, results, strict=False):
                    embedding = result.vector
                    await chunk_repo.update(chunk.id, embedding=embedding)

            except Exception as e:
                logger.error("Embedding failed for batch %d: %s", i // batch_size, e)
                raise ChunkingError(
                    message=f"Embedding batch failed: {e}",
                    error_code="EMBEDDING_BATCH_FAILED",
                    details={"batch_start": i, "batch_size": len(batch_texts)},
                ) from e

        logger.debug("Embedded %d chunks", len(chunks))

    # ── Qdrant upsert ────────────────────────────────────────────────

    async def _upsert_to_qdrant(
        self,
        chunks: list[DocumentChunk],
        document: Document,
    ) -> None:
        """Upsert chunk vectors and metadata to Qdrant.

        Args:
            chunks: List of DocumentChunk instances with embeddings.
            document: The parent Document for metadata.
        """
        collection = settings.QDRANT_COLLECTION

        points: list[PointUpsert] = []
        for chunk in chunks:
            if not chunk.embedding:
                logger.warning("Chunk %s has no embedding, skipping Qdrant upsert", chunk.id)
                continue

            metadata = PointMetadata(
                document_id=document.id,
                chunk_id=chunk.id,
                text=chunk.content[:500],  # Store preview text in payload
                filename=document.filename,
                chunk_index=chunk.chunk_index,
            )

            points.append(
                PointUpsert(
                    id=str(chunk.id),
                    vector=chunk.embedding,
                    metadata=metadata,
                ),
            )

        if points:
            # Ensure collection exists (try to create if not)
            exists = await self.qdrant_service.client.collection_exists(collection)

            if not exists:
                logger.info("Creating Qdrant collection: %s", collection)
                from app.services.qdrant.schemas import CollectionConfig

                config = CollectionConfig(
                    name=collection,
                    vector_size=settings.EMBEDDING_DIMENSION,
                )
                await self.qdrant_service.create_collection(config)

            await self.qdrant_service.batch_upsert_points(collection, points)
            logger.debug("Upserted %d points to Qdrant collection '%s'", len(points), collection)

    # ── BM25 update ──────────────────────────────────────────────────

    async def _update_bm25(self, chunks: list[DocumentChunk]) -> None:
        """Update the BM25 index with new chunk texts.

        Args:
            chunks: List of DocumentChunk instances to index.
        """
        for chunk in chunks:
            await self.bm25_indexer.update_index(
                doc_id=chunk.id,
                text=chunk.content,
            )

        logger.debug("Updated BM25 index with %d chunks", len(chunks))
