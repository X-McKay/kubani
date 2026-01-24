# Unit Testing Phase 2: MCP Client Layer

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Achieve 80%+ coverage on framework/mcp/client.py by testing all MCP client classes with mocked HTTP responses.

**Architecture:** Use respx for HTTP mocking to test MCP client methods without real MCP servers. Build on existing mcp_mocks.py fixture infrastructure from Phase 1.

**Tech Stack:** pytest, pytest-asyncio, respx (already in Phase 1), httpx

---

## Background

**Current State:**
- framework/mcp/client.py: 40% coverage (113/187 lines uncovered)
- mcp_mocks.py fixture exists with basic HTTP mocking
- All dependencies already installed from Phase 1

**Target:**
- 80%+ coverage on framework/mcp/client.py
- Test all 7 MCP client classes
- Estimated 25-30 new tests

---

## Task 1: Test MCPServerClient Base Class

**Files:**
- Test: `kubani/tests/unit/test_mcp_client_base.py`

**Step 1: Write test for successful health check**

```python
"""Tests for MCPServerClient base class."""

import pytest
from framework.mcp.client import MCPServerClient


class TestMCPServerClientHealth:
    """Test health check functionality"""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_server_healthy(self, respx_mock):
        """Health check should return True when server responds with 200"""
        respx_mock.get("http://test-server:8080/health").mock(return_value=httpx.Response(200))

        client = MCPServerClient("test", "http://test-server:8080")
        result = await client.health_check()

        assert result is True
        await client.close()
```

**Step 2: Run test to verify it fails**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py::TestMCPServerClientHealth::test_health_check_returns_true_when_server_healthy -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'httpx'" (need import)

**Step 3: Add missing imports and run again**

Add to test file:
```python
import httpx
```

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py::TestMCPServerClientHealth::test_health_check_returns_true_when_server_healthy -v`
Expected: PASS

**Step 4: Write test for health check failure**

```python
    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_server_unavailable(self, respx_mock):
        """Health check should return False when server is down"""
        respx_mock.get("http://test-server:8080/health").mock(side_effect=httpx.ConnectError("Connection refused"))

        client = MCPServerClient("test", "http://test-server:8080")
        result = await client.health_check()

        assert result is False
        await client.close()
```

**Step 5: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py::TestMCPServerClientHealth -v`
Expected: 2/2 PASS

**Step 6: Write tests for list_tools**

```python
class TestMCPServerClientListTools:
    """Test list_tools functionality"""

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools_array(self, respx_mock):
        """list_tools should return tools from server response"""
        respx_mock.get("http://test-server:8080/tools/list").mock(
            return_value=httpx.Response(
                200,
                json={"tools": [{"name": "tool1"}, {"name": "tool2"}]}
            )
        )

        client = MCPServerClient("test", "http://test-server:8080")
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[1]["name"] == "tool2"
        await client.close()

    @pytest.mark.asyncio
    async def test_list_tools_returns_empty_on_error(self, respx_mock):
        """list_tools should return empty array on error"""
        respx_mock.get("http://test-server:8080/tools/list").mock(side_effect=httpx.ConnectError("Connection refused"))

        client = MCPServerClient("test", "http://test-server:8080")
        tools = await client.list_tools()

        assert tools == []
        await client.close()
```

