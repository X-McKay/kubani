"""Tests for RegistryMCPClient."""

import httpx
import pytest

from kubani.framework.mcp.client import RegistryMCPClient


class TestRegistryMCPClientAgentManagement:
    """Test agent registration and management"""

    @pytest.mark.asyncio
    async def test_register_agent(self, respx_mock):
        """register_agent should register agent in registry"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"agent_id": "k8s-monitor", "registered": True}},
            )
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.register_agent(
            agent_id="k8s-monitor",
            name="K8s Monitor",
            version="0.1.0",
            capabilities=["monitoring", "remediation"],
            metadata={"description": "K8s monitoring"},
        )

        assert response.success is True
        assert response.data["agent_id"] == "k8s-monitor"
        await client.close()

    @pytest.mark.asyncio
    async def test_heartbeat(self, respx_mock):
        """heartbeat should update agent status"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(
                200, json={"content": {"agent_id": "k8s-monitor", "status": "healthy"}}
            )
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.heartbeat(agent_id="k8s-monitor")

        assert response.success is True
        assert response.data["status"] == "healthy"
        await client.close()

    @pytest.mark.asyncio
    async def test_list_agents(self, respx_mock):
        """list_agents should return all registered agents"""
        respx_mock.post("http://localhost:8085/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "agents": [
                            {"id": "k8s-monitor", "status": "healthy"},
                            {"id": "news-monitor", "status": "healthy"},
                        ]
                    }
                },
            )
        )

        client = RegistryMCPClient("registry", "http://localhost:8085")
        response = await client.list_agents()

        assert response.success is True
        assert len(response.data["agents"]) == 2
        await client.close()
