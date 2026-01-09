"""
MCP Server Registry client for agent discovery.

Provides utilities to read the centralized MCP server registry
ConfigMap and discover available MCP servers for agents.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default registry location
DEFAULT_REGISTRY_NAMESPACE = "ai-agents"
DEFAULT_REGISTRY_NAME = "mcp-server-registry"

# Local development paths (relative to project root)
LOCAL_REGISTRY_PATHS = [
    "mcp/registry.json",
    "../mcp/registry.json",
    "../../mcp/registry.json",
]


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    description: str
    transport: str  # "stdio" or "sse"
    command: str | None = None  # For stdio transport
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None  # For sse transport
    capabilities: list[str] | None = None
    namespaces: list[str] | None = None
    read_only: bool = False


@dataclass
class AgentPolicy:
    """Policy configuration for an agent."""

    allowed_servers: list[str]
    require_approval: list[str]
    audit_log: bool = True
    read_only: bool = False
    namespace_restrictions: dict[str, list[str]] | None = None


@dataclass
class MCPRegistry:
    """Parsed MCP server registry."""

    version: str
    servers: dict[str, MCPServerConfig]
    policies: dict[str, AgentPolicy]

    def get_server(self, name: str) -> MCPServerConfig | None:
        """Get a server configuration by name."""
        return self.servers.get(name)

    def get_policy(self, agent_name: str) -> AgentPolicy:
        """Get policy for an agent, falling back to default."""
        return self.policies.get(
            agent_name,
            self.policies.get(
                "default",
                AgentPolicy(
                    allowed_servers=[],
                    require_approval=["*"],
                    audit_log=True,
                ),
            ),
        )

    def get_allowed_servers(self, agent_name: str) -> list[MCPServerConfig]:
        """Get all servers allowed for an agent."""
        policy = self.get_policy(agent_name)
        return [self.servers[name] for name in policy.allowed_servers if name in self.servers]


def load_registry_from_configmap(
    namespace: str = DEFAULT_REGISTRY_NAMESPACE,
    name: str = DEFAULT_REGISTRY_NAME,
) -> MCPRegistry | None:
    """
    Load MCP registry from Kubernetes ConfigMap.

    Requires running in-cluster or with valid kubeconfig.

    Args:
        namespace: Namespace containing the ConfigMap
        name: Name of the ConfigMap

    Returns:
        Parsed MCPRegistry or None if not available
    """
    try:
        from kubernetes import client, config

        # Try in-cluster config first, fall back to kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        v1 = client.CoreV1Api()
        cm = v1.read_namespaced_config_map(name=name, namespace=namespace)

        if "registry.json" not in cm.data:
            logger.warning(f"ConfigMap {namespace}/{name} missing registry.json")
            return None

        return parse_registry(cm.data["registry.json"])

    except ImportError:
        logger.warning("kubernetes package not installed, cannot load registry from ConfigMap")
        return None
    except Exception as e:
        logger.warning(f"Failed to load MCP registry from ConfigMap: {e}")
        return None


def load_registry_from_file(path: str) -> MCPRegistry | None:
    """
    Load MCP registry from a local JSON file.

    Useful for local development and testing.

    Args:
        path: Path to the registry JSON file

    Returns:
        Parsed MCPRegistry or None if not available
    """
    try:
        with open(path) as f:
            return parse_registry(f.read())
    except Exception as e:
        logger.warning(f"Failed to load MCP registry from file: {e}")
        return None


def load_registry_from_env() -> MCPRegistry | None:
    """
    Load MCP registry from environment variable.

    Looks for MCP_REGISTRY_JSON environment variable.

    Returns:
        Parsed MCPRegistry or None if not available
    """
    registry_json = os.environ.get("MCP_REGISTRY_JSON")
    if registry_json:
        return parse_registry(registry_json)
    return None


def parse_registry(json_str: str) -> MCPRegistry:
    """
    Parse registry JSON into MCPRegistry dataclass.

    Args:
        json_str: JSON string containing registry configuration

    Returns:
        Parsed MCPRegistry
    """
    data = json.loads(json_str)

    # Parse servers
    servers: dict[str, MCPServerConfig] = {}
    for name, server_data in data.get("servers", {}).items():
        servers[name] = MCPServerConfig(
            name=server_data.get("name", name),
            description=server_data.get("description", ""),
            transport=server_data.get("transport", "stdio"),
            command=server_data.get("command"),
            args=server_data.get("args"),
            env=server_data.get("env"),
            url=server_data.get("url"),
            capabilities=server_data.get("capabilities"),
            namespaces=server_data.get("namespaces"),
            read_only=server_data.get("readOnly", False),
        )

    # Parse policies
    policies: dict[str, AgentPolicy] = {}
    for name, policy_data in data.get("policies", {}).items():
        policies[name] = AgentPolicy(
            allowed_servers=policy_data.get("allowedServers", []),
            require_approval=policy_data.get("requireApproval", []),
            audit_log=policy_data.get("auditLog", True),
            read_only=policy_data.get("readOnly", False),
            namespace_restrictions=policy_data.get("namespaceRestrictions"),
        )

    return MCPRegistry(
        version=data.get("version", "1.0"),
        servers=servers,
        policies=policies,
    )


def _find_local_registry() -> Path | None:
    """
    Find local registry file by searching common paths.

    Searches relative to the current working directory.

    Returns:
        Path to registry file if found, None otherwise
    """
    cwd = Path.cwd()
    for rel_path in LOCAL_REGISTRY_PATHS:
        candidate = cwd / rel_path
        if candidate.exists():
            return candidate.resolve()
    return None


def get_registry() -> MCPRegistry | None:
    """
    Get MCP registry using automatic discovery.

    Tries in order:
    1. Environment variable (MCP_REGISTRY_JSON)
    2. Local file (MCP_REGISTRY_FILE env var)
    3. Local file (./mcp/registry.json if exists)
    4. Kubernetes ConfigMap

    Returns:
        MCPRegistry or None if not available
    """
    # Try environment variable first
    registry = load_registry_from_env()
    if registry:
        logger.debug("Loaded MCP registry from environment variable")
        return registry

    # Try local file from env var
    file_path = os.environ.get("MCP_REGISTRY_FILE")
    if file_path:
        registry = load_registry_from_file(file_path)
        if registry:
            logger.debug(f"Loaded MCP registry from file: {file_path}")
            return registry

    # Try local registry paths (for local development)
    local_path = _find_local_registry()
    if local_path:
        registry = load_registry_from_file(str(local_path))
        if registry:
            logger.debug(f"Loaded MCP registry from local path: {local_path}")
            return registry

    # Try Kubernetes ConfigMap
    registry = load_registry_from_configmap()
    if registry:
        logger.debug("Loaded MCP registry from Kubernetes ConfigMap")
        return registry

    logger.warning("No MCP registry available")
    return None


def get_mcp_server_config(
    server_name: str,
    agent_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Get configuration for connecting to an MCP server.

    Returns the configuration in a format suitable for MCP client initialization.

    Args:
        server_name: Name of the MCP server (e.g., "kubernetes")
        agent_name: Optional agent name for policy validation

    Returns:
        Configuration dict for MCP client, or None if not available/allowed
    """
    registry = get_registry()
    if not registry:
        return None

    server = registry.get_server(server_name)
    if not server:
        logger.warning(f"MCP server not found: {server_name}")
        return None

    # Check agent policy if provided
    if agent_name:
        policy = registry.get_policy(agent_name)
        if server_name not in policy.allowed_servers:
            logger.warning(f"Agent {agent_name} not allowed to access MCP server {server_name}")
            return None

    # Build configuration
    config: dict[str, Any] = {
        "name": server.name,
        "transport": server.transport,
    }

    if server.transport == "stdio":
        config["command"] = server.command
        config["args"] = server.args or []
        config["env"] = server.env or {}
    elif server.transport == "sse":
        config["url"] = server.url

    return config
