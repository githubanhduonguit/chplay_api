"""
Qdrant async client wrapper.

Manages the connection to Qdrant and provides low-level
operations with retry and timeout support.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.core.exceptions import (
    CollectionNotFoundError,
    VectorDBError,
)

logger = logging.getLogger(__name__)


class QdrantClientWrapper:
    """Wrapper around AsyncQdrantClient with connection management.

    Provides a singleton-style access to the Qdrant async client
    with consistent error handling.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        prefer_grpc: bool = False,
    ) -> None:
        self.url = url or settings.QDRANT_URL
        self.api_key = api_key or settings.QDRANT_API_KEY
        self.prefer_grpc = prefer_grpc
        self._client: AsyncQdrantClient | None = None

    # ── Client lifecycle ─────────────────────────────────────────────

    async def get_client(self) -> AsyncQdrantClient:
        """Get or create the async Qdrant client.

        Returns:
            An initialized AsyncQdrantClient instance.
        """
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key,
                prefer_grpc=self.prefer_grpc,
                timeout=settings.TIMEOUT_SECONDS,
            )
        return self._client

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    # ── Collection operations ────────────────────────────────────────

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists.

        Args:
            collection_name: Name of the collection.

        Returns:
            True if the collection exists, False otherwise.
        """
        client = await self.get_client()
        try:
            result = await client.collection_exists(collection_name)
            return result
        except Exception as e:
            raise VectorDBError(
                message=f"Failed to check collection existence: {e}",
                error_code="COLLECTION_CHECK_FAILED",
                details={"collection": collection_name},
            ) from e

    async def create_collection(
        self,
        collection_name: str,
        vectors_config: qdrant_models.VectorParams,
        hnsw_config: qdrant_models.HnswConfigDiff | None = None,
    ) -> bool:
        """Create a new collection.

        Args:
            collection_name: Name of the collection.
            vectors_config: Vector parameters configuration.
            hnsw_config: Optional HNSW index configuration.

        Returns:
            True if the collection was created successfully.

        Raises:
            VectorDBError: If the creation fails.
        """
        client = await self.get_client()
        try:
            result = await client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                hnsw_config=hnsw_config,
            )
            logger.info("Created collection '%s'", collection_name)
            return result
        except Exception as e:
            raise VectorDBError(
                message=f"Failed to create collection '{collection_name}': {e}",
                error_code="COLLECTION_CREATE_FAILED",
                details={"collection": collection_name},
            ) from e

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            True if the collection was deleted successfully.
        """
        client = await self.get_client()
        try:
            result = await client.delete_collection(collection_name=collection_name)
            logger.info("Deleted collection '%s'", collection_name)
            return result
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Failed to delete collection: {e}",
                error_code="COLLECTION_DELETE_FAILED",
            ) from e
        except Exception as e:
            raise VectorDBError(
                message=f"Failed to delete collection: {e}",
                error_code="COLLECTION_DELETE_FAILED",
            ) from e

    async def list_collections(self) -> list[str]:
        """List all collection names.

        Returns:
            A list of collection names.
        """
        client = await self.get_client()
        try:
            response = await client.get_collections()
            return [c.name for c in response.collections]
        except Exception as e:
            raise VectorDBError(
                message=f"Failed to list collections: {e}",
                error_code="COLLECTION_LIST_FAILED",
            ) from e

    async def get_collection_info(self, collection_name: str) -> qdrant_models.CollectionInfo:
        """Get detailed info about a collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            CollectionInfo with details about the collection.

        Raises:
            CollectionNotFoundError: If the collection does not exist.
        """
        client = await self.get_client()
        try:
            response = await client.get_collection(collection_name=collection_name)
            return response
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Failed to get collection info: {e}",
                error_code="COLLECTION_INFO_FAILED",
            ) from e

    # ── Point operations ─────────────────────────────────────────────

    async def upsert_points(
        self,
        collection_name: str,
        points: list[qdrant_models.PointStruct],
        wait: bool = True,
    ) -> qdrant_models.UpdateResult:
        """Upsert points into a collection.

        Args:
            collection_name: Name of the collection.
            points: List of PointStruct to upsert.
            wait: Wait for the operation to complete.

        Returns:
            UpdateResult with operation status.

        Raises:
            CollectionNotFoundError: If the collection does not exist.
        """
        client = await self.get_client()
        try:
            result = await client.upsert(
                collection_name=collection_name,
                points=points,
                wait=wait,
            )
            logger.debug("Upserted %d points into '%s'", len(points), collection_name)
            return result
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Failed to upsert points: {e}",
                error_code="POINT_UPSERT_FAILED",
            ) from e

    async def delete_points(
        self,
        collection_name: str,
        point_ids: list[str | int],
        wait: bool = True,
    ) -> qdrant_models.UpdateResult:
        """Delete points by their IDs.

        Args:
            collection_name: Name of the collection.
            point_ids: List of point IDs to delete.
            wait: Wait for the operation to complete.

        Returns:
            UpdateResult with operation status.
        """
        client = await self.get_client()
        try:
            result = await client.delete(
                collection_name=collection_name,
                points_selector=qdrant_models.PointIdsList(
                    points=point_ids,
                ),
                wait=wait,
            )
            logger.debug("Deleted %d points from '%s'", len(point_ids), collection_name)
            return result
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Failed to delete points: {e}",
                error_code="POINT_DELETE_FAILED",
            ) from e

    async def delete_points_by_filter(
        self,
        collection_name: str,
        filter_conditions: qdrant_models.Filter,
        wait: bool = True,
    ) -> qdrant_models.UpdateResult:
        """Delete points matching a filter.

        Args:
            collection_name: Name of the collection.
            filter_conditions: Qdrant filter to match points for deletion.
            wait: Wait for the operation to complete.

        Returns:
            UpdateResult with operation status.
        """
        client = await self.get_client()
        try:
            result = await client.delete(
                collection_name=collection_name,
                points_selector=qdrant_models.FilterSelector(
                    filter=filter_conditions,
                ),
                wait=wait,
            )
            logger.debug("Deleted filtered points from '%s'", collection_name)
            return result
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Failed to delete points by filter: {e}",
                error_code="POINT_DELETE_FAILED",
            ) from e

    # ── Search operations ────────────────────────────────────────────

    async def search_points(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        query_filter: qdrant_models.Filter | None = None,
        with_payload: bool = True,
        with_vector: bool = False,
    ) -> list[qdrant_models.ScoredPoint]:
        """Search for the nearest points to a query vector.

        Args:
            collection_name: Name of the collection.
            query_vector: The query embedding vector.
            limit: Maximum number of results.
            score_threshold: Minimum score threshold.
            query_filter: Optional filter to apply.
            with_payload: Include payload in results.
            with_vector: Include vector in results.

        Returns:
            A list of ScoredPoint sorted by score (descending).
        """
        client = await self.get_client()
        try:
            # qdrant-client >= 1.15: search() was replaced by query_points()
            response = await client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=with_payload,
                with_vectors=with_vector,
            )
            return response.points
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Search failed: {e}",
                error_code="SEARCH_FAILED",
            ) from e

    async def search_batch(
        self,
        collection_name: str,
        queries: list[qdrant_models.SearchRequest],
    ) -> list[list[qdrant_models.ScoredPoint]]:
        """Run multiple searches in batch.

        Args:
            collection_name: Name of the collection.
            queries: List of SearchRequest objects.

        Returns:
            A list of result lists, one per query.
        """
        client = await self.get_client()
        try:
            # qdrant-client >= 1.15: search_batch() was replaced by query_batch_points()
            requests = [
                qdrant_models.QueryRequest(
                    query=q.vector,
                    filter=q.filter,
                    limit=q.limit,
                    score_threshold=q.score_threshold,
                    with_payload=q.with_payload,
                    with_vector=q.with_vector,
                )
                for q in queries
            ]
            responses = await client.query_batch_points(
                collection_name=collection_name,
                requests=requests,
            )
            return [r.points for r in responses]
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Batch search failed: {e}",
                error_code="BATCH_SEARCH_FAILED",
            ) from e

    # ── Scroll / Pagination ──────────────────────────────────────────

    async def scroll_points(
        self,
        collection_name: str,
        limit: int = 100,
        offset: str | int | None = None,
        query_filter: qdrant_models.Filter | None = None,
        with_payload: bool = True,
        with_vector: bool = False,
    ) -> tuple[list[qdrant_models.Record], Any | None]:  # noqa: ANN401
        """Scroll through points with pagination.

        Args:
            collection_name: Name of the collection.
            limit: Maximum number of points to return.
            offset: Optional point ID to start from.
            query_filter: Optional filter to apply.
            with_payload: Include payload in results.
            with_vector: Include vector in results.

        Returns:
            A tuple of (list of records, next_offset).
        """
        client = await self.get_client()
        try:
            records, next_offset = await client.scroll(
                collection_name=collection_name,
                limit=limit,
                offset=offset,
                scroll_filter=query_filter,
                with_payload=with_payload,
                with_vector=with_vector,
            )
            return records, next_offset
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Scroll failed: {e}",
                error_code="SCROLL_FAILED",
            ) from e

    # ── Count ────────────────────────────────────────────────────────

    async def count_points(
        self,
        collection_name: str,
        query_filter: qdrant_models.Filter | None = None,
    ) -> int:
        """Count points in a collection.

        Args:
            collection_name: Name of the collection.
            query_filter: Optional filter to apply.

        Returns:
            The number of matching points.
        """
        client = await self.get_client()
        try:
            result = await client.count(
                collection_name=collection_name,
                count_filter=query_filter,
            )
            return result.count
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise CollectionNotFoundError(collection_name) from e
            raise VectorDBError(
                message=f"Count failed: {e}",
                error_code="COUNT_FAILED",
            ) from e
