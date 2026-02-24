"""MCP client factory for the Nexus agent.

Creates Strands MCPClient instances for the servers permitted by the
active MCP policy. These clients are passed directly to Agent(tools=[...])
which auto-discovers all tools from each server.

Two policy tiers are supported:

``nexus`` (default, conservative):
    Memory + Skills + Fetch
    Safe for all conversational turns. No cluster access.

``nexus-proactive`` (expanded, for mission turns):
    Memory + Skills + Fetch + Kubernetes + Temporal
    Grants read-heavy cluster access for background monitoring missions.
    Destructive operations (delete, scale, terminate) require HITL approval.

Uses strands.tools.mcp.MCPClient — NOT the custom
kubani.framework.mcp.client.MCPClient.
"""

from __future__ import annotations

import logging

from strands.tools.mcp import MCPClient
from strands.tools.mcp.mcp_client import ToolFilters

logger = logging.getLogger(__name__)

# Operational tools exposed by multiple MCP servers that clash on name
# and aren't useful to the agent. Exclude them to avoid Strands'
# "Tool name already exists" ValueError.
_REJECTED_TOOLS: ToolFilters = {"rejected": ["health", "metrics"]}

# =========================================================================
# Policy definitions
# =========================================================================

# Each policy maps a server name to True (allowed) or False (denied).
# The ``nexus`` policy is the minimum-privilege default.
# The ``nexus-proactive`` policy adds cluster-facing servers for missions.
_POLICIES: dict[str, dict[str, bool]] = {
    "nexus": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": False,
        "temporal": False,
    },
    "nexus-proactive": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": True,
        "temporal": True,
    },
}

_DEFAULT_POLICY = "nexus"


def _get_allowed_servers(policy_name: str) -> set[str]:
    """Return the set of server names permitted by a policy.

    Args:
        policy_name: Name of the MCP policy.

    Returns:
        Set of allowed server names.
    """
    policy = _POLICIES.get(policy_name, _POLICIES[_DEFAULT_POLICY])
    if policy_name not in _POLICIES:
        logger.warning(f"Unknown MCP policy '{policy_name}'; falling back to '{_DEFAULT_POLICY}'")
    return {name for name, allowed in policy.items() if allowed}


# =========================================================================
# Client factory
# =========================================================================


def create_mcp_clients(policy_name: str = "nexus") -> list[MCPClient]:
    """Create MCPClient instances filtered by the given MCP policy.

    Args:
        policy_name: Name of the MCP policy to apply.
            ``nexus`` (default) — memory, skills, fetch.
            ``nexus-proactive`` — adds kubernetes, temporal.

    Returns:
        List of MCPClient instances for servers allowed by the policy.
        Servers that fail to initialise are skipped with a warning.
    """
    from kubani.framework.config import get_config

    config = get_config()
    allowed = _get_allowed_servers(policy_name)
    logger.info(f"MCP policy '{policy_name}': allowed servers = {sorted(allowed)}")

    clients: list[MCPClient] = []

    # ------------------------------------------------------------------
    # SSE-based servers
    # ------------------------------------------------------------------
    sse_candidates: dict[str, str | None] = {
        "memory": config.mcp.memory_url if config.mcp.memory_enabled else None,
        "skills": config.mcp.skills_url if config.mcp.skills_enabled else None,
        "temporal": config.mcp.temporal_url if config.mcp.temporal_enabled else None,
    }

    for name, base_url in sse_candidates.items():
        if name not in allowed:
            continue
        if not base_url:
            logger.debug(f"MCP server '{name}' is disabled in config; skipping")
            continue
        try:
            from mcp.client.sse import sse_client

            sse_url = base_url.rstrip("/") + "/sse"
            client = MCPClient(
                lambda u=sse_url: sse_client(u),
                tool_filters=_REJECTED_TOOLS,
            )
            clients.append(client)
            logger.info(f"Created MCPClient for '{name}' at {sse_url}")
        except Exception as exc:
            logger.warning(f"Failed to create MCPClient for '{name}': {exc}")

    # ------------------------------------------------------------------
    # Kubernetes MCP (npx-based stdio)
    # ------------------------------------------------------------------
    if "kubernetes" in allowed:
        try:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            k8s_client = MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(
                        command="npx",
                        args=["-y", "@modelcontextprotocol/server-kubernetes"],
                    )
                )
            )
            clients.append(k8s_client)
            logger.info("Created MCPClient for 'kubernetes' (stdio/npx)")
        except Exception as exc:
            logger.warning(f"Failed to create MCPClient for 'kubernetes': {exc}")

    # ------------------------------------------------------------------
    # Fetch MCP (in-process stdio, always allowed if in policy)
    # ------------------------------------------------------------------
    if "fetch" in allowed:
        try:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            fetch_client = MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(
                        command="python",
                        args=["-m", "mcp_server_fetch"],
                    )
                )
            )
            clients.append(fetch_client)
            logger.info("Created MCPClient for 'fetch' (stdio)")
        except Exception as exc:
            logger.warning(f"Failed to create MCPClient for 'fetch': {exc}")

    # Eagerly start each client so failures are caught here rather than
    # inside Agent.__init__ where one bad client kills all MCP tools.
    # MCPClient.start() is idempotent — already-started clients are skipped
    # by Agent.load_tools().
    ready: list[MCPClient] = []
    for client in clients:
        try:
            client.start()
            ready.append(client)
        except Exception as exc:
            logger.warning(f"MCP client failed to start, skipping: {exc}")
            try:
                client.stop(None, None, None)
            except Exception:
                pass

    logger.info(
        f"MCP client creation complete: {len(ready)}/{len(clients)} client(s) "
        f"ready for policy '{policy_name}'"
    )
    return ready
