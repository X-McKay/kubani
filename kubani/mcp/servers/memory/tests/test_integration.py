"""
Memory MCP Server Integration Tests.

Tests the generic memory interface with real backends (Qdrant, Neo4j, Redis).
These tests require the services to be running.

Run with: pytest tests/test_integration.py -m integration
"""

import os
import pytest
from datetime import datetime
from uuid import uuid4

from memory_mcp.backends import CacheBackend, GraphBackend, VectorBackend
from memory_mcp.models import MemoryObject, MemoryRelation


# Skip integration tests if services are not available
def is_service_available(host: str, port: int) -> bool:
    """Check if a service is available."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# Service availability checks
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
NEO4J_HOST = os.environ.get("NEO4J_HOST", "localhost")
NEO4J_PORT = int(os.environ.get("NEO4J_BOLT_PORT", "7687"))
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

QDRANT_AVAILABLE = is_service_available(QDRANT_HOST, QDRANT_PORT)
NEO4J_AVAILABLE = is_service_available(NEO4J_HOST, NEO4J_PORT)
REDIS_AVAILABLE = is_service_available(REDIS_HOST, REDIS_PORT)


@pytest.mark.integration
class TestVectorBackendIntegration:
    """Integration tests for VectorBackend with real Qdrant."""

    @pytest.fixture
    async def vector_backend(self):
        """Create and connect a VectorBackend."""
        if not QDRANT_AVAILABLE:
            pytest.skip(f"Qdrant not available at {QDRANT_HOST}:{QDRANT_PORT}")

        backend = VectorBackend(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            api_key=os.environ.get("QDRANT_API_KEY"),
        )
        await backend.connect()
        yield backend
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_store_and_search_round_trip(self, vector_backend):
        """Store object, verify it's searchable."""
        object_id = f"test-{uuid4()}"

        await vector_backend.store_object(
            object_id=object_id,
            object_type="document",
            namespace="integration-test",
            data={"title": "AI Technology News", "content": "Latest AI developments"},
            metadata={"source": "integration-test"},
            created_at=datetime.utcnow(),
        )

        # Search for it
        results = await vector_backend.search_objects(
            query="AI developments technology",
            namespace="integration-test",
            limit=10,
        )

        assert any(r.id == object_id for r in results), "Stored object not found in search"

    @pytest.mark.asyncio
    async def test_get_object_by_id(self, vector_backend):
        """Store and retrieve object by ID."""
        object_id = f"test-get-{uuid4()}"

        await vector_backend.store_object(
            object_id=object_id,
            object_type="analysis",
            namespace="integration-test",
            data={"summary": "Test analysis summary"},
            metadata={"author": "test"},
            created_at=datetime.utcnow(),
        )

        result = await vector_backend.get_object(object_id)

        assert result is not None
        assert result.id == object_id
        assert result.type == "analysis"
        assert result.data["summary"] == "Test analysis summary"

    @pytest.mark.asyncio
    async def test_list_objects_with_filters(self, vector_backend):
        """List objects with type and namespace filters."""
        # Store a few objects
        for i in range(3):
            await vector_backend.store_object(
                object_id=f"list-test-{uuid4()}",
                object_type="trend",
                namespace="list-test",
                data={"name": f"Trend {i}"},
                metadata={},
                created_at=datetime.utcnow(),
            )

        results = await vector_backend.list_objects(
            object_type="trend",
            namespace="list-test",
            limit=10,
        )

        assert len(results) >= 3
        assert all(r.type == "trend" for r in results)


