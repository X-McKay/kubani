"""
MCP-based Kubernetes tools for k8s-monitor.

Uses HTTP/SSE transport to connect to kubernetes-mcp-server, which can run as:
- Sidecar container (in-cluster): localhost:8080
- Local process (development): localhost:8080

This provides a consistent interface regardless of environment.
"""

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default MCP server URL (sidecar or local)
DEFAULT_MCP_SERVER_URL = "http://localhost:8080"


def get_mcp_server_url() -> str:
    """
    Get the MCP server URL from environment or default.

    Environment variables (in order of precedence):
        KUBERNETES_MCP_SERVER_URL: Full URL to MCP server (e.g., http://localhost:8080/sse)
        MCP_SERVER_URL: Base URL to MCP server (e.g., http://localhost:8080)
    """
    # Check for full URL with path
    full_url = os.environ.get("KUBERNETES_MCP_SERVER_URL")
    if full_url:
        # Extract base URL if it has a path
        if "/sse" in full_url or "/mcp" in full_url:
            return full_url.rsplit("/", 1)[0]
        return full_url

    return os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)


class MCPHttpClient:
    """
    HTTP client for MCP server using Streamable HTTP transport.

    The kubernetes-mcp-server exposes:
    - /mcp - Streamable HTTP endpoint (POST for requests)
    - /sse - Server-Sent Events endpoint (for streaming)

    We use the /mcp endpoint for simple request/response.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        """
        Initialize the MCP HTTP client.

        Args:
            base_url: MCP server base URL (default: from env or localhost:8080)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or get_mcp_server_url()
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Call an MCP tool via HTTP.

        Args:
            tool_name: Name of the tool (e.g., "pods_delete", "resources_scale")
            params: Parameters for the tool

        Returns:
            Result dict with tool response or error
        """
        client = await self._ensure_client()

        # MCP JSON-RPC request format
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
        }

        try:
            response = await client.post("/mcp", json=request)
            response.raise_for_status()

            result = response.json()

            # Check for JSON-RPC error
            if "error" in result:
                error = result["error"]
                return {
                    "success": False,
                    "error": error.get("message", str(error)),
                }

            # Extract tool result
            tool_result = result.get("result", {})

            # Handle different result formats
            if isinstance(tool_result, dict):
                # Check for content array (MCP tool response format)
                if "content" in tool_result:
                    content = tool_result["content"]
                    if isinstance(content, list) and content:
                        # Extract text content
                        text_content = [
                            c.get("text", str(c)) for c in content if c.get("type") == "text"
                        ]
                        return {
                            "success": True,
                            "result": "\n".join(text_content) if text_content else tool_result,
                        }
                return {"success": True, "result": tool_result}

            return {"success": True, "result": tool_result}

        except httpx.HTTPStatusError as e:
            logger.error(f"MCP HTTP error: {e.response.status_code} - {e.response.text}")
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text}"}

        except httpx.RequestError as e:
            logger.error(f"MCP request error: {e}")
            return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            return {"success": False, "error": str(e)}

    async def list_tools(self) -> list[str]:
        """
        List available tools from the MCP server.

        Returns:
            List of tool names
        """
        client = await self._ensure_client()

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }

        try:
            response = await client.post("/mcp", json=request)
            response.raise_for_status()

            result = response.json()
            tools = result.get("result", {}).get("tools", [])
            return [t.get("name", "") for t in tools]

        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}")
            return []

    async def health_check(self) -> bool:
        """
        Check if the MCP server is healthy.

        Returns:
            True if server is responding, False otherwise
        """
        try:
            client = await self._ensure_client()
            response = await client.get("/mcp")
            return response.status_code in (
                200,
                405,
            )  # 405 = method not allowed (GET on POST endpoint)
        except Exception:
            return False


# Singleton client instance
_mcp_client: MCPHttpClient | None = None


def get_mcp_client() -> MCPHttpClient:
    """Get or create the singleton MCP client."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPHttpClient()
    return _mcp_client


