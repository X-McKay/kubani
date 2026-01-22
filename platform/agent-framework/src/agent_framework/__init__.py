"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)
"""

from agent_framework.base import AgentBase
from agent_framework.runner import AgentRunner
from agent_framework.skill_executor import SkillExecutor

__all__ = ["AgentBase", "AgentRunner", "SkillExecutor"]
__version__ = "0.1.0"
