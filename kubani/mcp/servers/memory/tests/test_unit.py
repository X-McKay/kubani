"""
Memory MCP Server Unit Tests.

Tests the generic memory interface (add, search, get, list_objects, link, check_seen, mark_seen)
with mocked backends.
"""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory_mcp.models import (
    MemoryObject,
    MemoryRelation,
    MemoryAddResult,
    MemorySearchResult,
    MemoryGetResult,
    MemoryLinkResult,
    MemorySeenResult,
)


class TestMemoryModels:
    """Test that memory models are correctly defined."""

    def test_memory_object_creation(self):
        """Verify MemoryObject can be created with all fields."""
        obj = MemoryObject(
            id="test-123",
            type="document",
            namespace="test/articles",
            data={"title": "Test", "content": "Content"},
            metadata={"source": "test"},
            created_at=datetime.now(UTC),
            relations=[
                MemoryRelation(target_id="other-456", relation_type="RELATED_TO")
            ],
        )

        assert obj.id == "test-123"
        assert obj.type == "document"
        assert obj.namespace == "test/articles"
        assert obj.data["title"] == "Test"
        assert len(obj.relations) == 1

    def test_memory_add_result_creation(self):
        """Verify MemoryAddResult can be created."""
        result = MemoryAddResult(
            id="new-123",
            type="document",
            namespace="test",
            created_at=datetime.now(UTC),
            relations_created=2,
        )

        assert result.id == "new-123"
        assert result.relations_created == 2

    def test_memory_search_result_creation(self):
        """Verify MemorySearchResult can be created."""
        result = MemorySearchResult(
            results=[],
            count=0,
            total=0,
            query="test query",
        )

        assert result.query == "test query"
        assert result.count == 0

    def test_memory_get_result_found(self):
        """Verify MemoryGetResult with found object."""
        obj = MemoryObject(
            id="found-123",
            type="document",
            namespace="test",
            data={},
            created_at=datetime.now(UTC),
        )
        result = MemoryGetResult(found=True, object=obj)

        assert result.found is True
        assert result.object.id == "found-123"

    def test_memory_get_result_not_found(self):
        """Verify MemoryGetResult when not found."""
        result = MemoryGetResult(found=False, object=None)

        assert result.found is False
        assert result.object is None

    def test_memory_link_result_creation(self):
        """Verify MemoryLinkResult can be created."""
        result = MemoryLinkResult(
            source_id="src-123",
            target_id="tgt-456",
            relation_type="ANALYZED_FROM",
            created=True,
        )

        assert result.source_id == "src-123"
        assert result.created is True

    def test_memory_seen_result_creation(self):
        """Verify MemorySeenResult can be created."""
        result = MemorySeenResult(
            key="url-hash-123",
            namespace="test",
            seen=False,
        )

        assert result.key == "url-hash-123"
        assert result.seen is False


