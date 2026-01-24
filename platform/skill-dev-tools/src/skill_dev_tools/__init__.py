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
    from skill_dev_tools import AgentBase, AgentRunner, SkillExecutor
    from skill_dev_tools.llm import LLMClientWrapper
    from skill_dev_tools.evaluation import ModelMatrix
    from skill_dev_tools.backends import DuckDBBackend
"""

from skill_dev_tools.backends import DuckDBBackend, JsonlBackend, TraceBackend, TraceQuery
from skill_dev_tools.base import AgentBase
from skill_dev_tools.config import AgentConfig, RunMode, SkillConfig
from skill_dev_tools.runner import AgentRunner, run_agent
from skill_dev_tools.skill_executor import SkillExecutor
from skill_dev_tools.trace import ExecutionTrace, SpanKind, TraceSpan

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