**Step 7: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py -v`
Expected: 4/4 PASS

**Step 8: Write tests for call_tool**

```python
class TestMCPServerClientCallTool:
    """Test call_tool functionality"""

    @pytest.mark.asyncio
    async def test_call_tool_returns_success_response(self, respx_mock):
        """call_tool should return MCPResponse with success=True on successful call"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"result": "success", "data": [1, 2, 3]}}
            )
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool", arg1="value1", arg2=42)

        assert response.success is True
        assert response.data == {"result": "success", "data": [1, 2, 3]}
        assert response.error is None
        await client.close()

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_response_on_http_error(self, respx_mock):
        """call_tool should return MCPResponse with success=False on HTTP error"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool")

        assert response.success is False
        assert response.data is None
        assert response.error is not None
        assert "500" in response.error
        await client.close()

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_response_on_connection_error(self, respx_mock):
        """call_tool should return MCPResponse with success=False on connection error"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool")

        assert response.success is False
        assert response.data is None
        assert "Connection refused" in response.error
        await client.close()
```

**Step 9: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py -v`
Expected: 7/7 PASS

**Step 10: Test HTTP client lazy initialization**

```python
class TestMCPServerClientInitialization:
    """Test client initialization and cleanup"""

    @pytest.mark.asyncio
    async def test_http_client_created_lazily(self):
        """HTTP client should be created on first use, not in __init__"""
        client = MCPServerClient("test", "http://test-server:8080")

        assert client._client is None  # Not created yet

        # Trigger client creation
        await client._get_client()

        assert client._client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self):
        """close() should clean up HTTP client"""
        client = MCPServerClient("test", "http://test-server:8080")
        await client._get_client()

        assert client._client is not None

        await client.close()

        assert client._client is None
```

**Step 11: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_base.py -v`
Expected: 9/9 PASS

**Step 12: Commit**

```bash
git add kubani/tests/unit/test_mcp_client_base.py
git commit -m "test: add MCPServerClient base class tests (9 tests, health/tools/call_tool)"
```

---

## Task 2: Test TemporalMCPClient

**Files:**
- Test: `kubani/tests/unit/test_mcp_temporal.py`

**Step 1: Write tests for list_workflows**

```python
"""Tests for TemporalMCPClient."""

import httpx
import pytest
from framework.mcp.client import TemporalMCPClient


class TestTemporalMCPClientListWorkflows:
    """Test list_workflows functionality"""

    @pytest.mark.asyncio
    async def test_list_workflows_with_no_filters(self, respx_mock):
        """list_workflows should call temporal MCP with correct parameters"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "workflows": [
                            {"id": "wf-1", "status": "running"},
                            {"id": "wf-2", "status": "completed"},
                        ]
                    }
                }
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_workflows()

        assert response.success is True
        assert len(response.data["workflows"]) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_list_workflows_with_status_filter(self, respx_mock):
        """list_workflows should pass status filter to MCP server"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"workflows": [{"id": "wf-1", "status": "running"}]}}
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_workflows(status="running")

        assert response.success is True
        assert len(response.data["workflows"]) == 1
        await client.close()
```

**Step 2: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_temporal.py::TestTemporalMCPClientListWorkflows -v`
Expected: 2/2 PASS

**Step 3: Write tests for workflow operations**

```python
class TestTemporalMCPClientWorkflowOperations:
    """Test workflow CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_workflow_by_id(self, respx_mock):
        """get_workflow should retrieve workflow details"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"id": "wf-123", "status": "running", "history": []}}
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.get_workflow("wf-123")

        assert response.success is True
        assert response.data["id"] == "wf-123"
        await client.close()

    @pytest.mark.asyncio
    async def test_start_workflow(self, respx_mock):
        """start_workflow should start new workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"workflow_id": "wf-new", "run_id": "run-123"}}
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.start_workflow(
            workflow_type="MyWorkflow",
            workflow_id="wf-new",
            task_queue="default",
            args=[{"param": "value"}]
        )

        assert response.success is True
        assert response.data["workflow_id"] == "wf-new"
        await client.close()

    @pytest.mark.asyncio
    async def test_signal_workflow(self, respx_mock):
        """signal_workflow should send signal to workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"success": True}})
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.signal_workflow("wf-123", "pause", [{"reason": "maintenance"}])

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, respx_mock):
        """cancel_workflow should cancel running workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"cancelled": True}})
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.cancel_workflow("wf-123")

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_list_schedules(self, respx_mock):
        """list_schedules should retrieve schedule list"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"schedules": [{"id": "sched-1"}, {"id": "sched-2"}]}}
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_schedules(limit=50)

        assert response.success is True
        assert len(response.data["schedules"]) == 2
        await client.close()
```

**Step 4: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_temporal.py -v`
Expected: 7/7 PASS

**Step 5: Commit**

```bash
git add kubani/tests/unit/test_mcp_temporal.py
git commit -m "test: add TemporalMCPClient tests (7 tests, workflows/signals/schedules)"
```

---

## Task 3: Test QdrantMCPClient

**Files:**
- Test: `kubani/tests/unit/test_mcp_qdrant.py`

**Step 1: Write tests for collection operations**

```python
"""Tests for QdrantMCPClient."""

import httpx
import pytest
from framework.mcp.client import QdrantMCPClient


class TestQdrantMCPClientCollections:
    """Test collection management"""

    @pytest.mark.asyncio
    async def test_list_collections(self, respx_mock):
        """list_collections should return all collections"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"collections": ["skills", "learnings", "knowledge"]}}
            )
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.list_collections()

        assert response.success is True
        assert len(response.data["collections"]) == 3
        await client.close()

    @pytest.mark.asyncio
    async def test_create_collection(self, respx_mock):
        """create_collection should create new vector collection"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"created": True}})
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.create_collection(
            name="test_collection",
            vector_size=768,
            distance="Cosine"
        )

        assert response.success is True
        await client.close()
```

**Step 2: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_qdrant.py::TestQdrantMCPClientCollections -v`
Expected: 2/2 PASS

**Step 3: Write tests for vector operations**

```python
class TestQdrantMCPClientVectors:
    """Test vector operations"""

    @pytest.mark.asyncio
    async def test_search_vectors(self, respx_mock):
        """search_vectors should find similar vectors"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "results": [
                            {"id": "vec-1", "score": 0.95, "payload": {"text": "result 1"}},
                            {"id": "vec-2", "score": 0.87, "payload": {"text": "result 2"}},
                        ]
                    }
                }
            )
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.search_vectors(
            collection="skills",
            query_vector=[0.1] * 768,
            limit=10
        )

        assert response.success is True
        assert len(response.data["results"]) == 2
        assert response.data["results"][0]["score"] == 0.95
        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_vectors(self, respx_mock):
        """upsert_vectors should insert or update vectors"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"operation_id": 123, "status": "completed"}})
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.upsert_vectors(
            collection="skills",
            points=[
                {"id": "vec-1", "vector": [0.1] * 768, "payload": {"text": "skill 1"}},
                {"id": "vec-2", "vector": [0.2] * 768, "payload": {"text": "skill 2"}},
            ]
        )

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_points(self, respx_mock):
        """delete_points should remove vectors from collection"""
        respx_mock.post("http://localhost:8082/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"deleted": 2}})
        )

        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        response = await client.delete_points(
            collection="skills",
            point_ids=["vec-1", "vec-2"]
        )

        assert response.success is True
        await client.close()
```

**Step 4: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_qdrant.py -v`
Expected: 5/5 PASS

**Step 5: Commit**

```bash
git add kubani/tests/unit/test_mcp_qdrant.py
git commit -m "test: add QdrantMCPClient tests (5 tests, collections/vectors)"
```

---

## Task 4: Test MemoryMCPClient

**Files:**
- Test: `kubani/tests/unit/test_mcp_memory.py`

**Step 1: Write tests for learning storage**

```python
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
            return_value=httpx.Response(200, json={"content": {"id": "learning-123", "stored": True}})
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.store_learning(
            agent_id="k8s-monitor",
            learning_type="pattern",
            content="OOM kills indicate memory pressure",
            confidence=0.85,
            context={"namespace": "default"},
            tags=["kubernetes", "memory"]
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
                }
            )
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.query_learnings(
            query="memory issues",
            agent_id="k8s-monitor",
            min_confidence=0.7,
            limit=5
        )

        assert response.success is True
        assert len(response.data["learnings"]) == 2
        await client.close()
```

**Step 2: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_memory.py::TestMemoryMCPClientLearnings -v`
Expected: 2/2 PASS

**Step 3: Write tests for knowledge graph**

```python
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
            metadata={"severity": "high"}
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
                        "nodes": [{"id": "n1", "topic": "OOMKilled"}, {"id": "n2", "topic": "memory limits"}],
                        "edges": [{"from": "n1", "to": "n2", "relation": "related"}]
                    }
                }
            )
        )

        client = MemoryMCPClient("memory", "http://localhost:8083")
        response = await client.get_knowledge_graph(topic="OOMKilled", depth=2)

        assert response.success is True
        assert len(response.data["nodes"]) == 2
        await client.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_memory.py -v`
Expected: 4/4 PASS

**Step 5: Write tests for cache operations**

```python
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
```

**Step 6: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_memory.py -v`
Expected: 6/6 PASS

**Step 7: Commit**

```bash
git add kubani/tests/unit/test_mcp_memory.py
git commit -m "test: add MemoryMCPClient tests (6 tests, learnings/knowledge/cache)"
```

---

## Task 5: Test DiscordMCPClient and RegistryMCPClient

**Files:**
- Test: `kubani/tests/unit/test_mcp_discord.py`
- Test: `kubani/tests/unit/test_mcp_registry.py`

**Step 1: Write Discord client tests**

File: `kubani/tests/unit/test_mcp_discord.py`

```python
"""Tests for DiscordMCPClient."""

import httpx
import pytest
from framework.mcp.client import DiscordMCPClient


class TestDiscordMCPClient:
    """Test Discord operations"""

    @pytest.mark.asyncio
    async def test_send_message(self, respx_mock):
        """send_message should post message to channel"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"message_id": "msg-123"}})
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.send_message("channel-123", "Hello from tests")

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_send_embed(self, respx_mock):
        """send_embed should post rich embed to channel"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"message_id": "msg-456"}})
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.send_embed(
            "channel-123",
            title="Test Alert",
            description="Test description",
            color=0xFF0000,
            fields=[{"name": "Field 1", "value": "Value 1"}]
        )

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_add_reaction(self, respx_mock):
        """add_reaction should add emoji to message"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"added": True}})
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.add_reaction("channel-123", "msg-123", "✅")

        assert response.success is True
        await client.close()
