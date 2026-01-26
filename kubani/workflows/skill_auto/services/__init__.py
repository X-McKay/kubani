"""Service layer for skill_auto workflow.

This layer contains service classes that depend on external resources
(LLM, filesystem, etc.) but use dependency injection for testability.
"""

from .llm import LLMService
from .protocols import DiscordClient, FileSystem, LLMClient

__all__ = [
    "LLMClient",
    "FileSystem",
    "DiscordClient",
    "LLMService",
]
