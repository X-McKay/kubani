"""
MCP-based Kubernetes tools for k8s-monitor.

Uses Strands' native MCP integration to connect to kubernetes-mcp-server,
replacing the Python kubernetes client with MCP protocol calls.

This provides:
- Standardized protocol for Kubernetes operations
- Reduced code complexity (no direct K8s client management)
- Consistent tool interface across agents
- Better observability through MCP tracing
"""

import logging
import os
from contextlib import contextmanager
from typing import Any

from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Default kubernetes-mcp-server command
DEFAULT_MCP_COMMAND = "npx"
DEFAULT_MCP_ARGS = ["-y", "@anthropics/kubernetes-mcp-server@latest"]


def get_mcp_server_params() -> StdioServerParameters:
    """
    Get MCP server parameters from environment or defaults.

    Environment variables:
        MCP_K8S_COMMAND: Command to run MCP server (default: npx)
        MCP_K8S_ARGS: Comma-separated args (default: -y,@anthropics/kubernetes-mcp-server@latest)
        KUBECONFIG: Path to kubeconfig file (passed to MCP server)
    """
    command = os.environ.get("MCP_K8S_COMMAND", DEFAULT_MCP_COMMAND)
    args_str = os.environ.get("MCP_K8S_ARGS")
    args = args_str.split(",") if args_str else DEFAULT_MCP_ARGS

    # Build environment for MCP server
    env = dict(os.environ)

    # Ensure KUBECONFIG is set for the MCP server
    if "KUBECONFIG" not in env:
        # Try common locations
        kubeconfig_paths = [
            "/etc/kubernetes/kubeconfig",  # In-cluster mount
            os.path.expanduser("~/.kube/config"),  # Default location
        ]
        for path in kubeconfig_paths:
            if os.path.exists(path):
                env["KUBECONFIG"] = path
                break

    return StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )


@contextmanager
def get_k8s_mcp_client():
    """
    Get a configured MCP client for kubernetes-mcp-server.

    Usage:
        with get_k8s_mcp_client() as client:
            tools = client.list_tools_sync()
            # Use tools with agent

    Yields:
        Configured MCPClient connected to kubernetes-mcp-server
    """
    params = get_mcp_server_params()
    logger.info(f"Connecting to kubernetes-mcp-server: {params.command} {' '.join(params.args)}")

    client = MCPClient(lambda: stdio_client(params))

    with client:
        logger.info("Connected to kubernetes-mcp-server")
        yield client


def get_k8s_mcp_tools() -> list[Any]:
    """
    Get all Kubernetes tools from the MCP server.

    This returns the raw MCP tools that can be passed directly to a Strands Agent.

    Returns:
        List of MCP tools for Kubernetes operations

    Note:
        This should be called within an MCP client context:

        with get_k8s_mcp_client() as client:
            tools = get_k8s_mcp_tools_from_client(client)
    """
    with get_k8s_mcp_client() as client:
        return client.list_tools_sync()


def get_k8s_mcp_tools_from_client(client: MCPClient) -> list[Any]:
    """
    Get Kubernetes tools from an existing MCP client.

    Args:
        client: Active MCPClient connected to kubernetes-mcp-server

    Returns:
        List of MCP tools for Kubernetes operations
    """
    return client.list_tools_sync()


# Tool name mappings for convenience
# Maps our semantic names to kubernetes-mcp-server tool names
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


def find_tool_by_name(tools: list[Any], name: str) -> Any | None:
    """
    Find a specific tool by name from the MCP tools list.

    Args:
        tools: List of MCP tools
        name: Tool name (can be our semantic name or MCP tool name)

    Returns:
        The tool if found, None otherwise
    """
    # Check if it's one of our mapped names
    mcp_name = TOOL_NAME_MAP.get(name, name)

    for tool in tools:
        tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", "")
        if tool_name in (mcp_name, name):
            return tool

    return None


class K8sMCPToolset:
    """
    High-level toolset for Kubernetes MCP operations.

    Provides a convenient interface for creating agents with MCP tools.

    Usage:
        toolset = K8sMCPToolset()
        with toolset:
            agent = Agent(tools=toolset.all_tools)
            # Or create agent with the toolset itself
            agent = toolset.create_agent(name="scout", system_prompt="...")
    """

    def __init__(self):
        self._client: MCPClient | None = None
        self._tools: list[Any] | None = None

    def __enter__(self):
        """Enter context - connect to MCP server."""
        params = get_mcp_server_params()
        self._client = MCPClient(lambda: stdio_client(params))
        self._client.__enter__()
        self._tools = self._client.list_tools_sync()
        logger.info(f"K8sMCPToolset connected with {len(self._tools)} tools")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - disconnect from MCP server."""
        if self._client:
            self._client.__exit__(exc_type, exc_val, exc_tb)
        self._tools = None
        return False

    @property
    def all_tools(self) -> list[Any]:
        """Get all available Kubernetes tools."""
        if self._tools is None:
            raise RuntimeError("K8sMCPToolset must be used within a context manager")
        return self._tools

    @property
    def client(self) -> MCPClient:
        """Get the underlying MCP client."""
        if self._client is None:
            raise RuntimeError("K8sMCPToolset must be used within a context manager")
        return self._client

    def get_tool(self, name: str) -> Any | None:
        """Get a specific tool by name."""
        return find_tool_by_name(self.all_tools, name)

    def get_read_only_tools(self) -> list[Any]:
        """
        Get only read-only tools (no create/delete/scale operations).

        Useful for scout/diagnostic agents that shouldn't modify cluster state.
        """
        read_only_patterns = [
            "list",
            "get",
            "log",
            "top",
            "stats",
            "view",
            "events",
        ]
        write_patterns = [
            "create",
            "delete",
            "update",
            "scale",
            "exec",
            "run",
            "install",
            "uninstall",
        ]

        result = []
        for tool in self.all_tools:
            tool_name = getattr(tool, "name", "") or getattr(tool, "__name__", "")
            is_read_only = any(p in tool_name.lower() for p in read_only_patterns)
            is_write = any(p in tool_name.lower() for p in write_patterns)

            if is_read_only and not is_write:
                result.append(tool)

        return result

    def get_remediation_tools(self) -> list[Any]:
        """
        Get tools useful for remediation (including write operations).

        Includes: delete, scale, exec, run operations.
        """
        remediation_patterns = [
            "delete",
            "scale",
            "exec",
            "run",
            "restart",
        ]

        result = []
        for tool in self.all_tools:
            tool_name = getattr(tool, "name", "") or getattr(tool, "__name__", "")
            if any(p in tool_name.lower() for p in remediation_patterns):
                result.append(tool)

        return result


# Singleton toolset for shared access
_global_toolset: K8sMCPToolset | None = None


def get_global_toolset() -> K8sMCPToolset:
    """
    Get or create the global K8sMCPToolset.

    For use in applications that manage a single MCP connection.

    Warning: Caller must ensure proper context management.
    """
    global _global_toolset
    if _global_toolset is None:
        _global_toolset = K8sMCPToolset()
    return _global_toolset