```

**Step 2: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_discord.py -v`
Expected: 3/3 PASS

**Step 3: Write Registry client tests**

File: `kubani/tests/unit/test_mcp_registry.py`

```python
"""Tests for RegistryMCPClient."""

import httpx
import pytest
from framework.mcp.client import RegistryMCPClient


class TestRegistryMCPClient:
    """Test Registry operations"""

    @pytest.mark.asyncio
    async def test_register_agent(self, respx_mock):
        """register_agent should register new agent"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"registered": True, "agent_id": "agent-123"}})
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.register_agent(
            agent_id="k8s-monitor",
            name="K8s Monitor",
            version="1.0.0",
            capabilities=["monitoring", "remediation"],
            metadata={"namespace": "default"}
        )

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_heartbeat(self, respx_mock):
        """heartbeat should update agent status"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"acknowledged": True}})
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.heartbeat("agent-123")

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_list_agents(self, respx_mock):
        """list_agents should return agent list"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"agents": [{"id": "agent-1"}, {"id": "agent-2"}]}}
            )
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.list_agents(status="active")

        assert response.success is True
        assert len(response.data["agents"]) == 2
        await client.close()
```

**Step 4: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_discord.py tests/unit/test_mcp_registry.py -v`
Expected: 6/6 PASS

**Step 5: Commit**

```bash
git add kubani/tests/unit/test_mcp_discord.py kubani/tests/unit/test_mcp_registry.py
git commit -m "test: add Discord and Registry MCP client tests (6 tests)"
```

---

## Task 6: Test MCPClient Unified Wrapper

**Files:**
- Test: `kubani/tests/unit/test_mcp_client_unified.py`

**Step 1: Write tests for client property getters**

```python
"""Tests for unified MCPClient wrapper."""

