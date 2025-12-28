"""
Core reusable agents for multi-agent swarms.

These agents are designed to be shared across multiple applications:
- DiscordAgent: Publish notifications to Discord
- MemoryAgent: Store and recall learnings via mem0

Also provides utilities for:
- Temporal workflow connections
- Low-level Discord webhook posting
- mem0 integration with vLLM embeddings
"""

from core_agents.base import create_agent, create_model
from core_agents.discord_agent import (
    DISCORD_AGENT_PROMPT,
    DiscordAgent,
    discord_notify,
)
from core_agents.discord_utils import (
    Colors,
    DiscordEmbed,
    post_discord_message,
    send_discord_message,
    send_discord_message_sync,
)
from core_agents.mem0_utils import (
    VLLM_MODEL_DIMENSIONS,
    get_mem0_config,
)
from core_agents.memory_agent import MEMORY_AGENT_PROMPT, MemoryAgent
from core_agents.temporal import (
    get_local_temporal_client,
    get_temporal_client,
)

__all__ = [
    # Agents
    "DiscordAgent",
    "MemoryAgent",
    # Utilities
    "create_agent",
    "create_model",
    # Tools
    "discord_notify",
    # Prompts
    "DISCORD_AGENT_PROMPT",
    "MEMORY_AGENT_PROMPT",
    # Temporal
    "get_temporal_client",
    "get_local_temporal_client",
    # Discord utilities (low-level)
    "send_discord_message",
    "send_discord_message_sync",
    "post_discord_message",  # Alias for send_discord_message_sync
    "DiscordEmbed",
    "Colors",
    # mem0 utilities
    "get_mem0_config",
    "VLLM_MODEL_DIMENSIONS",
]
