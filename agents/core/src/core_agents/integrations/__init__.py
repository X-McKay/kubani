"""
External service integrations.

Provides utilities for integrating with external services like
Discord, Temporal, MCP servers, and GitOps.

Modules:
    discord: Discord formatting utilities (embeds, colors)
    discord_mcp: Discord MCP integration (primary way to send messages)
    temporal: Temporal workflow client helpers
    mcp: MCP server registry and configuration
    gitops: GitOps deployment automation
"""

from core_agents.integrations.discord import (
    Colors,
    DiscordEmbed,
)
from core_agents.integrations.discord_mcp import (
    DEFAULT_CHANNELS,
    DEFAULT_MCP_URL,
    DiscordMCPConfig,
    add_reaction,
    await_reaction,
    is_mcp_discord_configured,
    send_discord_message,
    send_discord_message_sync,
)
from core_agents.integrations.gitops import (
    DeploymentResult,
    FluxStatus,
    GitOpsAgent,
    GitOpsConfig,
    GitOpsManager,
    quick_deploy,
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
    # Discord formatting utilities
    "DiscordEmbed",
    "Colors",
    # Discord MCP (primary integration)
    "send_discord_message",
    "send_discord_message_sync",
    "add_reaction",
    "await_reaction",
    "is_mcp_discord_configured",
    "DiscordMCPConfig",
    "DEFAULT_MCP_URL",
    "DEFAULT_CHANNELS",
    # Temporal
    "get_temporal_client",
    "get_local_temporal_client",
    # MCP
    "MCPRegistry",
    "MCPServerConfig",
    "AgentPolicy",
    "get_registry",
    "get_mcp_server_config",
    # GitOps
    "GitOpsAgent",
    "GitOpsManager",
    "GitOpsConfig",
    "DeploymentResult",
    "FluxStatus",
    "quick_deploy",
]