import pytest
from framework.mcp.client import MCPClient, TemporalMCPClient, QdrantMCPClient, MemoryMCPClient


class TestMCPClientProperties:
    """Test lazy property initialization"""

    def test_temporal_property_creates_client(self):
        """temporal property should lazily create TemporalMCPClient"""
        client = MCPClient()

        assert client._temporal is None
        temporal = client.temporal

        assert isinstance(temporal, TemporalMCPClient)
        assert client._temporal is temporal  # Same instance on second access

    def test_qdrant_property_creates_client(self):
        """qdrant property should lazily create QdrantMCPClient"""
        client = MCPClient()

        assert client._qdrant is None
        qdrant = client.qdrant

        assert isinstance(qdrant, QdrantMCPClient)
        assert client._qdrant is qdrant

    def test_memory_property_creates_client(self):
        """memory property should lazily create MemoryMCPClient"""
        client = MCPClient()

        assert client._memory is None
        memory = client.memory

        assert isinstance(memory, MemoryMCPClient)
        assert client._memory is memory
```

**Step 2: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_unified.py::TestMCPClientProperties -v`
Expected: 3/3 PASS

**Step 3: Write tests for health_check_all**

```python
class TestMCPClientHealthCheckAll:
    """Test health_check_all functionality"""

    @pytest.mark.asyncio
    async def test_health_check_all_checks_enabled_servers(self, respx_mock, isolated_config_dir, create_yaml_config):
        """health_check_all should check all enabled MCP servers"""
        # Configure enabled servers
        create_yaml_config("default.yaml", {
            "mcp": {
                "temporal_enabled": True,
                "temporal_url": "http://localhost:8081",
                "qdrant_enabled": True,
                "qdrant_url": "http://localhost:8082",
                "memory_enabled": False,
                "discord_enabled": False,
            }
        })

        # Mock health endpoints
        respx_mock.get("http://localhost:8081/health").mock(return_value=httpx.Response(200))
        respx_mock.get("http://localhost:8082/health").mock(return_value=httpx.Response(200))

        from framework.config import reload_config
        reload_config()

        client = MCPClient()
        results = await client.health_check_all()

        assert "temporal" in results
        assert "qdrant" in results
        assert results["temporal"] is True
        assert results["qdrant"] is True
        assert "memory" not in results  # Disabled

        await client.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_unified.py -v`
