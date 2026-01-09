"""
Context Engineering module for AI agents.

Implements context optimization strategies proven by industry leaders:
1. todo.md file management for task focus and audit trail
2. Error context preservation to prevent repetition
3. Context compression and summarization
4. KV-cache optimization through prompt structuring

These techniques have been shown to achieve 5-10x cost reduction
and significant performance improvements in production systems.

Usage:
    from core_agents.context import ContextManager, TodoManager, ErrorContext

    # Create context manager
    ctx = ContextManager(working_dir="/tmp/agent-work")

    # Manage todo list
    ctx.todo.add_task("Investigate pod crash")
    ctx.todo.complete_task(0)

    # Track errors
    ctx.errors.record_error("kubectl get pods failed", "connection refused")
    if ctx.errors.has_similar_error("connection refused"):
        # Try different approach
        pass
"""

from core_agents.context.manager import ContextManager
from core_agents.context.todo import TodoManager, TodoItem, TodoStatus
from core_agents.context.errors import ErrorContext, ErrorRecord
from core_agents.context.compression import ContextCompressor

__all__ = [
    "ContextManager",
    "TodoManager",
    "TodoItem",
    "TodoStatus",
    "ErrorContext",
    "ErrorRecord",
    "ContextCompressor",
]
