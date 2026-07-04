"""
Document management API routes.

Provides RESTful endpoints for:
- Uploading documents
- Listing / searching documents
- Retrieving a single document
- Deleting documents
- Updating metadata
- Viewing version history
"""

from __future__ import annotations

from typing import Any

import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdateMetadata,
    DocumentUploadResponse,
    DocumentVersionListResponse,
    DocumentVersionResponse,
)
from app.services.document import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


async def _get_document_service(
    session: AsyncSession = Depends(get_db),
) -> DocumentService:
    """Dependency: create a DocumentService with the current DB session."""
    return DocumentService(session)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description="Upload a file as a new document. Returns the created document record.",
)
async def upload_document(
    file: UploadFile = File(..., description="The file to upload"),
    metadata: str | None = Form(
        None,
        description="Optional JSON string of key-value metadata",
    ),
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """Upload a new document.

    Accepts a file upload with optional JSON metadata.
    The file is validated for type and size before being stored.
    """
    content = await file.read()
    parsed_metadata: dict[str, Any] = {}
    if metadata:
        parsed_metadata = json.loads(metadata)

    document = await service.upload(
        filename=file.filename or "unknown",
        content=content,
        metadata=parsed_metadata,
    )

    return DocumentUploadResponse.model_validate(document)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Get a paginated list of documents with optional status and search filters.",
)
async def list_documents(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=200, description="Maximum records to return"),
    status: str | None = Query(None, description="Filter by document status"),
    search: str | None = Query(None, description="Search by filename"),
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """List documents with pagination and filtering."""
    documents, total = await service.list_documents(
        skip=skip,
        limit=limit,
        status=status,
        search=search,
    )

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document",
    description="Retrieve a single document by its ID.",
)
async def get_document(
    document_id: int,
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """Get a document by ID."""
    document = await service.get(document_id)
    return DocumentResponse.model_validate(document)


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete a document",
    description="Delete a document and its associated file from disk.",
)
async def delete_document(
    document_id: int,
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """Delete a document by ID."""
    await service.delete(document_id)
    return DocumentDeleteResponse(id=document_id)


@router.patch(
    "/{document_id}/metadata",
    response_model=DocumentResponse,
    summary="Update document metadata",
    description="Update the metadata of a document. Merges with existing metadata.",
)
async def update_document_metadata(
    document_id: int,
    body: DocumentUpdateMetadata,
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """Update the metadata of a document."""
    document = await service.update_metadata(
        document_id=document_id,
        metadata=body.metadata,
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/versions",
    response_model=DocumentVersionListResponse,
    summary="Get document versions",
    description="Get the version history for a document.",
)
async def get_document_versions(
    document_id: int,
    service: DocumentService = Depends(_get_document_service),
) -> Any:
    """Get version history for a document."""
    versions = await service.get_versions(document_id)
    return DocumentVersionListResponse(
        document_id=document_id,
        versions=[DocumentVersionResponse.model_validate(v) for v in versions],
    )