@pytest.mark.integration
class TestGraphBackendIntegration:
    """Integration tests for GraphBackend with real Neo4j."""

    @pytest.fixture
    async def graph_backend(self):
        """Create and connect a GraphBackend."""
        if not NEO4J_AVAILABLE:
            pytest.skip(f"Neo4j not available at {NEO4J_HOST}:{NEO4J_PORT}")

        backend = GraphBackend(
            uri=f"bolt://{NEO4J_HOST}:{NEO4J_PORT}",
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", ""),
        )
        await backend.connect()
        yield backend
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_create_and_link_nodes(self, graph_backend):
        """Create two nodes and link them."""
        doc_id = f"doc-{uuid4()}"
        analysis_id = f"analysis-{uuid4()}"

        # Create nodes
        await graph_backend.create_memory_node(
            object_id=doc_id,
            object_type="document",
            namespace="integration-test",
        )
        await graph_backend.create_memory_node(
            object_id=analysis_id,
            object_type="analysis",
            namespace="integration-test",
        )

        # Link them
        created = await graph_backend.create_memory_relation(
            source_id=analysis_id,
            target_id=doc_id,
            relation_type="ANALYZED_FROM",
        )

        assert created is True

        # Get relations
        relations = await graph_backend.get_object_relations(analysis_id)

        assert any(r.target_id == doc_id for r in relations)

    @pytest.mark.asyncio
    async def test_relation_not_duplicated(self, graph_backend):
        """Verify creating same relation twice doesn't duplicate."""
        source_id = f"source-{uuid4()}"
        target_id = f"target-{uuid4()}"

        await graph_backend.create_memory_node(source_id, "test", "test")
        await graph_backend.create_memory_node(target_id, "test", "test")

        # First creation
        created1 = await graph_backend.create_memory_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type="TEST_RELATION",
        )

        # Second creation (same relation)
        created2 = await graph_backend.create_memory_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type="TEST_RELATION",
        )

        assert created1 is True
        assert created2 is False


@pytest.mark.integration
class TestCacheBackendIntegration:
    """Integration tests for CacheBackend with real Redis."""

    @pytest.fixture
    async def cache_backend(self):
        """Create and connect a CacheBackend."""
        if not REDIS_AVAILABLE:
            pytest.skip(f"Redis not available at {REDIS_HOST}:{REDIS_PORT}")

        backend = CacheBackend(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=os.environ.get("REDIS_PASSWORD"),
        )
        await backend.connect()
        yield backend
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_check_seen_mark_seen_flow(self, cache_backend):
        """Test deduplication flow."""
        key = f"url-hash-{uuid4()}"
        namespace = "integration-test"

        # First check - not seen
        seen1 = await cache_backend.check_seen(key=key, namespace=namespace)
        assert seen1 is False

        # Mark as seen
        await cache_backend.mark_seen(key=key, namespace=namespace)

        # Second check - seen
        seen2 = await cache_backend.check_seen(key=key, namespace=namespace)
        assert seen2 is True

    @pytest.mark.asyncio
    async def test_mark_seen_with_ttl(self, cache_backend):
        """Test mark_seen with TTL."""
        key = f"ttl-test-{uuid4()}"
        namespace = "integration-test"

        await cache_backend.mark_seen(key=key, namespace=namespace, ttl_seconds=60)

        seen = await cache_backend.check_seen(key=key, namespace=namespace)
        assert seen is True


