"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)
- LLM: LLM client and skill executor
- Evaluation: Model comparison matrix
- Backends: Trace storage (JSONL, DuckDB)

Example:
    from agent_framework import AgentBase, AgentRunner, SkillExecutor
    from agent_framework.llm import LLMClientWrapper
    from agent_framework.evaluation import ModelMatrix
    from agent_framework.backends import DuckDBBackend
"""

from agent_framework.backends import DuckDBBackend, JsonlBackend, TraceBackend, TraceQuery
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
    # Backends
    "TraceBackend",
    "TraceQuery",
    "JsonlBackend",
    "DuckDBBackend",
    # Convenience
    "run_agent",
]

__version__ = "0.3.0"
