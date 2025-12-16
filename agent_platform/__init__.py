"""
Agent Platform - Shared utilities for Kubani AI agents.

Provides common functionality for agents including:
- LLM client wrappers (vLLM/OpenAI-compatible)
- Temporal workflow helpers
- Discord webhook integration
"""

from agent_platform.discord import send_discord_message
from agent_platform.llm_client import create_vllm_model_provider
from agent_platform.temporal_helpers import get_temporal_client

__all__ = [
    "create_vllm_model_provider",
    "send_discord_message",
    "get_temporal_client",
]
