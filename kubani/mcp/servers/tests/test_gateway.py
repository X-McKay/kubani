"""
Test script for MCP Gateway evaluation.

This script tests the gateway by:
1. Connecting to the gateway
2. Discovering available tools
3. Executing test operations
4. Measuring latency and comparing with direct connections
"""

import asyncio
import time
from typing import Any, Dict, List
import httpx
import pytest


class GatewayTestClient:
    """Client for testing MCP Gateway."""
    
    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available tools through the gateway."""
        response = await self.client.get(f"{self.gateway_url}/tools")
        response.raise_for_status()
        return response.json()
    
    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool through the gateway."""
        start_time = time.time()
        
        response = await self.client.post(
            f"{self.gateway_url}/call",
            json={
                "server": server_id,
                "tool": tool_name,
                "arguments": arguments
            }
        )
        
        latency = time.time() - start_time
        response.raise_for_status()
        
        result = response.json()
        result["_latency_ms"] = latency * 1000
        return result
    
    async def health_check(self) -> Dict[str, Any]:
        """Check gateway health."""
        response = await self.client.get(f"{self.gateway_url}/health")
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the client."""
        await self.client.aclose()


class DirectMCPClient:
    """Client for direct MCP server connections (for comparison)."""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool directly."""
        start_time = time.time()
        
        response = await self.client.post(
            f"{self.server_url}/call",
            json={
                "tool": tool_name,
                "arguments": arguments
            }
        )
        
        latency = time.time() - start_time
        response.raise_for_status()
        
        result = response.json()
        result["_latency_ms"] = latency * 1000
        return result
    
    async def close(self):
        """Close the client."""
        await self.client.aclose()


@pytest.mark.asyncio
async def test_gateway_health():
    """Test that the gateway is healthy and accessible."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    client = GatewayTestClient(gateway_url)
    
    try:
        health = await client.health_check()
        assert health["status"] in ["healthy", "degraded"]
        assert "servers" in health
        
        # Check that upstream servers are registered
        assert len(health["servers"]) > 0
        
        print(f"Gateway health: {health}")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gateway_tool_discovery():
    """Test tool discovery through the gateway."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    client = GatewayTestClient(gateway_url)
    
    try:
        tools = await client.discover_tools()
        assert len(tools) > 0
        
        # Check that tools from multiple servers are available
        server_ids = set(tool["server_id"] for tool in tools)
        assert len(server_ids) > 1
        
        print(f"Discovered {len(tools)} tools from {len(server_ids)} servers")
        print(f"Servers: {server_ids}")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gateway_read_operation():
    """Test a read operation through the gateway."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    client = GatewayTestClient(gateway_url)
    
    try:
        # Test listing skills (read operation)
        result = await client.call_tool(
            server_id="skills-mcp",
            tool_name="list_skills",
            arguments={}
        )
        
        assert "skills" in result or "result" in result
        assert result["_latency_ms"] > 0
        
        print(f"Read operation latency: {result['_latency_ms']:.2f}ms")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gateway_vs_direct_latency():
    """Compare latency between gateway and direct connection."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    direct_url = "http://skills-mcp-server.ai-agents.svc:8080"
    
    gateway_client = GatewayTestClient(gateway_url)
    direct_client = DirectMCPClient(direct_url)
    
    try:
        # Test through gateway
        gateway_result = await gateway_client.call_tool(
            server_id="skills-mcp",
            tool_name="list_skills",
            arguments={}
        )
        gateway_latency = gateway_result["_latency_ms"]
        
        # Test direct connection
        direct_result = await direct_client.call_tool(
            tool_name="list_skills",
            arguments={}
        )
        direct_latency = direct_result["_latency_ms"]
        
        # Calculate overhead
        overhead = gateway_latency - direct_latency
        overhead_percent = (overhead / direct_latency) * 100
        
        print(f"Gateway latency: {gateway_latency:.2f}ms")
        print(f"Direct latency: {direct_latency:.2f}ms")
        print(f"Gateway overhead: {overhead:.2f}ms ({overhead_percent:.1f}%)")
        
        # Gateway should add minimal overhead (< 50ms or < 50%)
        assert overhead < 50 or overhead_percent < 50
        
    finally:
        await gateway_client.close()
        await direct_client.close()


@pytest.mark.asyncio
async def test_gateway_concurrent_requests():
    """Test concurrent requests through the gateway."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    client = GatewayTestClient(gateway_url)
    
    try:
        # Send 10 concurrent requests
        tasks = []
        for i in range(10):
            task = client.call_tool(
                server_id="skills-mcp",
                tool_name="list_skills",
                arguments={}
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All requests should succeed
        assert len(results) == 10
        
        # Calculate average latency
        latencies = [r["_latency_ms"] for r in results]
        avg_latency = sum(latencies) / len(latencies)
        
        print(f"Concurrent requests: {len(results)}")
        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"Min latency: {min(latencies):.2f}ms")
        print(f"Max latency: {max(latencies):.2f}ms")
        
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_gateway_error_handling():
    """Test error handling through the gateway."""
    gateway_url = "http://mcp-gateway.ai-agents-test.svc:8080"
    client = GatewayTestClient(gateway_url)
    
    try:
        # Try to call a non-existent tool
        with pytest.raises(httpx.HTTPStatusError):
            await client.call_tool(
                server_id="skills-mcp",
                tool_name="non_existent_tool",
                arguments={}
            )
        
        # Try to call a non-existent server
        with pytest.raises(httpx.HTTPStatusError):
            await client.call_tool(
                server_id="non-existent-server",
                tool_name="some_tool",
                arguments={}
            )
        
        print("Error handling works correctly")
        
    finally:
        await client.close()


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(test_gateway_health())
    asyncio.run(test_gateway_tool_discovery())
    asyncio.run(test_gateway_read_operation())
    asyncio.run(test_gateway_vs_direct_latency())
    asyncio.run(test_gateway_concurrent_requests())
    asyncio.run(test_gateway_error_handling())
