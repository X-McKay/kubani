"""
Unified context manager for AI agents.

Integrates all context engineering components:
- Todo management for task focus
- Error tracking for mistake prevention
- Context compression for efficiency
- Session state management

Usage:
    from core_agents.context import ContextManager

    ctx = ContextManager(working_dir="/tmp/agent-work", agent_id="my-agent")

    # Task management
    ctx.todo.add_task("Investigate issue")
    ctx.todo.start_task(0)

    # Error tracking
    ctx.errors.record_error("kubectl get pods", "connection refused")

    # Get full context for LLM
    context = ctx.get_llm_context()
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core_agents.context.compression import CompressionConfig, ContextCompressor
from core_agents.context.errors import ErrorContext, ErrorContextConfig
from core_agents.context.todo import TodoManager, TodoManagerConfig

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """State of the current agent session."""

    session_id: str
    agent_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    iteration_count: int = 0
    total_tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "iteration_count": self.iteration_count,
            "total_tokens_used": self.total_tokens_used,
            "metadata": self.metadata,
        }


@dataclass
class ContextManagerConfig:
    """Configuration for ContextManager."""

    # Sub-component configs
    todo_config: TodoManagerConfig = field(default_factory=TodoManagerConfig)
    error_config: ErrorContextConfig = field(default_factory=ErrorContextConfig)
    compression_config: CompressionConfig = field(default_factory=CompressionConfig)

    # Session settings
    persist_session: bool = True
    session_file: str = "session.json"

    # Context generation settings
    max_context_tokens: int = 8000
    include_todo_in_context: bool = True
    include_errors_in_context: bool = True
    include_session_info: bool = True


class ContextManager:
    """
    Unified context manager for AI agent execution.

    Provides a single interface for all context engineering needs:
    - Task tracking via todo.md
    - Error context preservation
    - Context compression and optimization
    - Session state management
    """

    def __init__(
        self,
        working_dir: str | Path,
        agent_id: str,
        session_id: str | None = None,
        config: ContextManagerConfig | None = None,
    ):
        """
        Initialize the context manager.

        Args:
            working_dir: Working directory for the agent
            agent_id: Unique identifier for the agent
            session_id: Optional session ID (auto-generated if not provided)
            config: Optional configuration
        """
        self.working_dir = Path(working_dir)
        self.agent_id = agent_id
        self.config = config or ContextManagerConfig()

        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Initialize sub-components
        self.todo = TodoManager(self.working_dir, self.config.todo_config)
        self.errors = ErrorContext(self.config.error_config)
        self.compressor = ContextCompressor(self.config.compression_config)

        # Initialize session
        self.session = SessionState(
            session_id=session_id or self._generate_session_id(),
            agent_id=agent_id,
        )

        # Custom context sections
        self._custom_context: dict[str, str] = {}

        # Load persisted session if available
        if self.config.persist_session:
            self._load_session()

        logger.info(
            f"ContextManager initialized for {agent_id} (session: {self.session.session_id})"
        )

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid

        return (
            f"{self.agent_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )

    def _load_session(self) -> None:
        """Load session state from file."""
        session_path = self.working_dir / self.config.session_file
        if session_path.exists():
            try:
                data = json.loads(session_path.read_text())
                self.session.iteration_count = data.get("iteration_count", 0)
                self.session.total_tokens_used = data.get("total_tokens_used", 0)
                self.session.metadata = data.get("metadata", {})
                logger.debug(f"Loaded session state: {self.session.iteration_count} iterations")
            except Exception as e:
                logger.warning(f"Failed to load session: {e}")

    def _save_session(self) -> None:
        """Save session state to file."""
        if not self.config.persist_session:
            return

        session_path = self.working_dir / self.config.session_file
        try:
            session_path.write_text(json.dumps(self.session.to_dict(), indent=2))
        except Exception as e:
            logger.warning(f"Failed to save session: {e}")

    def record_iteration(self, tokens_used: int = 0) -> None:
        """
        Record an agent iteration.

        Args:
            tokens_used: Tokens used in this iteration
        """
        self.session.iteration_count += 1
        self.session.total_tokens_used += tokens_used
        self.session.last_activity = datetime.now(UTC)
        self._save_session()

    def add_custom_context(self, key: str, content: str) -> None:
        """
        Add custom context section.

        Args:
            key: Section identifier
            content: Context content
        """
        self._custom_context[key] = content

    def remove_custom_context(self, key: str) -> None:
        """Remove a custom context section."""
        self._custom_context.pop(key, None)

    def get_llm_context(
        self,
        include_todo: bool | None = None,
        include_errors: bool | None = None,
        include_session: bool | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Get formatted context for LLM consumption.

        Combines all context sources into a single formatted string
        suitable for inclusion in system prompts or messages.

        Args:
            include_todo: Include todo context (default from config)
            include_errors: Include error context (default from config)
            include_session: Include session info (default from config)
            max_tokens: Maximum tokens for context (default from config)

        Returns:
            Formatted context string
        """
        include_todo = (
            include_todo if include_todo is not None else self.config.include_todo_in_context
        )
        include_errors = (
            include_errors if include_errors is not None else self.config.include_errors_in_context
        )
        include_session = (
            include_session if include_session is not None else self.config.include_session_info
        )
        max_tokens = max_tokens or self.config.max_context_tokens

        sections = []

        # Session info
        if include_session:
            session_info = [
                "## Session Info",
                f"- Agent: {self.agent_id}",
                f"- Session: {self.session.session_id}",
                f"- Iteration: {self.session.iteration_count}",
                f"- Started: {self.session.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            ]
            sections.append("\n".join(session_info))

        # Todo context
        if include_todo:
            todo_context = self.todo.get_context_summary()
            if todo_context:
                sections.append(todo_context)

        # Error context
        if include_errors:
            error_context = self.errors.get_context_summary()
            if error_context:
                sections.append(error_context)

        # Custom context sections
        for key, content in self._custom_context.items():
            sections.append(f"## {key}\n{content}")

        # Combine and compress if needed
        full_context = "\n\n".join(sections)

        # Estimate tokens and compress if needed
        estimated_tokens = self.compressor.estimate_tokens(full_context)
        if estimated_tokens > max_tokens:
            full_context = self.compressor.summarize_for_context(
                full_context,
                max_length=max_tokens * 4,  # Approximate chars
            )

        return full_context

    def get_system_prompt_addition(self) -> str:
        """
        Get context suitable for appending to system prompts.

        Returns a condensed version of the context optimized for
        system prompt inclusion.

        Returns:
            Formatted context string
        """
        lines = [
            "",
            "---",
            "## Agent Context",
            "",
        ]

        # Current task focus
        current_task = self.todo.get_current_task()
        if current_task:
            lines.append(f"**Current Task**: {current_task.description}")

        # Pending tasks count
        pending = self.todo.get_pending_tasks()
        if pending:
            lines.append(f"**Pending Tasks**: {len(pending)}")

        # Recent errors warning
        recent_errors = self.errors.get_recent_errors(3)
        if recent_errors:
            lines.append("")
            lines.append("**Recent Errors** (avoid repeating):")
            for err in recent_errors:
                lines.append(f"  - {err.action}: {err.error_message[:50]}")

        lines.append("")
        lines.append("---")

        return "\n".join(lines)

    def create_checkpoint(self, name: str = "") -> dict[str, Any]:
        """
        Create a checkpoint of current context state.

        Args:
            name: Optional checkpoint name

        Returns:
            Checkpoint data
        """
        checkpoint = {
            "name": name or f"checkpoint-{datetime.now(UTC).isoformat()}",
            "timestamp": datetime.now(UTC).isoformat(),
            "session": self.session.to_dict(),
            "errors": self.errors.to_dict(),
            "todo_tasks": len(self.todo.get_all_tasks()),
            "custom_context_keys": list(self._custom_context.keys()),
        }

        # Save checkpoint file
        checkpoint_path = self.working_dir / f"checkpoint-{self.session.iteration_count}.json"
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2))

        logger.info(f"Created checkpoint: {checkpoint['name']}")
        return checkpoint

    def reset(self, keep_session: bool = True) -> None:
        """
        Reset context state.

        Args:
            keep_session: Whether to keep session info
        """
        self.todo.reset()
        self.errors.clear()
        self._custom_context.clear()

        if not keep_session:
            self.session = SessionState(
                session_id=self._generate_session_id(),
                agent_id=self.agent_id,
            )

        self._save_session()
        logger.info("Context reset")


def create_context_manager(
    working_dir: str | Path,
    agent_id: str,
    **kwargs,
) -> ContextManager:
    """
    Factory function to create a ContextManager.

    Args:
        working_dir: Working directory
        agent_id: Agent identifier
        **kwargs: Additional config options

    Returns:
        Configured ContextManager
    """
    config = ContextManagerConfig()

    # Apply any config overrides
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)

    return ContextManager(working_dir, agent_id, config=config)
