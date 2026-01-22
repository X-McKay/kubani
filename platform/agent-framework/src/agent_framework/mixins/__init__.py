"""Composable agent mixins."""

from agent_framework.mixins.mcp import MCPClientMixin
from agent_framework.mixins.observability import ObservabilityMixin
from agent_framework.mixins.skills import SkillLoaderMixin

__all__ = [
    "MCPClientMixin",
    "ObservabilityMixin",
    "SkillLoaderMixin",
]
