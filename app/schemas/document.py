"""
Document Pydantic schemas for request/response validation.

Defines the data contracts for the Document Management API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    """Response after a successful file upload."""

    id: int
    filename: str
    mime_type: str
    size: int
    version: int
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentUpdateMetadata(BaseModel):
    """Request schema for updating document metadata."""

    metadata: dict[str, Any] = Field(..., description="Arbitrary key-value metadata")


# ── Response Schemas ─────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """Full document response returned to the client."""

    id: int
    filename: str
    mime_type: str
    size: int
    version: int
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    error_message: str | None = None
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentDeleteResponse(BaseModel):
    """Response after deleting a document."""

    id: int
    deleted: bool = True
    message: str = "Document deleted successfully"


class DocumentVersionResponse(BaseModel):
    """Response for a document version entry."""

    version: int
    filename: str
    size: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionListResponse(BaseModel):
    """List of versions for a document."""

    document_id: int
    versions: list[DocumentVersionResponse]
