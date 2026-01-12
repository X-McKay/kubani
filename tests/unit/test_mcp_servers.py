"""
Tests for the MCP servers.

Tests cover:
- Temporal MCP server tools
- Qdrant MCP server tools
- Memory MCP server tools
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemporalMCPServer:
    """Tests for the Temporal MCP server."""

    def test_server_initialization(self):
        """Test Temporal MCP server initialization."""
        from temporal_mcp.server import create_server
        
        server = create_server()
        
        assert server is not None
        assert server.name == "temporal-mcp"

    @pytest.mark.asyncio
    async def test_list_workflows_tool(self):
        """Test list_workflows tool."""
        from temporal_mcp.server import list_workflows
        from temporal_mcp.models import ListWorkflowsInput
        
        input = ListWorkflowsInput(
            status="running",
            workflow_type=None,
            limit=10,
        )
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_client.return_value.list_workflows = AsyncMock(return_value=[
                MagicMock(
                    id="workflow-1",
                    run_id="run-1",
                    type="TestWorkflow",
                    status="RUNNING",
                    start_time=datetime.now(timezone.utc),
                )
            ])
            
            result = await list_workflows(input)
            
            assert len(result.workflows) == 1
            assert result.workflows[0].id == "workflow-1"

    @pytest.mark.asyncio
    async def test_get_workflow_tool(self):
        """Test get_workflow tool."""
        from temporal_mcp.server import get_workflow
        from temporal_mcp.models import GetWorkflowInput
        
        input = GetWorkflowInput(
            workflow_id="workflow-123",
            run_id=None,
        )
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_handle = MagicMock()
            mock_handle.describe = AsyncMock(return_value=MagicMock(
                id="workflow-123",
                run_id="run-123",
                type="TestWorkflow",
                status="COMPLETED",
            ))
            mock_client.return_value.get_workflow_handle = MagicMock(return_value=mock_handle)
            
            result = await get_workflow(input)
            
            assert result.workflow.id == "workflow-123"

    @pytest.mark.asyncio
    async def test_start_workflow_tool(self):
        """Test start_workflow tool."""
        from temporal_mcp.server import start_workflow
        from temporal_mcp.models import StartWorkflowInput
        
        input = StartWorkflowInput(
            workflow_type="TestWorkflow",
            workflow_id="new-workflow-123",
            task_queue="test-queue",
            args={"param": "value"},
        )
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_handle = MagicMock()
            mock_handle.id = "new-workflow-123"
            mock_handle.run_id = "run-new-123"
            mock_client.return_value.start_workflow = AsyncMock(return_value=mock_handle)
            
            result = await start_workflow(input)
            
            assert result.workflow_id == "new-workflow-123"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_signal_workflow_tool(self):
        """Test signal_workflow tool."""
        from temporal_mcp.server import signal_workflow
        from temporal_mcp.models import SignalWorkflowInput
        
        input = SignalWorkflowInput(
            workflow_id="workflow-123",
            signal_name="pause",
            args=None,
        )
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_handle = MagicMock()
            mock_handle.signal = AsyncMock()
            mock_client.return_value.get_workflow_handle = MagicMock(return_value=mock_handle)
            
            result = await signal_workflow(input)
            
            assert result.success is True
            mock_handle.signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_workflow_tool(self):
        """Test cancel_workflow tool."""
        from temporal_mcp.server import cancel_workflow
        from temporal_mcp.models import CancelWorkflowInput
        
        input = CancelWorkflowInput(
            workflow_id="workflow-123",
        )
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_handle = MagicMock()
            mock_handle.cancel = AsyncMock()
            mock_client.return_value.get_workflow_handle = MagicMock(return_value=mock_handle)
            
            result = await cancel_workflow(input)
            
            assert result.success is True


class TestQdrantMCPServer:
    """Tests for the Qdrant MCP server."""

    def test_server_initialization(self):
        """Test Qdrant MCP server initialization."""
        from qdrant_mcp.server import create_server
        
        server = create_server()
        
        assert server is not None
        assert server.name == "qdrant-mcp"

    @pytest.mark.asyncio
    async def test_list_collections_tool(self):
        """Test list_collections tool."""
        from qdrant_mcp.server import list_collections
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.get_collections = AsyncMock(return_value=MagicMock(
                collections=[
                    MagicMock(name="collection1"),
                    MagicMock(name="collection2"),
                ]
            ))
            
            result = await list_collections()
            
            assert len(result.collections) == 2
            assert "collection1" in result.collections

    @pytest.mark.asyncio
    async def test_create_collection_tool(self):
        """Test create_collection tool."""
        from qdrant_mcp.server import create_collection
        from qdrant_mcp.models import CreateCollectionInput
        
        input = CreateCollectionInput(
            name="new-collection",
            vector_size=1536,
            distance="cosine",
        )
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.create_collection = AsyncMock(return_value=True)
            
            result = await create_collection(input)
            
            assert result.success is True
            assert result.collection_name == "new-collection"

    @pytest.mark.asyncio
    async def test_search_vectors_tool(self):
        """Test search_vectors tool."""
        from qdrant_mcp.server import search_vectors
        from qdrant_mcp.models import SearchVectorsInput
        
        input = SearchVectorsInput(
            collection="test-collection",
            query_vector=[0.1] * 1536,
            limit=5,
            score_threshold=0.7,
        )
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.search = AsyncMock(return_value=[
                MagicMock(id=1, score=0.95, payload={"text": "Result 1"}),
                MagicMock(id=2, score=0.85, payload={"text": "Result 2"}),
            ])
            
            result = await search_vectors(input)
            
            assert len(result.results) == 2
            assert result.results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_upsert_vectors_tool(self):
        """Test upsert_vectors tool."""
        from qdrant_mcp.server import upsert_vectors
        from qdrant_mcp.models import UpsertVectorsInput, VectorPoint
        
        input = UpsertVectorsInput(
            collection="test-collection",
            points=[
                VectorPoint(
                    id="point-1",
                    vector=[0.1] * 1536,
                    payload={"text": "Test point"},
                ),
            ],
        )
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.upsert = AsyncMock(return_value=MagicMock(
                status="completed"
            ))
            
            result = await upsert_vectors(input)
            
            assert result.success is True
            assert result.points_upserted == 1

    @pytest.mark.asyncio
    async def test_delete_points_tool(self):
        """Test delete_points tool."""
        from qdrant_mcp.server import delete_points
        from qdrant_mcp.models import DeletePointsInput
        
        input = DeletePointsInput(
            collection="test-collection",
            point_ids=["point-1", "point-2"],
        )
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.delete = AsyncMock(return_value=True)
            
            result = await delete_points(input)
            
            assert result.success is True


class TestMemoryMCPServer:
    """Tests for the Memory MCP server."""

    def test_server_initialization(self):
        """Test Memory MCP server initialization."""
        from memory_mcp.server import create_server
        
        server = create_server()
        
        assert server is not None
        assert server.name == "memory-mcp"

    @pytest.mark.asyncio
    async def test_store_learning_tool(self):
        """Test store_learning tool."""
        from memory_mcp.server import store_learning
        from memory_mcp.models import StoreLearningInput
        
        input = StoreLearningInput(
            agent_id="test-agent",
            learning_type="pattern",
            content="Test learning content",
            confidence=0.85,
            tags=["test", "learning"],
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.store_learning = AsyncMock(return_value="learning-123")
            
            result = await store_learning(input)
            
            assert result.success is True
            assert result.learning_id == "learning-123"

    @pytest.mark.asyncio
    async def test_query_learnings_tool(self):
        """Test query_learnings tool."""
        from memory_mcp.server import query_learnings
        from memory_mcp.models import QueryLearningsInput
        
        input = QueryLearningsInput(
            query="memory issues",
            agent_id=None,
            min_confidence=0.7,
            limit=10,
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.query_learnings = AsyncMock(return_value=[
                {
                    "id": "learning-1",
                    "content": "OOM kills indicate memory pressure",
                    "confidence": 0.9,
                    "score": 0.95,
                },
            ])
            
            result = await query_learnings(input)
            
            assert len(result.learnings) == 1
            assert result.learnings[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_store_knowledge_tool(self):
        """Test store_knowledge tool."""
        from memory_mcp.server import store_knowledge
        from memory_mcp.models import StoreKnowledgeInput
        
        input = StoreKnowledgeInput(
            topic="kubernetes/memory-management",
            content="Memory management best practices",
            source="documentation",
            relationships=[
                {"type": "related_to", "target": "kubernetes/resources"},
            ],
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.store_knowledge = AsyncMock(return_value="knowledge-123")
            
            result = await store_knowledge(input)
            
            assert result.success is True
            assert result.knowledge_id == "knowledge-123"

    @pytest.mark.asyncio
    async def test_get_knowledge_graph_tool(self):
        """Test get_knowledge_graph tool."""
        from memory_mcp.server import get_knowledge_graph
        from memory_mcp.models import GetKnowledgeGraphInput
        
        input = GetKnowledgeGraphInput(
            topic="kubernetes",
            depth=2,
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.get_knowledge_graph = AsyncMock(return_value={
                "nodes": [
                    {"id": "kubernetes", "type": "topic"},
                    {"id": "pods", "type": "concept"},
                ],
                "edges": [
                    {"source": "kubernetes", "target": "pods", "type": "contains"},
                ],
            })
            
            result = await get_knowledge_graph(input)
            
            assert len(result.nodes) == 2
            assert len(result.edges) == 1

    @pytest.mark.asyncio
    async def test_cache_operations(self):
        """Test cache get/set operations."""
        from memory_mcp.server import cache_get, cache_set
        from memory_mcp.models import CacheGetInput, CacheSetInput
        
        # Test cache set
        set_input = CacheSetInput(
            key="test-key",
            value={"data": "test"},
            ttl=3600,
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.cache_set = AsyncMock(return_value=True)
            
            set_result = await cache_set(set_input)
            
            assert set_result.success is True
        
        # Test cache get
        get_input = CacheGetInput(key="test-key")
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.cache_get = AsyncMock(return_value={"data": "test"})
            
            get_result = await cache_get(get_input)
            
            assert get_result.value == {"data": "test"}
            assert get_result.found is True

    @pytest.mark.asyncio
    async def test_consolidate_learnings_tool(self):
        """Test consolidate_learnings tool."""
        from memory_mcp.server import consolidate_learnings
        from memory_mcp.models import ConsolidateLearningsInput
        
        input = ConsolidateLearningsInput(
            agent_id="test-agent",
            similarity_threshold=0.85,
        )
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.consolidate_learnings = AsyncMock(return_value={
                "consolidated_count": 5,
                "removed_duplicates": 3,
            })
            
            result = await consolidate_learnings(input)
            
            assert result.consolidated_count == 5
            assert result.removed_duplicates == 3


class TestMCPServerHealth:
    """Tests for MCP server health endpoints."""

    @pytest.mark.asyncio
    async def test_temporal_health(self):
        """Test Temporal MCP server health endpoint."""
        from temporal_mcp.server import health_check
        
        with patch("temporal_mcp.server.get_temporal_client") as mock_client:
            mock_client.return_value.service_client.check_health = AsyncMock()
            
            result = await health_check()
            
            assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_qdrant_health(self):
        """Test Qdrant MCP server health endpoint."""
        from qdrant_mcp.server import health_check
        
        with patch("qdrant_mcp.server.get_qdrant_client") as mock_client:
            mock_client.return_value.get_collections = AsyncMock()
            
            result = await health_check()
            
            assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_memory_health(self):
        """Test Memory MCP server health endpoint."""
        from memory_mcp.server import health_check
        
        with patch("memory_mcp.server.get_memory_backend") as mock_backend:
            mock_backend.return_value.health_check = AsyncMock(return_value={
                "qdrant": True,
                "neo4j": True,
                "redis": True,
            })
            
            result = await health_check()
            
            assert result["status"] == "healthy"
            assert result["backends"]["qdrant"] is True
