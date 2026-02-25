"""MCP client factory for the Nexus agent.

Creates Strands MCPClient instances for the servers permitted by the
active MCP policy. These clients are passed directly to Agent(tools=[...])
which auto-discovers all tools from each server.

Three policy tiers are supported:

``nexus`` (default, conservative):
    Memory + Skills + Fetch
    Safe for all conversational turns. No cluster access.

``nexus-proactive`` (expanded, for mission turns):
    Memory + Skills + Fetch + Kubernetes + Temporal
    Grants read-heavy cluster access for background monitoring missions.
    Destructive operations (delete, scale, terminate) require HITL approval.

``nexus-computer`` (computer use):
    Memory + Skills + Fetch + Computer
    Grants browser automation via the computer use MCP server.

Uses strands.tools.mcp.MCPClient — NOT the custom
kubani.framework.mcp.client.MCPClient.
"""

from __future__ import annotations

import logging
import os

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
        "computer": False,
    },
    "nexus-proactive": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": True,
        "temporal": True,
        "computer": False,
    },
    "nexus-computer": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": False,
        "temporal": False,
        "computer": True,
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
            ``nexus-computer`` — adds computer use server.

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
        "computer": os.environ.get("MCP_COMPUTER_URL", ""),
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

    logger.info(
        f"MCP client creation complete: {len(clients)} client(s) for policy '{policy_name}'"
    )
    return clients


async def load_tools_resilient(
    clients: list[MCPClient],
) -> tuple[list, list[MCPClient]]:
    """Load tools from each MCP client individually, skipping failures.

    Strands Agent fails entirely if ANY MCPClient passed to ``tools=``
    fails to start. This helper pre-loads tools from each client so that
    one bad client (e.g. kubernetes npx) doesn't take down the rest.

    Returns:
        Tuple of (loaded_tools, started_clients).
        ``loaded_tools`` are Tool objects to pass to ``Agent(tools=...)``.
        ``started_clients`` must be stopped in the caller's finally block.
    """
    all_tools: list = []
    started: list[MCPClient] = []

    for client in clients:
        try:
            tools = await client.load_tools()
            all_tools.extend(tools)
            started.append(client)
            logger.info(f"Loaded {len(tools)} tool(s) from MCP client")
        except Exception as exc:
            logger.warning(f"MCP client failed to load tools, skipping: {exc}")
            try:
                client.stop(None, None, None)
            except Exception:
                pass

    logger.info(
        f"Resilient tool loading: {len(all_tools)} tools from {len(started)}/{len(clients)} clients"
    )
    return all_tools, started
