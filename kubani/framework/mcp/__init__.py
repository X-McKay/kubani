"""
MCP Client Module.

Provides unified access to all MCP servers and skill filtering.

Usage:
    from framework.mcp import get_mcp_client, MCPClient

    client = get_mcp_client()

    # Use specific MCP servers
    await client.temporal.list_workflows()
    await client.memory.store_learning(...)
    await client.skills.execute_skill(...)
"""

from framework.mcp.client import (
    DiscordMCPClient,
    MCPClient,
    MCPResponse,
    MCPServerClient,
    MemoryMCPClient,
    QdrantMCPClient,
    RegistryMCPClient,
    SkillsMCPClient,
    TemporalMCPClient,
    close_mcp_client,
    get_mcp_client,
)
from framework.mcp.skills import (
    SkillInfo,
    execute_skill,
    filter_skills,
    get_filtered_skills,
    get_skill_as_tool,
    get_skills_as_tools,
)

__all__ = [
    # Client classes
    "MCPClient",
    "MCPServerClient",
    "MCPResponse",
    "TemporalMCPClient",
    "QdrantMCPClient",
    "MemoryMCPClient",
    "DiscordMCPClient",
    "RegistryMCPClient",
    "SkillsMCPClient",
    # Client functions
    "get_mcp_client",
    "close_mcp_client",
    # Skill filtering
    "SkillInfo",
    "filter_skills",
    "get_filtered_skills",
    "get_skill_as_tool",
    "get_skills_as_tools",
    "execute_skill",
]
