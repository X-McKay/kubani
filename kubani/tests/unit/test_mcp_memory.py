"""Tests for MemoryMCPClient."""

import httpx
import pytest

from framework.mcp.client import MemoryMCPClient


class TestMemoryMCPClientLearnings:
    """Test learning storage and retrieval"""

    @pytest.mark.asyncio
    async def test_store_learning(self, respx_mock):
        """store_learning should persist agent learning"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(
                200, json={"content": {"id": "learning-123", "stored": True}}
            )
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.store_learning(
            agent_id="k8s-monitor",
            learning_type="pattern",
            content="OOM kills indicate memory pressure",
            confidence=0.85,
            context={"namespace": "default"},
            tags=["kubernetes", "memory"],
        )

        assert response.success is True
        assert response.data["id"] == "learning-123"
        await client.close()

    @pytest.mark.asyncio
    async def test_query_learnings(self, respx_mock):
        """query_learnings should search by semantic similarity"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "learnings": [
                            {"id": "l1", "content": "Learning 1", "confidence": 0.9},
                            {"id": "l2", "content": "Learning 2", "confidence": 0.75},
                        ]
                    }
                },
            )
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.query_learnings(
            query="memory issues", agent_id="k8s-monitor", min_confidence=0.7, limit=5
        )

        assert response.success is True
        assert len(response.data["learnings"]) == 2
        await client.close()


class TestMemoryMCPClientKnowledge:
    """Test knowledge graph operations"""

    @pytest.mark.asyncio
    async def test_store_knowledge(self, respx_mock):
        """store_knowledge should persist domain knowledge"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"id": "k-123", "stored": True}})
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.store_knowledge(
            topic="Kubernetes OOMKilled",
            content="Pod terminated due to out-of-memory",
            related_topics=["memory limits", "resource quotas"],
            metadata={"severity": "high"},
        )

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_get_knowledge_graph(self, respx_mock):
        """get_knowledge_graph should retrieve topic relationships"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "nodes": [
                            {"id": "n1", "topic": "OOMKilled"},
                            {"id": "n2", "topic": "memory limits"},
                        ],
                        "edges": [{"from": "n1", "to": "n2", "relation": "related"}],
                    }
                },
            )
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.get_knowledge_graph(topic="OOMKilled", depth=2)

        assert response.success is True
        assert len(response.data["nodes"]) == 2
        await client.close()


class TestMemoryMCPClientCache:
    """Test cache operations"""

    @pytest.mark.asyncio
    async def test_cache_set(self, respx_mock):
        """cache_set should store key-value pair"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"stored": True}})
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.cache_set("my-key", {"data": "value"}, ttl_seconds=3600)

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_cache_get(self, respx_mock):
        """cache_get should retrieve cached value"""
        respx_mock.post("http://localhost:8083/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"value": {"data": "value"}}})
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.cache_get("my-key")

        assert response.success is True
        assert response.data["value"]["data"] == "value"
        await client.close()
