"""
Document management service.

Handles all document-related business logic:
- File upload (validate, save to disk, create DB record)
- File deletion (remove from disk + DB)
- Listing with pagination and filtering
- Metadata management
- Version tracking
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeError,
    NotFoundError,
    StorageError,
    UnsupportedFileTypeError,
)
from app.db.models.document import Document
from app.db.repository.document import DocumentRepository

# Allowed MIME types for upload
ALLOWED_MIME_TYPES: set[str] = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "text/markdown",
    "text/html",
    "application/json",
    "application/xml",
    "application/rtf",
    # Images (for OCR / vision pipelines)
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}

# Max file size (default 100 MB)
_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class DocumentService:
    """Service for managing documents.

    Provides high-level operations that coordinate file storage
    and database persistence.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.repo = DocumentRepository(session)
        self.session = session

    # ── Public API ─────────────────────────────────────────────────

    async def upload(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Upload a new document.

        Args:
            filename: Original filename from the client.
            content: Raw file bytes.
            metadata: Optional key-value metadata.

        Returns:
            The created Document record.

        Raises:
            FileTooLargeError: If the file exceeds the size limit.
            UnsupportedFileTypeError: If the MIME type is not allowed.
            StorageError: If the file cannot be saved to disk.
            ConflictError: If a document with the same filename already exists.
        """
        self._validate_file_size(content)
        mime_type = self._infer_mime_type(filename)
        self._validate_mime_type(mime_type)

        storage_path = await self._save_to_disk(filename, content)

        document = await self.repo.create(
            filename=filename,
            file_path=str(storage_path),
            mime_type=mime_type,
            size=len(content),
            version=1,
            metadata_json=metadata or {},
            status="uploaded",
        )

        return document

    async def delete(self, document_id: int) -> Document:
        """Delete a document by ID.

        Removes the file from disk and deletes the database record.

        Args:
            document_id: The document primary key.

        Returns:
            The deleted Document record.

        Raises:
            NotFoundError: If the document does not exist.
            StorageError: If the file cannot be removed from disk.
        """
        document = await self.repo.get(document_id)
        if document is None:
            raise NotFoundError(
                message=f"Document with id={document_id} not found",
                error_code="DOCUMENT_NOT_FOUND",
            )

        # Remove the file from disk
        file_path = Path(document.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError as e:
                raise StorageError(
                    message=f"Failed to delete file: {e}",
                    error_code="FILE_DELETE_FAILED",
                ) from e

        await self.repo.delete(document_id)
        return document

    async def get(self, document_id: int) -> Document:
        """Get a document by ID.

        Args:
            document_id: The document primary key.

        Returns:
            The Document record.

        Raises:
            NotFoundError: If the document does not exist.
        """
        document = await self.repo.get(document_id)
        if document is None:
            raise NotFoundError(
                message=f"Document with id={document_id} not found",
                error_code="DOCUMENT_NOT_FOUND",
            )
        return document

    async def list_documents(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Document], int]:
        """List documents with optional filtering and pagination.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            status: Optional filter by document status.
            search: Optional filename search query.

        Returns:
            A tuple of (list of documents, total count).
        """
        if search:
            all_docs = await self.repo.search_by_filename(search, limit + skip)
            total = len(all_docs)
            return all_docs[skip:], total

        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status

        documents = await self.repo.get_many(
            skip=skip,
            limit=limit,
            filters=filters if filters else None,
            order_by="created_at",
            descending=True,
        )
        total = await self.repo.count(filters=filters if filters else None)
        return documents, total

    async def update_metadata(
        self,
        document_id: int,
        metadata: dict[str, Any],
    ) -> Document:
        """Update the metadata of a document (merge strategy).

        Args:
            document_id: The document primary key.
            metadata: Key-value metadata to merge into existing metadata.

        Returns:
            The updated Document record.

        Raises:
            NotFoundError: If the document does not exist.
        """
        document = await self.repo.get(document_id)
        if document is None:
            raise NotFoundError(
                message=f"Document with id={document_id} not found",
                error_code="DOCUMENT_NOT_FOUND",
            )

        current_meta: dict[str, Any] = dict(document.metadata_json or {})
        current_meta.update(metadata)

        updated = await self.repo.update(document_id, metadata_json=current_meta)
        if updated is None:
            raise NotFoundError(
                message=f"Document with id={document_id} not found",
                error_code="DOCUMENT_NOT_FOUND",
            )
        return updated

    async def get_versions(self, document_id: int) -> list[dict[str, Any]]:
        """Get version history for a document.

        Currently returns the current version as a single entry.
        This will be expanded when proper versioning is implemented.

        Args:
            document_id: The document primary key.

        Returns:
            A list of version entries.

        Raises:
            NotFoundError: If the document does not exist.
        """
        document = await self.get(document_id)
        return [
            {
                "version": document.version,
                "filename": document.filename,
                "size": document.size,
                "status": document.status,
                "created_at": document.created_at,
            },
        ]

    # ── Internal helpers ─────────────────────────────────────────────

    def _validate_file_size(self, content: bytes) -> None:
        """Validate that the file does not exceed the maximum size."""
        if len(content) > _MAX_FILE_SIZE_BYTES:
            actual_mb = len(content) / (1024 * 1024)
            raise FileTooLargeError(
                actual_size_mb=actual_mb,
            )

    def _validate_mime_type(self, mime_type: str) -> None:
        """Validate that the MIME type is allowed."""
        if mime_type not in ALLOWED_MIME_TYPES:
            raise UnsupportedFileTypeError(mime_type=mime_type)

    def _infer_mime_type(self, filename: str) -> str:
        """Infer the MIME type from a filename.

        Falls back to 'application/octet-stream' if unknown.
        """
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def _ensure_upload_dir(self) -> None:
        """Create the upload directory if it does not exist."""
        upload_path = settings.upload_path
        upload_path.mkdir(parents=True, exist_ok=True)

    async def _save_to_disk(self, filename: str, content: bytes) -> Path:
        """Save file content to disk with a unique name.

        Args:
            filename: The original filename (used for extension).
            content: Raw file bytes.

        Returns:
            The full path to the saved file.

        Raises:
            StorageError: If the file cannot be written.
        """
        upload_path = settings.upload_path

        # Generate a unique filename to prevent collisions
        ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = upload_path / unique_name

        try:
            # Use asyncio.to_thread to avoid blocking the event loop
            await asyncio.to_thread(file_path.write_bytes, content)
        except OSError as e:
            raise StorageError(
                message=f"Failed to write file to disk: {e}",
                error_code="FILE_WRITE_FAILED",
            ) from e

        return file_path
