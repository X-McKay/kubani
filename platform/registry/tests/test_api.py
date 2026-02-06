"""Integration tests for the Registry Service API."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestHealthEndpoints:
    """Test health check endpoints."""

    async def test_health_endpoint(self, async_client: AsyncClient):
        """Health endpoint should return 200."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "kubani-registry"

    async def test_ready_endpoint(self, async_client: AsyncClient):
        """Ready endpoint should return status."""
        response = await async_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestAgentAPI:
    """Test agent registry endpoints."""

    async def test_list_agents_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/agents")
        assert response.status_code == 200
        assert response.json() == []

    async def test_register_agent(self, async_client: AsyncClient):
        """Should be able to register an agent."""
        agent_data = {
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent",
            "version": "1.0.0",
            "task_queue": "test-agent-queue",
            "metadata": {"env": "test"},
            "capabilities": [
                {
                    "name": "analyze",
                    "description": "Analyze data",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "string"},
                    "tags": ["analysis"],
                }
            ],
        }
        response = await async_client.post("/api/v1/agents", json=agent_data)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == "test-agent"
        assert data["name"] == "Test Agent"
        assert data["status"] == "healthy"
        assert data["metadata"] == {"env": "test"}
        assert len(data["capabilities"]) == 1
        assert data["capabilities"][0]["name"] == "analyze"

    async def test_get_agent(self, async_client: AsyncClient):
        """Should be able to get an agent by ID."""
        # First register an agent
        agent_data = {
            "id": "get-test-agent",
            "name": "Get Test Agent",
        }
        await async_client.post("/api/v1/agents", json=agent_data)

        # Then get it
        response = await async_client.get("/api/v1/agents/get-test-agent")
        assert response.status_code == 200
        assert response.json()["name"] == "Get Test Agent"

    async def test_get_nonexistent_agent(self, async_client: AsyncClient):
        """Should return 404 for nonexistent agent."""
        response = await async_client.get("/api/v1/agents/nonexistent")
        assert response.status_code == 404

    async def test_update_agent(self, async_client: AsyncClient):
        """Re-registering should update an existing agent."""
        # Register initial agent
        agent_data = {
            "id": "update-test-agent",
            "name": "Initial Name",
            "version": "1.0.0",
        }
        await async_client.post("/api/v1/agents", json=agent_data)

        # Re-register with updated data
        agent_data["name"] = "Updated Name"
        agent_data["version"] = "2.0.0"
        response = await async_client.post("/api/v1/agents", json=agent_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["version"] == "2.0.0"

    async def test_delete_agent(self, async_client: AsyncClient):
        """Should be able to delete an agent."""
        # Register an agent
        agent_data = {
            "id": "delete-test-agent",
            "name": "Delete Test Agent",
        }
        await async_client.post("/api/v1/agents", json=agent_data)

        # Delete it
        response = await async_client.delete("/api/v1/agents/delete-test-agent")
        assert response.status_code == 204

        # Verify it's gone
        response = await async_client.get("/api/v1/agents/delete-test-agent")
        assert response.status_code == 404

    async def test_heartbeat(self, async_client: AsyncClient):
        """Should be able to update agent heartbeat."""
        # Register an agent
        agent_data = {
            "id": "heartbeat-test-agent",
            "name": "Heartbeat Test Agent",
        }
        await async_client.post("/api/v1/agents", json=agent_data)

        # Update heartbeat
        response = await async_client.put("/api/v1/agents/heartbeat-test-agent/heartbeat")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["status"] == "healthy"
        assert "last_heartbeat" in data

    async def test_find_agents_by_capability(self, async_client: AsyncClient):
        """Should find agents by capability."""
        # Register agents with different capabilities
        agent1 = {
            "id": "cap-agent-1",
            "name": "Agent 1",
            "capabilities": [{"name": "analyze"}],
        }
        agent2 = {
            "id": "cap-agent-2",
            "name": "Agent 2",
            "capabilities": [{"name": "analyze"}, {"name": "diagnose"}],
        }
        agent3 = {
            "id": "cap-agent-3",
            "name": "Agent 3",
            "capabilities": [{"name": "diagnose"}],
        }

        await async_client.post("/api/v1/agents", json=agent1)
        await async_client.post("/api/v1/agents", json=agent2)
        await async_client.post("/api/v1/agents", json=agent3)

        # Find by analyze capability
        response = await async_client.get("/api/v1/agents/capability/analyze")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        agent_ids = [a["id"] for a in data]
        assert "cap-agent-1" in agent_ids
        assert "cap-agent-2" in agent_ids


class TestEndpointAPI:
    """Test endpoint registry endpoints."""

    async def test_list_endpoints_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/endpoints")
        assert response.status_code == 200
        assert response.json() == []

    async def test_register_endpoint(self, async_client: AsyncClient):
        """Should be able to register an endpoint."""
        endpoint_data = {
            "id": "vllm-general",
            "name": "vLLM General",
            "service_type": "llm",
            "internal_url": "http://vllm.vllm.svc:8000/v1",
            "external_url": "https://llm.almckay.io/v1",
            "metadata": {"gpu": "rtx4090"},
        }
        response = await async_client.post("/api/v1/endpoints", json=endpoint_data)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == "vllm-general"
        assert data["service_type"] == "llm"
        assert data["metadata"] == {"gpu": "rtx4090"}

    async def test_get_endpoint(self, async_client: AsyncClient):
        """Should be able to get an endpoint by ID."""
        endpoint_data = {
            "id": "get-test-endpoint",
            "name": "Test Endpoint",
            "service_type": "database",
        }
        await async_client.post("/api/v1/endpoints", json=endpoint_data)

        response = await async_client.get("/api/v1/endpoints/get-test-endpoint")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Endpoint"

    async def test_get_nonexistent_endpoint(self, async_client: AsyncClient):
        """Should return 404 for nonexistent endpoint."""
        response = await async_client.get("/api/v1/endpoints/nonexistent")
        assert response.status_code == 404

    async def test_update_endpoint_health(self, async_client: AsyncClient):
        """Should be able to update endpoint health status."""
        endpoint_data = {
            "id": "health-test-endpoint",
            "name": "Health Test",
            "service_type": "llm",
        }
        await async_client.post("/api/v1/endpoints", json=endpoint_data)

        # Update health
        response = await async_client.put(
            "/api/v1/endpoints/health-test-endpoint/health",
            json={"status": "healthy", "details": {"latency_ms": 50}},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["metadata"]["last_health_details"]["latency_ms"] == 50

    async def test_resolve_endpoint_internal(self, async_client: AsyncClient):
        """Should resolve to internal URL when preferred."""
        endpoint_data = {
            "id": "resolve-test",
            "name": "Resolve Test",
            "service_type": "llm",
            "internal_url": "http://internal:8000",
            "external_url": "https://external.com",
        }
        await async_client.post("/api/v1/endpoints", json=endpoint_data)

        response = await async_client.get(
            "/api/v1/endpoints/resolve/resolve-test",
            params={"prefer_internal": "true"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["url"] == "http://internal:8000"
        assert data["is_internal"] is True

    async def test_resolve_endpoint_external(self, async_client: AsyncClient):
        """Should resolve to external URL when preferred."""
        endpoint_data = {
            "id": "resolve-test-ext",
            "name": "Resolve Test External",
            "service_type": "llm",
            "internal_url": "http://internal:8000",
            "external_url": "https://external.com",
        }
        await async_client.post("/api/v1/endpoints", json=endpoint_data)

        response = await async_client.get(
            "/api/v1/endpoints/resolve/resolve-test-ext",
            params={"prefer_internal": "false"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["url"] == "https://external.com"
        assert data["is_internal"] is False

    async def test_list_endpoints_by_type(self, async_client: AsyncClient):
        """Should filter endpoints by service type."""
        # Register endpoints of different types
        await async_client.post(
            "/api/v1/endpoints",
            json={"id": "llm-1", "name": "LLM 1", "service_type": "llm"},
        )
        await async_client.post(
            "/api/v1/endpoints",
            json={"id": "db-1", "name": "DB 1", "service_type": "database"},
        )

        response = await async_client.get("/api/v1/endpoints/type/llm")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "llm-1"


class TestModelAPI:
    """Test model registry endpoints."""

    async def test_list_models_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/models")
        assert response.status_code == 200
        assert response.json() == []

    async def test_register_model(self, async_client: AsyncClient):
        """Should be able to register a model."""
        model_data = {
            "id": "nvidia/Qwen3-14B-FP4",
            "name": "Qwen3-14B-FP4",
            "model_type": "general",
            "provider": "nvidia",
            "quantization": "FP4",
            "context_length": 32768,
            "vram_required_gb": 8.0,
            "capabilities": {"tool_use": True, "vision": False},
            "metadata": {"source": "huggingface"},
        }
        response = await async_client.post("/api/v1/models", json=model_data)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == "nvidia/Qwen3-14B-FP4"
        assert data["model_type"] == "general"
        assert data["metadata"] == {"source": "huggingface"}

    async def test_get_model(self, async_client: AsyncClient):
        """Should be able to get a model by ID."""
        model_data = {
            "id": "get-test-model",
            "name": "Test Model",
            "model_type": "embeddings",
        }
        await async_client.post("/api/v1/models", json=model_data)

        response = await async_client.get("/api/v1/models/get-test-model")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Model"

    async def test_get_nonexistent_model(self, async_client: AsyncClient):
        """Should return 404 for nonexistent model."""
        response = await async_client.get("/api/v1/models/nonexistent")
        assert response.status_code == 404

    async def test_list_models_by_type(self, async_client: AsyncClient):
        """Should filter models by type."""
        await async_client.post(
            "/api/v1/models",
            json={"id": "gen-1", "name": "General 1", "model_type": "general"},
        )
        await async_client.post(
            "/api/v1/models",
            json={"id": "emb-1", "name": "Embeddings 1", "model_type": "embeddings"},
        )

        response = await async_client.get("/api/v1/models/type/general")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "gen-1"

    async def test_update_model_status(self, async_client: AsyncClient):
        """Should update model status."""
        model_data = {
            "id": "status-test-model",
            "name": "Status Test",
            "model_type": "general",
        }
        await async_client.post("/api/v1/models", json=model_data)

        response = await async_client.put(
            "/api/v1/models/status-test-model/status",
            params={"new_status": "loading"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "loading"


class TestMCPServerAPI:
    """Test MCP server registry endpoints."""

    async def test_list_mcp_servers_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/mcp/servers")
        assert response.status_code == 200
        assert response.json() == []

    async def test_register_mcp_server(self, async_client: AsyncClient):
        """Should be able to register an MCP server."""
        server_data = {
            "id": "kubernetes-mcp",
            "name": "Kubernetes MCP",
            "description": "MCP server for Kubernetes operations",
            "transport": "stdio",
            "connection_config": {
                "command": "uv",
                "args": ["run", "kubernetes-mcp"],
            },
            "capabilities": ["pods_list", "pods_log"],
            "namespaces": ["ai-agents", "vllm"],
            "read_only": True,
        }
        response = await async_client.post("/api/v1/mcp/servers", json=server_data)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == "kubernetes-mcp"
        assert data["transport"] == "stdio"
        assert data["read_only"] is True
        assert data["health_endpoint"] == "/health"
        assert data["metrics_endpoint"] == "/metrics"
        assert data["last_heartbeat"] is None
        assert data["backend_status"] == {}

    async def test_heartbeat_updates_timestamp(self, async_client: AsyncClient):
        """Heartbeat should update last_heartbeat timestamp and status."""
        # Register a server
        server_data = {
            "id": "heartbeat-test-server",
            "name": "Heartbeat Test Server",
            "transport": "sse",
            "connection_config": {"url": "http://server:8000"},
        }
        await async_client.post("/api/v1/mcp/servers", json=server_data)

        # Send heartbeat
        heartbeat_data = {
            "status": "healthy",
            "backend_status": {
                "discord_api": "healthy",
                "redis_cache": "healthy",
            },
        }
        response = await async_client.put(
            "/api/v1/mcp/servers/heartbeat-test-server/heartbeat",
            json=heartbeat_data,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["last_heartbeat"] is not None
        assert data["backend_status"]["discord_api"] == "healthy"
        assert data["backend_status"]["redis_cache"] == "healthy"

    async def test_heartbeat_nonexistent_server(self, async_client: AsyncClient):
        """Heartbeat for nonexistent server should return 404."""
        heartbeat_data = {"status": "healthy"}
        response = await async_client.put(
            "/api/v1/mcp/servers/nonexistent/heartbeat",
            json=heartbeat_data,
        )
        assert response.status_code == 404

    async def test_list_servers_with_status_filter(self, async_client: AsyncClient):
        """Should filter servers by status."""
        # Register servers with different statuses
        await async_client.post(
            "/api/v1/mcp/servers",
            json={
                "id": "healthy-server",
                "name": "Healthy Server",
                "transport": "sse",
                "connection_config": {"url": "http://healthy:8000"},
            },
        )
        await async_client.put(
            "/api/v1/mcp/servers/healthy-server/heartbeat",
            json={"status": "healthy"},
        )

        await async_client.post(
            "/api/v1/mcp/servers",
            json={
                "id": "unhealthy-server",
                "name": "Unhealthy Server",
                "transport": "sse",
                "connection_config": {"url": "http://unhealthy:8000"},
            },
        )
        await async_client.put(
            "/api/v1/mcp/servers/unhealthy-server/heartbeat",
            json={"status": "unhealthy"},
        )

        # Filter by healthy
        response = await async_client.get("/api/v1/mcp/servers?status_filter=healthy")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "healthy-server"

        # Filter by unhealthy
        response = await async_client.get("/api/v1/mcp/servers?status_filter=unhealthy")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "unhealthy-server"

    async def test_query_returns_connection_info(self, async_client: AsyncClient):
        """Query should return complete connection information."""
        server_data = {
            "id": "connection-test-server",
            "name": "Connection Test Server",
            "transport": "sse",
            "connection_config": {
                "url": "https://server.almckay.io/sse",
                "internal_url": "http://server.ai-agents.svc:8080/sse",
            },
            "capabilities": ["tool1", "tool2"],
        }
        await async_client.post("/api/v1/mcp/servers", json=server_data)

        response = await async_client.get("/api/v1/mcp/servers/connection-test-server")
        assert response.status_code == 200

        data = response.json()
        assert data["connection_config"]["url"] == "https://server.almckay.io/sse"
        assert data["connection_config"]["internal_url"] == "http://server.ai-agents.svc:8080/sse"
        assert data["capabilities"] == ["tool1", "tool2"]
        assert data["transport"] == "sse"

    async def test_register_mcp_policy(self, async_client: AsyncClient):
        """Should be able to register an MCP policy."""
        # First register a server
        server_data = {
            "id": "policy-test-server",
            "name": "Policy Test Server",
            "transport": "sse",
            "connection_config": {"url": "http://server:8000"},
        }
        await async_client.post("/api/v1/mcp/servers", json=server_data)

        # Then register a policy
        policy_data = {
            "agent_pattern": "k8s-*",
            "allowed_tools": ["pods_list", "pods_log"],
            "require_approval": ["pods_delete"],
            "priority": 10,
        }
        response = await async_client.post(
            "/api/v1/mcp/servers/policy-test-server/policies",
            json=policy_data,
        )
        assert response.status_code == 201

    async def test_get_mcp_policy(self, async_client: AsyncClient):
        """Should get effective policy for an agent."""
        # Register agent first
        await async_client.post(
            "/api/v1/agents",
            json={"id": "policy-agent", "name": "Policy Agent"},
        )

        response = await async_client.get("/api/v1/mcp/policy/policy-agent")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "policy-agent"
        assert "servers" in data
        assert "policies" in data


class TestSkillAPI:
    """Test skill metadata endpoints."""

    async def test_list_skills_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/skills")
        assert response.status_code == 200
        assert response.json() == []

    async def test_sync_skill_metadata(self, async_client: AsyncClient):
        """Should sync skill metadata from Qdrant."""
        skill_data = {
            "id": "diagnose-pod-crash",
            "name": "Diagnose Pod Crash",
            "domain": "kubernetes",
            "category": "diagnostics",
            "confidence": 0.8,
        }
        response = await async_client.post("/api/v1/skills", json=skill_data)
        assert response.status_code == 201

        data = response.json()
        assert data["id"] == "diagnose-pod-crash"
        assert data["confidence"] == 0.8

    async def test_record_skill_outcome_success(self, async_client: AsyncClient):
        """Should update skill confidence on success."""
        # Create a skill
        skill_data = {
            "id": "outcome-test-skill",
            "name": "Outcome Test",
            "domain": "test",
            "category": "test",
            "confidence": 0.5,
        }
        await async_client.post("/api/v1/skills", json=skill_data)

        # Record success
        response = await async_client.put(
            "/api/v1/skills/outcome-test-skill/outcome",
            json={"success": True},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success_count"] == 1
        assert data["confidence"] > 0.5  # Confidence should increase


class TestDeploymentAPI:
    """Test deployment tracking endpoints."""

    async def test_list_deployments_empty(self, async_client: AsyncClient):
        """Empty registry should return empty list."""
        response = await async_client.get("/api/v1/deployments")
        assert response.status_code == 200
        assert response.json() == []

    async def test_record_deployment(self, async_client: AsyncClient):
        """Should record a deployment."""
        deployment_data = {
            "agent_id": "k8s-monitor",
            "version": "0.2.15",
            "image_tag": "0.2.15-abc1234",
            "git_sha": "abc1234",
            "deployed_by": "ci-bot",
        }
        response = await async_client.post("/api/v1/deployments", json=deployment_data)
        assert response.status_code == 201

        data = response.json()
        assert data["agent_id"] == "k8s-monitor"
        assert data["version"] == "0.2.15"
        assert data["status"] == "active"

    async def test_get_deployment_history(self, async_client: AsyncClient):
        """Should get deployment history for an agent."""
        # Create multiple deployments
        for version in ["0.2.13", "0.2.14", "0.2.15"]:
            await async_client.post(
                "/api/v1/deployments",
                json={
                    "agent_id": "history-agent",
                    "version": version,
                    "image_tag": f"{version}-sha",
                },
            )

        response = await async_client.get("/api/v1/deployments/agent/history-agent")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_rollback_deployment(self, async_client: AsyncClient):
        """Should support deployment rollback."""
        # Create two deployments
        resp1 = await async_client.post(
            "/api/v1/deployments",
            json={"agent_id": "rollback-agent", "version": "1.0.0"},
        )
        dep1_id = resp1.json()["id"]

        await async_client.post(
            "/api/v1/deployments",
            json={"agent_id": "rollback-agent", "version": "1.1.0"},
        )

        # Rollback to first deployment
        response = await async_client.post(f"/api/v1/deployments/{dep1_id}/rollback")
        assert response.status_code == 200

        data = response.json()
        assert data["rollback_from"] == dep1_id