async def call_mcp_tool_async(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Call an MCP tool asynchronously.

    Args:
        tool_name: Name of the MCP tool
        params: Parameters for the tool

    Returns:
        Result dict with 'success' and 'result' or 'error' keys
    """
    client = get_mcp_client()
    return await client.call_tool(tool_name, params)


def call_mcp_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Call an MCP tool synchronously.

    This is a convenience wrapper for sync code. For async code,
    use call_mcp_tool_async directly.

    Args:
        tool_name: Name of the MCP tool
        params: Parameters for the tool

    Returns:
        Result dict with 'success' and 'result' or 'error' keys
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(call_mcp_tool_async(tool_name, params))


# =============================================================================
# Tool name mappings for convenience
# =============================================================================

TOOL_NAME_MAP = {
    # Pod operations
    "list_pods": "pods_list",
    "get_pod": "pods_get",
    "get_pod_logs": "pods_log",
    "delete_pod": "pods_delete",
    "exec_in_pod": "pods_exec",
    "run_pod": "pods_run",
    "pods_top": "pods_top",
    # Node operations
    "nodes_top": "nodes_top",
    "node_logs": "nodes_log",
    "node_stats": "nodes_stats_summary",
    # Events
    "list_events": "events_list",
    # Namespaces
    "list_namespaces": "namespaces_list",
    # Generic resources
    "get_resource": "resources_get",
    "list_resources": "resources_list",
    "create_resource": "resources_create_or_update",
    "delete_resource": "resources_delete",
    "scale_resource": "resources_scale",
    # Helm
    "helm_install": "helm_install",
    "helm_list": "helm_list",
    "helm_uninstall": "helm_uninstall",
    # Config
    "get_config": "configuration_view",
}


def normalize_tool_name(name: str) -> str:
    """Convert semantic tool name to MCP tool name."""
    return TOOL_NAME_MAP.get(name, name)


# =============================================================================
# High-level convenience functions
# =============================================================================


async def delete_pod(name: str, namespace: str = "default") -> dict[str, Any]:
    """Delete a pod."""
    return await call_mcp_tool_async("pods_delete", {"name": name, "namespace": namespace})


async def get_pod(name: str, namespace: str = "default") -> dict[str, Any]:
    """Get pod details."""
    return await call_mcp_tool_async("pods_get", {"name": name, "namespace": namespace})


async def get_pod_logs(
    name: str,
    namespace: str = "default",
    container: str | None = None,
    tail: int = 100,
) -> dict[str, Any]:
    """Get pod logs."""
    params: dict[str, Any] = {"name": name, "namespace": namespace, "tail": tail}
    if container:
        params["container"] = container
    return await call_mcp_tool_async("pods_log", params)


async def list_pods(
    namespace: str | None = None,
    label_selector: str | None = None,
) -> dict[str, Any]:
    """List pods."""
    params: dict[str, Any] = {}
    if namespace:
        params["namespace"] = namespace
    if label_selector:
        params["labelSelector"] = label_selector
    tool = "pods_list_in_namespace" if namespace else "pods_list"
    return await call_mcp_tool_async(tool, params)


async def list_events(namespace: str | None = None) -> dict[str, Any]:
    """List cluster events."""
    params: dict[str, Any] = {}
    if namespace:
        params["namespace"] = namespace
    return await call_mcp_tool_async("events_list", params)


async def scale_resource(
    name: str,
    namespace: str = "default",
    kind: str = "Deployment",
    scale: int | None = None,
) -> dict[str, Any]:
    """Scale a resource (Deployment, StatefulSet, etc.)."""
    params: dict[str, Any] = {
        "name": name,
        "namespace": namespace,
        "apiVersion": "apps/v1",
        "kind": kind,
    }
    if scale is not None:
        params["scale"] = scale
    return await call_mcp_tool_async("resources_scale", params)


async def get_resource(
    name: str,
    kind: str,
    namespace: str | None = None,
    api_version: str = "v1",
) -> dict[str, Any]:
    """Get a Kubernetes resource."""
    params: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "apiVersion": api_version,
    }
    if namespace:
        params["namespace"] = namespace
    return await call_mcp_tool_async("resources_get", params)