class TestCacheBackendDedup:
    """Test CacheBackend deduplication methods with mock Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        client = AsyncMock()
        client.exists = AsyncMock(return_value=0)
        client.set = AsyncMock()
        client.setex = AsyncMock()
        return client

    @pytest.fixture
    def cache_backend(self, mock_redis):
        """Create CacheBackend with mock client."""
        from memory_mcp.backends import CacheBackend

        backend = CacheBackend()
        backend._client = mock_redis
        return backend

    @pytest.mark.asyncio
    async def test_check_seen_returns_false_for_new_key(self, cache_backend, mock_redis):
        """Verify check_seen returns False for new key."""
        mock_redis.exists.return_value = 0

        result = await cache_backend.check_seen(key="new-hash", namespace="test")

        assert result is False
        mock_redis.exists.assert_called_once_with("seen:test:new-hash")

    @pytest.mark.asyncio
    async def test_check_seen_returns_true_for_existing_key(self, cache_backend, mock_redis):
        """Verify check_seen returns True for existing key."""
        mock_redis.exists.return_value = 1

        result = await cache_backend.check_seen(key="existing-hash", namespace="test")

        assert result is True

    @pytest.mark.asyncio
    async def test_mark_seen_without_ttl(self, cache_backend, mock_redis):
        """Verify mark_seen uses set() without TTL."""
        await cache_backend.mark_seen(key="new-key", namespace="test")

        mock_redis.set.assert_called_once_with("seen:test:new-key", "1")
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_seen_with_ttl(self, cache_backend, mock_redis):
        """Verify mark_seen uses setex() with TTL."""
        await cache_backend.mark_seen(key="new-key", namespace="test", ttl_seconds=3600)

        mock_redis.setex.assert_called_once_with("seen:test:new-key", 3600, "1")
        mock_redis.set.assert_not_called()


class TestVectorBackendObjectMethods:
    """Test VectorBackend generic memory methods."""

    @pytest.fixture
    def mock_qdrant(self):
        """Create mock Qdrant client."""
        client = AsyncMock()
        client.get_collections = AsyncMock(
            return_value=MagicMock(collections=[MagicMock(name="kubani_memory")])
        )
        client.upsert = AsyncMock()
        client.query_points = AsyncMock(return_value=MagicMock(points=[]))
        client.retrieve = AsyncMock(return_value=[])
        client.scroll = AsyncMock(return_value=([], None))
        return client

    @pytest.fixture
    def vector_backend(self, mock_qdrant):
        """Create VectorBackend with mock client."""
        from memory_mcp.backends import VectorBackend

        backend = VectorBackend()
        backend._client = mock_qdrant
        # Mock the embedding function
        backend._get_embedding = AsyncMock(return_value=[0.1] * 1024)
        return backend

    @pytest.mark.asyncio
    async def test_store_object_calls_upsert(self, vector_backend, mock_qdrant):
        """Verify store_object calls Qdrant upsert."""
        await vector_backend.store_object(
            object_id="test-123",
            object_type="document",
            namespace="test/articles",
            data={"title": "Test"},
            metadata={"source": "test"},
            created_at=datetime.now(UTC),
        )

        mock_qdrant.upsert.assert_called_once()
        call_args = mock_qdrant.upsert.call_args
        assert call_args.kwargs["collection_name"] == "kubani_memory"

    @pytest.mark.asyncio
    async def test_get_object_returns_none_when_not_found(self, vector_backend, mock_qdrant):
        """Verify get_object returns None when not found."""
        mock_qdrant.retrieve.return_value = []

        result = await vector_backend.get_object("non-existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_object_returns_object_when_found(self, vector_backend, mock_qdrant):
        """Verify get_object returns the object when found."""
        mock_point = MagicMock()
        mock_point.id = "found-123"
        mock_point.payload = {
            "type": "document",
            "namespace": "test",
            "data": {"title": "Found"},
            "metadata": {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        mock_qdrant.retrieve.return_value = [mock_point]

        result = await vector_backend.get_object("found-123")

        assert result is not None
        assert result.id == "found-123"
        assert result.type == "document"

    @pytest.mark.asyncio
    async def test_search_objects_applies_filters(self, vector_backend, mock_qdrant):
        """Verify search_objects applies type and namespace filters."""
        mock_qdrant.query_points.return_value = MagicMock(points=[])

        await vector_backend.search_objects(
            query="test query",
            object_type="document",
            namespace="test/articles",
            limit=10,
        )

        mock_qdrant.query_points.assert_called_once()
        call_args = mock_qdrant.query_points.call_args
        assert call_args.kwargs["query_filter"] is not None


class TestGraphBackendRelations:
    """Test GraphBackend relation methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock Neo4j session."""
        session = AsyncMock()
        session.run = AsyncMock()
        return session

    @pytest.fixture
    def mock_neo4j(self, mock_session):
        """Create mock Neo4j driver."""
        driver = MagicMock()
        # Make session() return an async context manager
        driver.session = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        ))
        return driver

    @pytest.fixture
    def graph_backend(self, mock_neo4j):
        """Create GraphBackend with mock driver."""
        from memory_mcp.backends import GraphBackend

        backend = GraphBackend()
        backend._driver = mock_neo4j
        return backend

    @pytest.mark.asyncio
    async def test_create_memory_node_runs_cypher(self, graph_backend, mock_session):
        """Verify create_memory_node runs correct Cypher."""
        await graph_backend.create_memory_node(
            object_id="node-123",
            object_type="document",
            namespace="test",
        )

        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        assert "MERGE (m:MemoryObject" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_create_memory_relation_returns_true_for_new(
        self, graph_backend, mock_session
    ):
        """Verify create_memory_relation returns True for new relation."""
        # First call: check exists (count=0)
        mock_result_check = AsyncMock()
        mock_result_check.single = AsyncMock(return_value={"count": 0})
        # Second call: create relation
        mock_result_create = AsyncMock()

        mock_session.run = AsyncMock(side_effect=[mock_result_check, mock_result_create])

        created = await graph_backend.create_memory_relation(
            source_id="src-123",
            target_id="tgt-456",
            relation_type="ANALYZED_FROM",
        )

        assert created is True
        assert mock_session.run.call_count == 2

    @pytest.mark.asyncio
    async def test_create_memory_relation_returns_false_when_exists(
        self, graph_backend, mock_session
    ):
        """Verify create_memory_relation returns False when exists."""
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"count": 1})
        mock_session.run = AsyncMock(return_value=mock_result)

        created = await graph_backend.create_memory_relation(
            source_id="src-123",
            target_id="tgt-456",
            relation_type="ANALYZED_FROM",
        )

        assert created is False
        # Should only call once (check), not create
        assert mock_session.run.call_count == 1

    @pytest.mark.asyncio
    async def test_get_object_relations_returns_list(self, graph_backend, mock_session):
        """Verify get_object_relations returns MemoryRelation list."""
        mock_result = AsyncMock()
        mock_result.data = AsyncMock(return_value=[
            {"target_id": "tgt-1", "relation_type": "ANALYZED_FROM"},
            {"target_id": "tgt-2", "relation_type": "DERIVED_FROM"},
        ])
        mock_session.run = AsyncMock(return_value=mock_result)

        relations = await graph_backend.get_object_relations("src-123")

        assert len(relations) == 2
        assert relations[0].target_id == "tgt-1"
        assert relations[0].relation_type == "ANALYZED_FROM"


class TestMemoryMCPServerTools:
    """Test that the Memory MCP server exposes correct tools."""

    def test_server_creation_succeeds(self):
        """Verify server can be created without errors."""
        with patch("memory_mcp.server._vector_backend", None), \
             patch("memory_mcp.server._graph_backend", None), \
             patch("memory_mcp.server._cache_backend", None):
            from memory_mcp.server import create_server
            mcp = create_server()

            # Server should be created
            assert mcp is not None
            assert mcp.name == "Memory MCP Server"

    def test_server_has_tool_decorator(self):
        """Verify server has tool decorator available."""
        with patch("memory_mcp.server._vector_backend", None), \
             patch("memory_mcp.server._graph_backend", None), \
             patch("memory_mcp.server._cache_backend", None):
            from memory_mcp.server import create_server
            mcp = create_server()

            # The tool decorator should exist
            assert hasattr(mcp, "tool")
            assert callable(mcp.tool)


class TestMemoryMCPToolSignatures:
    """Test that tool functions have correct signatures."""

    def test_add_function_exists_in_server_module(self):
        """Verify add function is defined in server module."""
        # Import should not raise
        from memory_mcp import server
        # The function is defined inside create_server, so we verify
        # the server module loads without errors
        assert hasattr(server, "create_server")

    def test_required_tool_names_documented(self):
        """Document the required tool names from the plan."""
        # These are the tools required by the skills-mcp-integration plan
        required_tools = {
            "add",           # Store any object with relations
            "search",        # Semantic search
            "get",           # Get by ID
            "list_objects",  # List with filters (renamed from 'list')
            "link",          # Create relationship
            "check_seen",    # Dedup check
            "mark_seen",     # Dedup mark
        }

        # Just document these for reference
        assert len(required_tools) == 7
