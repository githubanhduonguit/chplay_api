"""
Qdrant vector store service.

Provides high-level operations for:
- Collection management (create, delete, list, info)
- Point operations (upsert, batch upsert, delete)
- Search (vector search, hybrid search)
- Pagination (scroll)
- Filter and payload management

Uses the low-level QdrantClientWrapper for actual Qdrant communication.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client.http import models as qdrant_models

from app.core.config import settings
from app.core.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    VectorDBError,
)
from app.services.qdrant.client import QdrantClientWrapper
from app.services.qdrant.schemas import (
    CollectionConfig,
    CollectionInfo,
    CollectionListResponse,
    DeleteResponse,
    HybridSearchQuery,
    PointUpsert,
    ScoredPoint,
    ScrollQuery,
    ScrollResponse,
    SearchQuery,
    SearchResponse,
    UpsertResponse,
)

logger = logging.getLogger(__name__)


class QdrantService:
    """High-level service for Qdrant vector database operations.

    Provides a clean domain-oriented API that maps to the
    underlying Qdrant client with proper error handling.
    """

    def __init__(self, client: QdrantClientWrapper | None = None) -> None:
        self.client = client or QdrantClientWrapper()

    # ── Collection Management ────────────────────────────────────────

    async def create_collection(self, config: CollectionConfig) -> CollectionInfo:
        """Create a new collection.

        Args:
            config: Collection configuration (name, vector_size, distance, etc.).

        Returns:
            Information about the created collection.

        Raises:
            CollectionAlreadyExistsError: If the collection already exists.
        """
        exists = await self.client.collection_exists(config.name)
        if exists:
            raise CollectionAlreadyExistsError(config.name)

        distance_map: dict[str, qdrant_models.Distance] = {
            "Cosine": qdrant_models.Distance.COSINE,
            "Dot": qdrant_models.Distance.DOT,
            "Euclid": qdrant_models.Distance.EUCLID,
        }

        vectors_config = qdrant_models.VectorParams(
            size=config.vector_size,
            distance=distance_map.get(config.distance, qdrant_models.Distance.COSINE),
            on_disk=config.on_disk,
        )

        hnsw_config = None
        if config.hnsw_m is not None or config.hnsw_ef_construct is not None:
            hnsw_config = qdrant_models.HnswConfigDiff(
                m=config.hnsw_m,
                ef_construct=config.hnsw_ef_construct,
            )

        await self.client.create_collection(
            collection_name=config.name,
            vectors_config=vectors_config,
            hnsw_config=hnsw_config,
        )

        return await self.get_collection_info(config.name)

    async def delete_collection(self, name: str) -> DeleteResponse:
        """Delete a collection.

        Args:
            name: Name of the collection to delete.

        Returns:
            A DeleteResponse indicating success.
        """
        await self.client.delete_collection(name)
        return DeleteResponse(status="ok")

    async def list_collections(self) -> CollectionListResponse:
        """List all collections with their information.

        Returns:
            A CollectionListResponse with all collections.
        """
        names = await self.client.list_collections()
        collections = []
        for name in names:
            try:
                info = await self.get_collection_info(name)
                collections.append(info)
            except VectorDBError:
                # Include minimal info if detailed fetch fails
                collections.append(
                    CollectionInfo(name=name, vector_size=0, distance="unknown"),
                )
        return CollectionListResponse(collections=collections)

    async def get_collection_info(self, name: str) -> CollectionInfo:
        """Get detailed information about a collection.

        Args:
            name: Name of the collection.

        Returns:
            CollectionInfo with details.

        Raises:
            CollectionNotFoundError: If the collection does not exist.
        """
        info = await self.client.get_collection_info(name)

        # Extract vector config info
        vector_config = info.config.params.vectors
        if isinstance(vector_config, dict):
            # Multiple named vectors — use the first one
            first_key = next(iter(vector_config))
            v_conf = vector_config[first_key]
            vector_size = v_conf.size
            distance = str(v_conf.distance)
        else:
            vector_size = vector_config.size
            distance = str(vector_config.distance)

        return CollectionInfo(
            name=name,
            vector_size=vector_size,
            distance=distance,
            points_count=info.points_count,
            status=info.status,
        )

    # ── Point Operations ─────────────────────────────────────────────

    async def upsert_points(self, collection: str, points: list[PointUpsert]) -> UpsertResponse:
        """Upsert points into a collection.

        Args:
            collection: Name of the collection.
            points: List of points to upsert.

        Returns:
            UpsertResponse with the number of points upserted.

        Raises:
            VectorDBError: If the operation fails.
        """
        point_structs = [self._to_point_struct(p) for p in points]
        await self.client.upsert_points(collection, point_structs)
        return UpsertResponse(status="ok", points_count=len(points))

    async def batch_upsert_points(
        self,
        collection: str,
        points: list[PointUpsert],
        batch_size: int = 256,
    ) -> UpsertResponse:
        """Upsert points in batches to avoid large payloads.

        Args:
            collection: Name of the collection.
            points: List of points to upsert.
            batch_size: Maximum points per batch.

        Returns:
            UpsertResponse with the total number of points upserted.

        Raises:
            VectorDBError: If any batch fails.
        """
        total = len(points)
        for i in range(0, total, batch_size):
            batch = points[i : i + batch_size]
            point_structs = [self._to_point_struct(p) for p in batch]
            await self.client.upsert_points(collection, point_structs)
            logger.debug("Upserted batch %d/%d (%d points)", i // batch_size + 1, (total + batch_size - 1) // batch_size, len(batch))  # fmt: skip

        return UpsertResponse(status="ok", points_count=total)

    async def delete_points(self, collection: str, point_ids: list[str | int]) -> DeleteResponse:
        """Delete points by their IDs.

        Args:
            collection: Name of the collection.
            point_ids: IDs of points to delete.

        Returns:
            DeleteResponse indicating success.
        """
        await self.client.delete_points(collection, point_ids)
        return DeleteResponse(status="ok")

    async def delete_points_by_document_id(
        self,
        collection: str,
        document_id: int,
    ) -> DeleteResponse:
        """Delete all points belonging to a specific document.

        Args:
            collection: Name of the collection.
            document_id: The document ID to filter by.

        Returns:
            DeleteResponse indicating success.
        """
        qdrant_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="document_id",
                    match=qdrant_models.MatchValue(value=document_id),
                ),
            ],
        )
        await self.client.delete_points_by_filter(collection, qdrant_filter)
        return DeleteResponse(status="ok")

    # ── Search Operations ────────────────────────────────────────────

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Search for the nearest vectors.

        Args:
            query: Search parameters including vector, limit, filter.

        Returns:
            SearchResponse with ranked results.

        Raises:
            CollectionNotFoundError: If the collection does not exist.
        """
        qdrant_filter = self._build_filter(query.filter_conditions) if query.filter_conditions else None  # fmt: skip

        results = await self.client.search_points(
            collection_name=query.collection,
            query_vector=query.vector,
            limit=query.limit,
            score_threshold=query.score_threshold,
            query_filter=qdrant_filter,
            with_payload=query.with_payload,
            with_vector=query.with_vector,
        )

        return self._to_search_response(results, query.collection)

    async def hybrid_search(self, query: HybridSearchQuery) -> SearchResponse:
        """Hybrid search using vector similarity with optional pre-filter.

        Note: True hybrid search (vector + keyword fusion) is handled
        at the retrieval layer (Bước 8). This performs vector search
        with keyword-based pre-filtering.

        Args:
            query: Hybrid search parameters.

        Returns:
            SearchResponse with ranked results.
        """
        qdrant_filter = self._build_filter(query.keyword_filter) if query.keyword_filter else None  # fmt: skip

        results = await self.client.search_points(
            collection_name=query.collection,
            query_vector=query.vector,
            limit=query.limit,
            score_threshold=query.score_threshold,
            query_filter=qdrant_filter,
            with_payload=query.with_payload,
        )

        return self._to_search_response(results, query.collection)

    async def scroll(self, query: ScrollQuery) -> ScrollResponse:
        """Scroll through points with pagination.

        Args:
            query: Scroll parameters including limit, offset, filter.

        Returns:
            ScrollResponse with points and next offset for pagination.
        """
        qdrant_filter = self._build_filter(query.filter_conditions) if query.filter_conditions else None  # fmt: skip

        records, next_offset = await self.client.scroll_points(
            collection_name=query.collection,
            limit=query.limit,
            offset=query.offset,
            query_filter=qdrant_filter,
            with_payload=query.with_payload,
            with_vector=query.with_vector,
        )

        # Scroll results don't have relevance scores; use 0.0 to indicate no ranking
        points = [
            ScoredPoint(
                id=r.id,
                score=0.0,
                payload=r.payload or {},
                vector=r.vector if isinstance(r.vector, list) else None,
            )
            for r in records
        ]

        return ScrollResponse(
            points=points,
            next_offset=next_offset,
        )

    async def count_points(
        self,
        collection: str,
        filter_conditions: dict[str, Any] | None = None,
    ) -> int:
        """Count points in a collection.

        Args:
            collection: Name of the collection.
            filter_conditions: Optional filter to apply.

        Returns:
            The number of matching points.
        """
        qdrant_filter = self._build_filter(filter_conditions) if filter_conditions else None  # fmt: skip
        return await self.client.count_points(collection, qdrant_filter)

    # ── Internal helpers ─────────────────────────────────────────────

    def _to_point_struct(self, point: PointUpsert) -> qdrant_models.PointStruct:
        """Convert a PointUpsert schema to a Qdrant PointStruct.

        Args:
            point: The domain point to convert.

        Returns:
            A Qdrant PointStruct ready for upsert.
        """
        payload: dict[str, Any] = {}
        meta = point.metadata

        if meta.document_id is not None:
            payload["document_id"] = meta.document_id
        if meta.chunk_id is not None:
            payload["chunk_id"] = meta.chunk_id
        if meta.text is not None:
            payload["text"] = meta.text
        if meta.filename is not None:
            payload["filename"] = meta.filename
        if meta.chunk_index is not None:
            payload["chunk_index"] = meta.chunk_index
        payload.update(meta.additional)  # Include extra metadata

        return qdrant_models.PointStruct(
            id=point.id,
            vector=point.vector,
            payload=payload,
        )

    def _to_search_response(
        self,
        scored_points: list[qdrant_models.ScoredPoint],
        collection: str,
    ) -> SearchResponse:
        """Convert Qdrant ScoredPoint list to a SearchResponse.

        Args:
            scored_points: Raw results from Qdrant.
            collection: The collection name.

        Returns:
            A formatted SearchResponse.
        """
        results = [
            ScoredPoint(
                id=p.id,
                score=p.score,
                payload=p.payload or {},
                vector=p.vector if isinstance(p.vector, list) else None,
            )
            for p in scored_points
        ]
        return SearchResponse(results=results, collection=collection)

    @staticmethod
    def _build_filter(conditions: dict[str, Any]) -> qdrant_models.Filter:
        """Build a Qdrant Filter from a dictionary of conditions.

        Supports:
        - Simple field matches: {"field_name": value}
        - Range: {"field_name": {"gte": 0, "lte": 100}}
        - Pre-built must/should: {"must": [Condition, ...], "should": [Condition, ...]}

        Args:
            conditions: Dictionary of filter conditions.

        Returns:
            A configured Qdrant Filter.
        """
        must_conditions: list[qdrant_models.Condition] = []
        should_conditions: list[qdrant_models.Condition] | None = None

        for key, value in conditions.items():
            if key == "must" and isinstance(value, list):
                must_conditions.extend(value)
            elif key == "should" and isinstance(value, list):
                if should_conditions is None:
                    should_conditions = []
                should_conditions.extend(value)
            elif isinstance(value, dict) and any(k in value for k in ("gte", "lte", "gt", "lt")):
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        range=qdrant_models.Range(
                            gte=value.get("gte"),
                            lte=value.get("lte"),
                            gt=value.get("gt"),
                            lt=value.get("lt"),
                        ),
                    ),
                )
            elif isinstance(value, list):
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchAny(any=value),
                    ),
                )
            else:
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    ),
                )

        return qdrant_models.Filter(
            must=must_conditions,
            should=should_conditions,
        )
