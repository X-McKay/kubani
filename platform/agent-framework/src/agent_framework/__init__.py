"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)

Example:
    from agent_framework import AgentBase, AgentRunner
    from agent_framework.config import AgentConfig
    from agent_framework.mixins import SkillLoaderMixin, ObservabilityMixin

    class MyAgent(AgentBase, SkillLoaderMixin, ObservabilityMixin):
        async def initialize(self) -> None:
            await super().initialize()
            await self.init_skills()
            self.init_observability()

        async def run(self) -> None:
            while self.running:
                await self.process_next()

    if __name__ == "__main__":
        from agent_framework.runner import run_agent
        run_agent(MyAgent, name="my-agent")
"""

from agent_framework.base import AgentBase
from agent_framework.config import AgentConfig, RunMode, SkillConfig
from agent_framework.runner import AgentRunner, run_agent
from agent_framework.skill_executor import SkillExecutor
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

__all__ = [
    # Core classes
    "AgentBase",
    "AgentRunner",
    "SkillExecutor",
    # Config
    "AgentConfig",
    "RunMode",
    "SkillConfig",
    # Trace
    "ExecutionTrace",
    "TraceSpan",
    "SpanKind",
    # Convenience
    "run_agent",
]

__version__ = "0.1.0"
