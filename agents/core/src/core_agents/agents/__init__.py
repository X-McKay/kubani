"""
Reusable agent implementations.

Provides pre-built agents that can be used across multiple applications.

Modules:
    discord: DiscordAgent for notifications
    memory: MemoryAgent for learning and recall
"""

from core_agents.agents.discord import (
    DISCORD_AGENT_PROMPT,
    DiscordAgent,
    discord_notify,
)
from core_agents.agents.memory import MEMORY_AGENT_PROMPT, MemoryAgent

__all__ = [
    "DiscordAgent",
    "MemoryAgent",
    "discord_notify",
    "DISCORD_AGENT_PROMPT",
    "MEMORY_AGENT_PROMPT",
]
