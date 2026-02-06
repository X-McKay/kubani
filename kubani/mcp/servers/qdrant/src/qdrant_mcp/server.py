"""
Qdrant MCP Server implementation.

Provides MCP tools for vector search and semantic memory operations.
Enables agents and Claude Code to store, search, and manage embeddings.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from kubani.framework.mcp.server.health import HealthCheckManager
from kubani.framework.mcp.server.metrics import MetricsCollector
from kubani.framework.mcp.server.registry import RegistryClient
from qdrant_mcp.models import (
    CollectionInfo,
    CollectionsResult,
    PointResult,
    SearchResult,
    SearchResults,
    UpsertResult,
)

logger = logging.getLogger(__name__)

# Global Qdrant client
_qdrant_client: AsyncQdrantClient | None = None

# Default embedding dimension (OpenAI ada-002 compatible)
DEFAULT_VECTOR_SIZE = 1536

# Global framework components
_health_manager: HealthCheckManager | None = None
_metrics_collector: MetricsCollector | None = None
_registry_client: RegistryClient | None = None
_heartbeat_task: asyncio.Task | None = None


async def connect_qdrant() -> AsyncQdrantClient:
    """Connect to Qdrant at server startup."""
    global _qdrant_client

    if _qdrant_client is not None:
        return _qdrant_client

    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))
    api_key = os.environ.get("QDRANT_API_KEY")
    https = os.environ.get("QDRANT_HTTPS", "false").lower() == "true"

    logger.info(f"Connecting to Qdrant at {host}:{port}...")

    if api_key:
        _qdrant_client = AsyncQdrantClient(
            host=host,
            port=port,
            api_key=api_key,
            https=https,
            check_compatibility=False,  # Allow version mismatch
        )
    else:
        _qdrant_client = AsyncQdrantClient(
            host=host,
            port=port,
            https=https,
            check_compatibility=False,  # Allow version mismatch
        )

    logger.info("Qdrant client connected")
    return _qdrant_client


async def disconnect_qdrant() -> None:
    """Disconnect from Qdrant at server shutdown."""
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None


def _get_client_or_error() -> AsyncQdrantClient:
    """Get the Qdrant client or raise an error."""
    if _qdrant_client is None:
        raise RuntimeError(
            "Qdrant client not initialized. Ensure connect_qdrant() was called at server startup."
        )
    return _qdrant_client


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP session lifespan."""
    global _health_manager, _metrics_collector, _registry_client, _heartbeat_task
    
    # Initialize framework components
    _health_manager = HealthCheckManager(version="1.0.0")
    _metrics_collector = MetricsCollector(server_name="qdrant-mcp")
    
    # Register health check for Qdrant
    async def check_qdrant():
        """Check if Qdrant is accessible."""
        try:
            client = _get_client_or_error()
            # Try to list collections as a health check
            await client.get_collections()
            return True
        except Exception:
            return False
    
    _health_manager.register("qdrant", check_qdrant, timeout=5.0)
    
    # Register with registry if URL provided
    registry_url = os.environ.get("REGISTRY_URL")
    if registry_url:
        _registry_client = RegistryClient(
            registry_url=registry_url,
            server_id="qdrant-mcp",
        )
        
        # Get connection config from environment
        external_url = os.environ.get("EXTERNAL_URL", "http://qdrant-mcp.almckay.io/sse")
        internal_url = os.environ.get("INTERNAL_URL", "http://qdrant-mcp-server.ai-agents.svc:8080/sse")
        
        # Get tool names for capabilities
        capabilities = [
            "list_collections",
            "create_collection",
            "delete_collection",
            "get_collection_info",
            "upsert_vectors",
            "search_vectors",
            "get_point",
            "delete_points",
            "scroll_points",
            "count_points",
        ]
        
        await _registry_client.register(
            name="Qdrant MCP Server",
            description="Vector database for semantic search and memory",
            transport="sse",
            connection_config={
                "url": external_url,
                "internal_url": internal_url,
            },
            capabilities=capabilities,
        )
        
        # Start heartbeat task
        async def get_backend_status():
            health = await _health_manager.check_all()
            return {name: backend.status.value for name, backend in health.backends.items()}
        
        _heartbeat_task = asyncio.create_task(
            _registry_client.start_heartbeat(interval=30, get_backend_status=get_backend_status)
        )
    
    yield
    
    # Cleanup
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    
    if _registry_client:
        await _registry_client.unregister()