@pytest.mark.integration
class TestMemoryMCPIntegration:
    """Full integration tests with all backends."""

    @pytest.fixture
    async def all_backends(self):
        """Create all backends for full integration test."""
        if not all([QDRANT_AVAILABLE, NEO4J_AVAILABLE, REDIS_AVAILABLE]):
            pytest.skip("Not all services available for full integration test")

        vector = VectorBackend(host=QDRANT_HOST, port=QDRANT_PORT)
        graph = GraphBackend(
            uri=f"bolt://{NEO4J_HOST}:{NEO4J_PORT}",
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", ""),
        )
        cache = CacheBackend(host=REDIS_HOST, port=REDIS_PORT)

        await vector.connect()
        await graph.connect()
        await cache.connect()

        yield vector, graph, cache

        await vector.disconnect()
        await graph.disconnect()
        await cache.disconnect()

    @pytest.mark.asyncio
    async def test_full_document_flow(self, all_backends):
        """Test storing document, creating analysis, and linking them."""
        vector, graph, cache = all_backends

        # 1. Check if URL has been seen (dedup)
        url_hash = f"url-{uuid4()}"
        seen = await cache.check_seen(key=url_hash, namespace="news/articles")
        assert seen is False

        # 2. Store document
        doc_id = f"doc-{uuid4()}"
        await vector.store_object(
            object_id=doc_id,
            object_type="document",
            namespace="news/articles",
            data={
                "title": "AI Breakthrough",
                "content": "Researchers announced a major AI breakthrough...",
                "url": f"https://example.com/{doc_id}",
            },
            metadata={"source": "example.com", "published_at": datetime.utcnow().isoformat()},
            created_at=datetime.utcnow(),
        )
        await graph.create_memory_node(doc_id, "document", "news/articles")

        # 3. Mark URL as seen
        await cache.mark_seen(key=url_hash, namespace="news/articles", ttl_seconds=86400)

        # 4. Create analysis
        analysis_id = f"analysis-{uuid4()}"
        await vector.store_object(
            object_id=analysis_id,
            object_type="analysis",
            namespace="news/analyses",
            data={
                "summary": "This article discusses a significant AI breakthrough...",
                "importance_score": 8,
                "entities": ["AI", "research", "breakthrough"],
            },
            metadata={"analyzed_at": datetime.utcnow().isoformat()},
            created_at=datetime.utcnow(),
        )
        await graph.create_memory_node(analysis_id, "analysis", "news/analyses")

        # 5. Link analysis to document
        await graph.create_memory_relation(
            source_id=analysis_id,
            target_id=doc_id,
            relation_type="ANALYZED_FROM",
        )

        # 6. Verify document is searchable
        docs = await vector.search_objects(query="AI breakthrough research", limit=10)
        assert any(d.id == doc_id for d in docs)

        # 7. Verify relation exists
        relations = await graph.get_object_relations(analysis_id)
        assert any(r.target_id == doc_id and r.relation_type == "ANALYZED_FROM" for r in relations)

        # 8. Verify dedup works
        seen_after = await cache.check_seen(key=url_hash, namespace="news/articles")
        assert seen_after is True

    @pytest.mark.asyncio
    async def test_data_lineage_chain(self, all_backends):
        """Test creating a chain: document -> analysis -> trend."""
        vector, graph, cache = all_backends

        # Create document
        doc_id = f"lineage-doc-{uuid4()}"
        await vector.store_object(
            object_id=doc_id,
            object_type="document",
            namespace="lineage-test",
            data={"title": "Lineage Test Doc"},
            metadata={},
            created_at=datetime.utcnow(),
        )
        await graph.create_memory_node(doc_id, "document", "lineage-test")

        # Create analysis linked to document
        analysis_id = f"lineage-analysis-{uuid4()}"
        await vector.store_object(
            object_id=analysis_id,
            object_type="analysis",
            namespace="lineage-test",
            data={"summary": "Analysis of lineage doc"},
            metadata={},
            created_at=datetime.utcnow(),
        )
        await graph.create_memory_node(analysis_id, "analysis", "lineage-test")
        await graph.create_memory_relation(analysis_id, doc_id, "ANALYZED_FROM")

        # Create trend linked to analysis
        trend_id = f"lineage-trend-{uuid4()}"
        await vector.store_object(
            object_id=trend_id,
            object_type="trend",
            namespace="lineage-test",
            data={"name": "Emerging Trend", "velocity": "rising"},
            metadata={},
            created_at=datetime.utcnow(),
        )
        await graph.create_memory_node(trend_id, "trend", "lineage-test")
        await graph.create_memory_relation(trend_id, analysis_id, "DETECTED_FROM")

        # Verify chain
        trend_relations = await graph.get_object_relations(trend_id)
        assert any(r.target_id == analysis_id for r in trend_relations)

        analysis_relations = await graph.get_object_relations(analysis_id)
        assert any(r.target_id == doc_id for r in analysis_relations)
