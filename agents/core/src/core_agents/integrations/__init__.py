"""
External service integrations.

Provides utilities for integrating with external services like
Discord, Temporal, and MCP servers.

Modules:
    discord: Discord webhook utilities and message formatting
    temporal: Temporal workflow client helpers
    mcp: MCP server registry and configuration
"""

from core_agents.integrations.discord import (
    Colors,
    DiscordEmbed,
    post_discord_message,
    send_discord_message,
    send_discord_message_sync,
)
from core_agents.integrations.mcp import (
    AgentPolicy,
    MCPRegistry,
    MCPServerConfig,
    get_mcp_server_config,
    get_registry,
)
from core_agents.integrations.temporal import (
    get_local_temporal_client,
    get_temporal_client,
)

__all__ = [
    # Discord
    "send_discord_message",
    "send_discord_message_sync",
    "post_discord_message",
    "DiscordEmbed",
    "Colors",
    # Temporal
    "get_temporal_client",
    "get_local_temporal_client",
    # MCP
    "MCPRegistry",
    "MCPServerConfig",
    "AgentPolicy",
    "get_registry",
    "get_mcp_server_config",
]
