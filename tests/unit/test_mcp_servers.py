"""
Tests for the MCP servers.

Tests cover:
- Temporal MCP server models
- Qdrant MCP server models
- Memory MCP server models
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemporalMCPServer:
    """Tests for the Temporal MCP server."""

    def test_workflow_result_model(self):
        """Test WorkflowResult model."""
        from temporal_mcp.models import WorkflowResult
        
        result = WorkflowResult(
            workflow_id="wf-123",
            run_id="run-456",
            workflow_type="TestWorkflow",
            status="RUNNING",
        )
        
        assert result.workflow_id == "wf-123"
        assert result.status == "RUNNING"

    def test_workflows_result_model(self):
        """Test WorkflowsResult model."""
        from temporal_mcp.models import WorkflowsResult, WorkflowResult
        
        result = WorkflowsResult(
            workflows=[
                WorkflowResult(
                    workflow_id="wf-1",
                    status="RUNNING",
                ),
            ],
            count=1,
        )
        
        assert result.count == 1
        assert len(result.workflows) == 1

    def test_workflow_history_result_model(self):
        """Test WorkflowHistoryResult model."""
        from temporal_mcp.models import WorkflowHistoryResult
        
        result = WorkflowHistoryResult(
            workflow_id="wf-123",
            run_id="run-456",
            events=[{"event_type": "WorkflowExecutionStarted"}],
            count=1,
        )
        
        assert result.workflow_id == "wf-123"
        assert result.count == 1

    def test_activity_result_model(self):
        """Test ActivityResult model."""
        from temporal_mcp.models import ActivityResult
        
        result = ActivityResult(
            activity_id="act-123",
            activity_type="TestActivity",
            status="COMPLETED",
        )
        
        assert result.activity_id == "act-123"
        assert result.status == "COMPLETED"

    def test_schedule_info_model(self):
        """Test ScheduleInfo model."""
        from temporal_mcp.models import ScheduleInfo
        
        info = ScheduleInfo(
            schedule_id="sched-123",
            workflow_type="ScheduledWorkflow",
            paused=False,
        )
        
        assert info.schedule_id == "sched-123"
        assert info.paused is False

    def test_schedules_result_model(self):
        """Test SchedulesResult model."""
        from temporal_mcp.models import SchedulesResult, ScheduleInfo
        
        result = SchedulesResult(
            schedules=[
                ScheduleInfo(
                    schedule_id="sched-1",
                    workflow_type="TestWorkflow",
                ),
            ],
            count=1,
        )
        
        assert result.count == 1


class TestQdrantMCPServer:
    """Tests for the Qdrant MCP server."""

    def test_collection_info_model(self):
        """Test CollectionInfo model."""
        from qdrant_mcp.models import CollectionInfo
        
        info = CollectionInfo(
            name="test_collection",
            vectors_count=100,
            points_count=100,
            status="green",
        )
        
        assert info.name == "test_collection"
        assert info.vectors_count == 100

    def test_collections_result_model(self):
        """Test CollectionsResult model."""
        from qdrant_mcp.models import CollectionsResult, CollectionInfo
        
        result = CollectionsResult(
            collections=[
                CollectionInfo(
                    name="test",
                    vectors_count=10,
                    points_count=10,
                    status="green",
                ),
            ],
            count=1,
        )
        
        assert result.count == 1

    def test_search_result_model(self):
        """Test SearchResult model."""
        from qdrant_mcp.models import SearchResult
        
        result = SearchResult(
            id="point-123",
            score=0.95,
            payload={"key": "value"},
        )
        
        assert result.id == "point-123"
        assert result.score == 0.95

    def test_search_results_model(self):
        """Test SearchResults model."""
        from qdrant_mcp.models import SearchResults, SearchResult
        
        result = SearchResults(
            results=[
                SearchResult(
                    id="point-1",
                    score=0.9,
                    payload={},
                ),
            ],
            count=1,
        )
        
        assert result.count == 1

    def test_point_result_model(self):
        """Test PointResult model."""
        from qdrant_mcp.models import PointResult
        
        result = PointResult(
            id="point-123",
            vector=[0.1, 0.2, 0.3],
            payload={"key": "value"},
        )
        
        assert result.id == "point-123"
        assert len(result.vector) == 3

    def test_upsert_result_model(self):
        """Test UpsertResult model."""
        from qdrant_mcp.models import UpsertResult
        
        result = UpsertResult(
            collection="test",
            upserted_count=5,
            ids=["id1", "id2", "id3", "id4", "id5"],
        )
        
        assert result.upserted_count == 5
        assert len(result.ids) == 5


class TestMemoryMCPServer:
    """Tests for the Memory MCP server."""

    def test_learning_entry_model(self):
        """Test LearningEntry model."""
        from memory_mcp.models import LearningEntry
        
        entry = LearningEntry(
            learning_id="learn-123",
            agent_id="k8s-monitor",
            learning_type="pattern",
            content="Learned pattern...",
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
        )
        
        assert entry.learning_id == "learn-123"
        assert entry.confidence == 0.9

    def test_learning_result_model(self):
        """Test LearningResult model."""
        from memory_mcp.models import LearningResult
        
        result = LearningResult(
            learning_id="learn-123",
            agent_id="k8s-monitor",
            learning_type="pattern",
            content="Learned pattern...",
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
        )
        
        assert result.learning_id == "learn-123"

    def test_learnings_result_model(self):
        """Test LearningsResult model."""
        from memory_mcp.models import LearningsResult, LearningEntry
        
        result = LearningsResult(
            learnings=[
                LearningEntry(
                    learning_id="learn-1",
                    agent_id="test",
                    learning_type="pattern",
                    content="Test",
                    confidence=0.8,
                    timestamp=datetime.now(timezone.utc),
                ),
            ],
            count=1,
            query="test query",
        )
        
        assert result.count == 1

    def test_knowledge_entry_model(self):
        """Test KnowledgeEntry model."""
        from memory_mcp.models import KnowledgeEntry
        
        entry = KnowledgeEntry(
            knowledge_id="know-123",
            topic="kubernetes",
            content="Kubernetes best practices...",
            source="documentation",
            timestamp=datetime.now(timezone.utc),
        )
        
        assert entry.knowledge_id == "know-123"
        assert entry.topic == "kubernetes"

    def test_knowledge_result_model(self):
        """Test KnowledgeResult model."""
        from memory_mcp.models import KnowledgeResult
        
        result = KnowledgeResult(
            knowledge_id="know-123",
            topic="kubernetes",
            content="Kubernetes best practices...",
            source="documentation",
            timestamp=datetime.now(timezone.utc),
        )
        
        assert result.knowledge_id == "know-123"

    def test_relationship_result_model(self):
        """Test RelationshipResult model."""
        from memory_mcp.models import RelationshipResult
        
        result = RelationshipResult(
            relationship_id="rel-123",
            from_entity="node-1",
            to_entity="node-2",
            relationship_type="RELATED_TO",
        )
        
        assert result.from_entity == "node-1"
        assert result.relationship_type == "RELATED_TO"

    def test_memory_stats_model(self):
        """Test MemoryStats model."""
        from memory_mcp.models import MemoryStats
        
        stats = MemoryStats(
            total_learnings=100,
            total_knowledge=50,
            total_relationships=25,
            cache_keys=10,
            agents_with_learnings=5,
        )
        
        assert stats.total_learnings == 100


class TestMemoryBackends:
    """Tests for the Memory MCP server backends."""

    def test_vector_backend_initialization(self):
        """Test VectorBackend initialization."""
        from memory_mcp.backends import VectorBackend
        
        backend = VectorBackend(
            host="localhost",
            port=6333,
        )
        
        assert backend.host == "localhost"
        assert backend.port == 6333

    def test_graph_backend_initialization(self):
        """Test GraphBackend initialization."""
        from memory_mcp.backends import GraphBackend
        
        backend = GraphBackend(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
        )
        
        assert backend.uri == "bolt://localhost:7687"

    def test_cache_backend_initialization(self):
        """Test CacheBackend initialization."""
        from memory_mcp.backends import CacheBackend
        
        backend = CacheBackend(host="localhost", port=6379)
        
        assert backend.host == "localhost"
        assert backend.port == 6379