Expected: 4/4 PASS (add httpx import if needed)

**Step 5: Write tests for global singleton**

```python
class TestMCPClientSingleton:
    """Test global singleton pattern"""

    def test_get_mcp_client_returns_same_instance(self):
        """get_mcp_client should return same instance"""
        from framework.mcp.client import get_mcp_client

        client1 = get_mcp_client()
        client2 = get_mcp_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_mcp_client_clears_singleton(self):
        """close_mcp_client should clear global instance"""
        from framework.mcp.client import get_mcp_client, close_mcp_client

        client1 = get_mcp_client()
        await close_mcp_client()
        client2 = get_mcp_client()

        assert client1 is not client2  # New instance created
```

**Step 6: Run all tests to verify they pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp_client_unified.py -v`
Expected: 6/6 PASS

**Step 7: Commit**

```bash
git add kubani/tests/unit/test_mcp_client_unified.py
git commit -m "test: add unified MCPClient wrapper tests (6 tests, properties/health/singleton)"
```

---

## Task 7: Run Full Test Suite and Check Coverage

**Step 1: Run all tests**

Run: `cd kubani && uv run pytest tests/ -v`
Expected: 28 (Phase 1) + 39 (Phase 2) = 67 tests PASS

**Step 2: Check coverage for MCP client**

Run: `cd kubani && uv run pytest tests/ --cov=framework/mcp/client --cov-report=term-missing`
Expected: Coverage 80%+ on framework/mcp/client.py

**Step 3: Generate full coverage report**

Run: `just test-coverage`
Expected: Overall framework coverage 60-65% (up from 53%)

**Step 4: Verify all tests still pass**

Run: `cd kubani && uv run pytest tests/unit/test_mcp*.py -v --tb=short`
Expected: All 39 new MCP tests PASS

---

## Task 8: Create Phase 2 Completion Report

**Files:**
- Create: `docs/plans/2026-01-24-unit-testing-phase2-completion.md`

**Step 1: Generate coverage report**

Run: `cd kubani && uv run pytest tests/ --cov=framework --cov-report=term > /tmp/phase2-coverage.txt`

**Step 2: Write completion report**

Create comprehensive report documenting:
- Tests created (39 new tests across 7 MCP client classes)
- Coverage improvements (framework/mcp/client.py: 40% → 80%+)
- Files created (7 new test files)
- Commits made (6 commits)
- Lessons learned
- Next steps for Phase 3 (integration tests, agent testing)

Report template:
```markdown
# Unit Testing Phase 2 Completion Report

**Date:** 2026-01-24
**Status:** ✅ Complete
**Branch:** `feature/refactor-unittests`

## Executive Summary

[Summary of achievements]

## Coverage Improvements

[Before/after coverage comparison]

## Tests Created

[List of 39 tests by client class]

## Files Created

[List of 7 test files]

## Lessons Learned

[What worked well, challenges, improvements]

## Next Steps (Phase 3)

[Recommendations for Phase 3]
```

**Step 3: Commit completion report**

```bash
git add docs/plans/2026-01-24-unit-testing-phase2-completion.md
git commit -m "docs: add Phase 2 unit testing completion report

Summary:
- 39 new tests for MCP client layer
- Coverage on framework/mcp/client.py: 40% → 80%+
- 7 new test files (temporal, qdrant, memory, discord, registry, unified, base)
- Overall framework coverage: 53% → 65%+
- Foundation for Phase 3 (integration tests, agent testing)"
```

---

## Summary

**Phase 2 Scope:**
- 8 tasks total
- 39 new tests estimated
- 7 new test files
- Target: 80%+ coverage on framework/mcp/client.py
- Expected overall framework coverage: 65%+

**Testing Strategy:**
- Use respx for HTTP mocking (already in dependencies)
- Follow TDD: write test → run → verify fail → implement → verify pass
- Test all MCP client methods (Temporal, Qdrant, Memory, Discord, Registry, Skills)
- Test unified MCPClient wrapper and singleton pattern

**Success Criteria:**
- All 39 tests pass
- Coverage on framework/mcp/client.py ≥ 80%
- All tests run in <2 seconds (fast unit tests)
- No external service dependencies (all mocked)