def create_server() -> FastMCP:
    """Create and configure the Qdrant MCP server."""
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Qdrant MCP Server",
        instructions=(
            "Vector database for semantic search and memory. "
            "Use these tools to store embeddings, perform similarity search, "
            "and manage vector collections for AI agent memory."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Collection Management Tools
    # =========================================================================

    @mcp.tool()
    async def list_collections() -> CollectionsResult:
        """
        List all collections in Qdrant.

        Returns:
            List of collection names and info
        """
        client = _get_client_or_error()
        collections = await client.get_collections()

        result = []
        for collection in collections.collections:
            info = await client.get_collection(collection.name)
            result.append(
                CollectionInfo(
                    name=collection.name,
                    vectors_count=info.vectors_count or 0,
                    points_count=info.points_count or 0,
                    status=str(info.status),
                )
            )

        return CollectionsResult(
            collections=result,
            count=len(result),
        )

    @mcp.tool()
    async def create_collection(
        name: str,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        distance: str = "cosine",
    ) -> CollectionInfo:
        """
        Create a new vector collection.

        Args:
            name: Collection name
            vector_size: Dimension of vectors (default: 1536 for OpenAI)
            distance: Distance metric: cosine, euclid, or dot (default: cosine)

        Returns:
            Information about the created collection
        """
        client = _get_client_or_error()

        distance_map = {
            "cosine": Distance.COSINE,
            "euclid": Distance.EUCLID,
            "dot": Distance.DOT,
        }
        dist = distance_map.get(distance.lower(), Distance.COSINE)

        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=dist,
            ),
        )

        return CollectionInfo(
            name=name,
            vectors_count=0,
            points_count=0,
            status="green",
        )

    @mcp.tool()
    async def delete_collection(
        name: str,
    ) -> dict[str, str]:
        """
        Delete a collection.

        Args:
            name: Collection name to delete

        Returns:
            Confirmation of deletion
        """
        client = _get_client_or_error()
        await client.delete_collection(collection_name=name)

        return {
            "status": "deleted",
            "collection": name,
        }

    @mcp.tool()
    async def get_collection_info(
        name: str,
    ) -> CollectionInfo:
        """
        Get detailed information about a collection.

        Args:
            name: Collection name

        Returns:
            Collection information
        """
        client = _get_client_or_error()
        info = await client.get_collection(name)

        return CollectionInfo(
            name=name,
            vectors_count=info.vectors_count or 0,
            points_count=info.points_count or 0,
            status=str(info.status),
        )

    # =========================================================================
    # Vector Operations Tools
    # =========================================================================

    @mcp.tool()
    async def upsert_vectors(
        collection: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> UpsertResult:
        """
        Insert or update vectors in a collection.

        Args:
            collection: Collection name
            vectors: List of embedding vectors
            payloads: Optional metadata for each vector
            ids: Optional IDs (auto-generated if not provided)

        Returns:
            Result of the upsert operation
        """
        client = _get_client_or_error()

        if ids is None:
            ids = [str(uuid4()) for _ in vectors]

        if payloads is None:
            payloads = [{} for _ in vectors]

        points = [
            PointStruct(
                id=id_,
                vector=vector,
                payload=payload,
            )
            for id_, vector, payload in zip(ids, vectors, payloads, strict=False)
        ]

        await client.upsert(
            collection_name=collection,
            points=points,
        )

        return UpsertResult(
            collection=collection,
            upserted_count=len(points),
            ids=ids,
        )

    @mcp.tool()
    async def search_vectors(
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filter_field: str | None = None,
        filter_value: str | None = None,
    ) -> SearchResults:
        """
        Search for similar vectors.

        Args:
            collection: Collection name
            query_vector: Query embedding vector
            limit: Maximum results to return (default: 10)
            score_threshold: Minimum similarity score (optional)
            filter_field: Field name to filter on (optional)
            filter_value: Value to match for filter (optional)

        Returns:
            Search results with scores and payloads
        """
        client = _get_client_or_error()

        query_filter = None
        if filter_field and filter_value:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key=filter_field,
                        match=MatchValue(value=filter_value),
                    )
                ]
            )

        results = await client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        )

        return SearchResults(
            results=[
                SearchResult(
                    id=str(r.id),
                    score=r.score,
                    payload=r.payload or {},
                )
                for r in results
            ],
            count=len(results),
        )

    @mcp.tool()
    async def get_point(
        collection: str,
        point_id: str,
    ) -> PointResult:
        """
        Get a specific point by ID.

        Args:
            collection: Collection name
            point_id: Point ID to retrieve

        Returns:
            Point data including vector and payload
        """
        client = _get_client_or_error()

        points = await client.retrieve(
            collection_name=collection,
            ids=[point_id],
            with_vectors=True,
            with_payload=True,
        )

        if not points:
            raise ValueError(f"Point {point_id} not found in collection {collection}")

        point = points[0]
        return PointResult(
            id=str(point.id),
            vector=point.vector if isinstance(point.vector, list) else [],
            payload=point.payload or {},
        )

    @mcp.tool()
    async def delete_points(
        collection: str,
        point_ids: list[str],
    ) -> dict[str, Any]:
        """
        Delete points by IDs.

        Args:
            collection: Collection name
            point_ids: List of point IDs to delete

        Returns:
            Confirmation of deletion
        """
        client = _get_client_or_error()

        await client.delete(
            collection_name=collection,
            points_selector=point_ids,
        )

        return {
            "status": "deleted",
            "collection": collection,
            "deleted_count": len(point_ids),
        }

    @mcp.tool()
    async def scroll_points(
        collection: str,
        limit: int = 100,
        offset: str | None = None,
        filter_field: str | None = None,
        filter_value: str | None = None,
    ) -> dict[str, Any]:
        """
        Scroll through all points in a collection.

        Args:
            collection: Collection name
            limit: Number of points per page (default: 100)
            offset: Offset for pagination (from previous scroll)
            filter_field: Field name to filter on (optional)
            filter_value: Value to match for filter (optional)

        Returns:
            Points and next offset for pagination
        """
        client = _get_client_or_error()

        query_filter = None
        if filter_field and filter_value:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key=filter_field,
                        match=MatchValue(value=filter_value),
                    )
                ]
            )

        records, next_offset = await client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            scroll_filter=query_filter,
            with_payload=True,
            with_vectors=False,
        )

        return {
            "points": [
                {
                    "id": str(r.id),
                    "payload": r.payload or {},
                }
                for r in records
            ],
            "next_offset": str(next_offset) if next_offset else None,
            "count": len(records),
        }

    # =========================================================================
    # Utility Tools
    # =========================================================================

    @mcp.tool()
    async def count_points(
        collection: str,
        filter_field: str | None = None,
        filter_value: str | None = None,
    ) -> dict[str, int]:
        """
        Count points in a collection.

        Args:
            collection: Collection name
            filter_field: Field name to filter on (optional)
            filter_value: Value to match for filter (optional)

        Returns:
            Count of points
        """
        client = _get_client_or_error()

        query_filter = None
        if filter_field and filter_value:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key=filter_field,
                        match=MatchValue(value=filter_value),
                    )
                ]
            )

        if _metrics_collector:
            with _metrics_collector.track_request("count_points"):
                with _metrics_collector.track_backend("qdrant"):
                    result = await client.count(
                        collection_name=collection,
                        count_filter=query_filter,
                    )
        else:
            result = await client.count(
                collection_name=collection,
                count_filter=query_filter,
            )

        return {
            "collection": collection,
            "count": result.count,
        }
    
    # =========================================================================
    # Health and Metrics Tools
    # =========================================================================

    @mcp.tool()
    async def health() -> dict[str, Any]:
        """
        Check the health of the Qdrant MCP server.

        Returns:
            Health status including Qdrant connectivity
        """
        if _health_manager:
            health_response = await _health_manager.check_all()
            return health_response.to_dict()
        
        # Fallback if health manager not initialized
        try:
            client = _get_client_or_error()
            await client.get_collections()
            return {
                "status": "healthy",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
    
    @mcp.tool()
    async def metrics() -> dict[str, Any]:
        """
        Get Prometheus metrics for the Qdrant MCP server.

        Returns:
            Metrics in Prometheus format
        """
        if _metrics_collector:
            metrics_data = _metrics_collector.get_metrics()
            return {
                "content_type": "text/plain; version=0.0.4",
                "body": metrics_data.decode("utf-8"),
            }
        return {
            "error": "Metrics collector not initialized",
        }

    return mcp


def main():
    """Entry point for the Qdrant MCP server."""
    import sys

    import anyio
    from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with connection management
    async def run_with_qdrant():
        try:
            await connect_qdrant()
            await run_server_async(mcp, config)
        finally:
            await disconnect_qdrant()

    anyio.run(run_with_qdrant)


# Alias for backward compatibility
run = main


if __name__ == "__main__":
    run()
