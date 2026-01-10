"""
Todo management for context engineering.

Implements the todo.md pattern for maintaining agent focus and providing
a clear audit trail of task progress. This approach has been shown to
significantly improve agent performance by keeping the agent focused
on the current objective.

Usage:
    from core_agents.context.todo import TodoManager

    todo = TodoManager(working_dir="/tmp/agent-work")
    todo.add_task("Investigate pod crash in namespace prod")
    todo.add_task("Check pod logs for errors")
    todo.complete_task(0)
    todo.add_task("Increase memory limits based on findings")
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TodoStatus(Enum):
    """Status of a todo item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class TodoItem:
    """A single todo item."""

    description: str
    status: TodoStatus = TodoStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    notes: str = ""
    subtasks: list["TodoItem"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self, indent: int = 0) -> str:
        """Convert to markdown format."""
        prefix = "  " * indent
        if self.status == TodoStatus.COMPLETED:
            checkbox = "[x]"
        elif self.status == TodoStatus.IN_PROGRESS:
            checkbox = "[~]"
        elif self.status == TodoStatus.BLOCKED:
            checkbox = "[!]"
        elif self.status == TodoStatus.SKIPPED:
            checkbox = "[-]"
        else:
            checkbox = "[ ]"

        line = f"{prefix}- {checkbox} {self.description}"
        if self.notes:
            line += f" _{self.notes}_"

        lines = [line]
        for subtask in self.subtasks:
            lines.append(subtask.to_markdown(indent + 1))

        return "\n".join(lines)

    @classmethod
    def from_markdown_line(cls, line: str) -> "TodoItem | None":
        """Parse a markdown todo line."""
        line = line.strip()
        if not line.startswith("- ["):
            return None

        # Extract checkbox status
        if line.startswith("- [x]"):
            status = TodoStatus.COMPLETED
        elif line.startswith("- [~]"):
            status = TodoStatus.IN_PROGRESS
        elif line.startswith("- [!]"):
            status = TodoStatus.BLOCKED
        elif line.startswith("- [-]"):
            status = TodoStatus.SKIPPED
        elif line.startswith("- [ ]"):
            status = TodoStatus.PENDING
        else:
            return None

        # Extract description (after checkbox)
        description = line[6:].strip()

        # Extract notes if present (italic text at end)
        notes = ""
        if "_" in description:
            parts = description.rsplit("_", 2)
            if len(parts) >= 3 and parts[-1] == "":
                notes = parts[-2]
                description = parts[0].strip()

        return cls(description=description, status=status, notes=notes)


@dataclass
class TodoManagerConfig:
    """Configuration for TodoManager."""

    filename: str = "todo.md"
    auto_save: bool = True
    max_history_items: int = 50
    include_timestamps: bool = True


class TodoManager:
    """
    Manages a todo.md file for agent task tracking.

    The todo.md pattern helps agents maintain focus by:
    1. Providing a clear list of pending tasks
    2. Tracking completed work for context
    3. Enabling dynamic task addition during execution
    4. Creating an audit trail for debugging
    """

    def __init__(
        self,
        working_dir: str | Path,
        config: TodoManagerConfig | None = None,
    ):
        """
        Initialize the TodoManager.

        Args:
            working_dir: Directory where todo.md will be stored
            config: Optional configuration
        """
        self.working_dir = Path(working_dir)
        self.config = config or TodoManagerConfig()
        self.todo_path = self.working_dir / self.config.filename

        self._tasks: list[TodoItem] = []
        self._completed_history: list[TodoItem] = []

        # Ensure directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Load existing todo if present
        if self.todo_path.exists():
            self._load()

        logger.debug(f"TodoManager initialized at {self.todo_path}")

    def _load(self) -> None:
        """Load todo items from file."""
        try:
            content = self.todo_path.read_text()
            self._tasks = []
            self._completed_history = []

            in_completed_section = False
            for line in content.split("\n"):
                if "## Completed" in line:
                    in_completed_section = True
                    continue
                if "## " in line and "Completed" not in line:
                    in_completed_section = False

                item = TodoItem.from_markdown_line(line)
                if item:
                    if in_completed_section or item.status == TodoStatus.COMPLETED:
                        self._completed_history.append(item)
                    else:
                        self._tasks.append(item)

            logger.debug(
                f"Loaded {len(self._tasks)} tasks, {len(self._completed_history)} completed"
            )
        except Exception as e:
            logger.warning(f"Failed to load todo.md: {e}")

    def _save(self) -> None:
        """Save todo items to file."""
        if not self.config.auto_save:
            return

        lines = ["# Agent Todo List", ""]

        if self.config.include_timestamps:
            lines.append(f"_Last updated: {datetime.now(UTC).isoformat()}_")
            lines.append("")

        # Current tasks
        lines.append("## Current Tasks")
        lines.append("")
        if self._tasks:
            for task in self._tasks:
                lines.append(task.to_markdown())
        else:
            lines.append("_No pending tasks_")
        lines.append("")

        # Completed history (limited)
        if self._completed_history:
            lines.append("## Completed")
            lines.append("")
            for task in self._completed_history[-self.config.max_history_items :]:
                lines.append(task.to_markdown())
            lines.append("")

        self.todo_path.write_text("\n".join(lines))
        logger.debug(f"Saved todo.md with {len(self._tasks)} tasks")

    def add_task(
        self,
        description: str,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
        position: int | None = None,
    ) -> int:
        """
        Add a new task to the todo list.

        Args:
            description: Task description
            notes: Optional notes
            metadata: Optional metadata
            position: Insert position (None = end)

        Returns:
            Index of the added task
        """
        task = TodoItem(
            description=description,
            notes=notes,
            metadata=metadata or {},
        )

        if position is None:
            self._tasks.append(task)
            idx = len(self._tasks) - 1
        else:
            self._tasks.insert(position, task)
            idx = position

        self._save()
        logger.info(f"Added task [{idx}]: {description}")
        return idx

    def add_subtask(self, parent_idx: int, description: str, notes: str = "") -> None:
        """Add a subtask to an existing task."""
        if 0 <= parent_idx < len(self._tasks):
            subtask = TodoItem(description=description, notes=notes)
            self._tasks[parent_idx].subtasks.append(subtask)
            self._save()
            logger.debug(f"Added subtask to [{parent_idx}]: {description}")

    def start_task(self, idx: int) -> bool:
        """Mark a task as in progress."""
        if 0 <= idx < len(self._tasks):
            self._tasks[idx].status = TodoStatus.IN_PROGRESS
            self._save()
            logger.info(f"Started task [{idx}]: {self._tasks[idx].description}")
            return True
        return False

    def complete_task(self, idx: int, notes: str = "") -> bool:
        """
        Mark a task as completed.

        Args:
            idx: Task index
            notes: Optional completion notes

        Returns:
            True if task was completed
        """
        if 0 <= idx < len(self._tasks):
            task = self._tasks[idx]
            task.status = TodoStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            if notes:
                task.notes = notes

            # Move to history
            self._completed_history.append(task)
            self._tasks.pop(idx)

            self._save()
            logger.info(f"Completed task: {task.description}")
            return True
        return False

    def block_task(self, idx: int, reason: str) -> bool:
        """Mark a task as blocked."""
        if 0 <= idx < len(self._tasks):
            self._tasks[idx].status = TodoStatus.BLOCKED
            self._tasks[idx].notes = reason
            self._save()
            logger.warning(f"Blocked task [{idx}]: {reason}")
            return True
        return False

    def skip_task(self, idx: int, reason: str = "") -> bool:
        """Skip a task."""
        if 0 <= idx < len(self._tasks):
            task = self._tasks[idx]
            task.status = TodoStatus.SKIPPED
            if reason:
                task.notes = reason

            self._completed_history.append(task)
            self._tasks.pop(idx)

            self._save()
            logger.info(f"Skipped task: {task.description}")
            return True
        return False

    def get_current_task(self) -> TodoItem | None:
        """Get the current (first in-progress or first pending) task."""
        for task in self._tasks:
            if task.status == TodoStatus.IN_PROGRESS:
                return task
        for task in self._tasks:
            if task.status == TodoStatus.PENDING:
                return task
        return None

    def get_pending_tasks(self) -> list[TodoItem]:
        """Get all pending tasks."""
        return [t for t in self._tasks if t.status == TodoStatus.PENDING]

    def get_all_tasks(self) -> list[TodoItem]:
        """Get all current tasks."""
        return list(self._tasks)

    def get_context_summary(self, max_tasks: int = 5) -> str:
        """
        Get a summary suitable for LLM context.

        Args:
            max_tasks: Maximum tasks to include

        Returns:
            Formatted summary string
        """
        lines = ["## Current Todo"]

        current = self.get_current_task()
        if current:
            lines.append(f"**Current Focus**: {current.description}")
            if current.notes:
                lines.append(f"  Notes: {current.notes}")

        pending = self.get_pending_tasks()[:max_tasks]
        if pending:
            lines.append("")
            lines.append("**Pending Tasks**:")
            for i, task in enumerate(pending):
                lines.append(f"  {i + 1}. {task.description}")

        recent_completed = self._completed_history[-3:]
        if recent_completed:
            lines.append("")
            lines.append("**Recently Completed**:")
            for task in recent_completed:
                lines.append(f"  - {task.description}")

        return "\n".join(lines)

    def clear_completed(self) -> int:
        """Clear completed history. Returns number cleared."""
        count = len(self._completed_history)
        self._completed_history = []
        self._save()
        return count

    def reset(self) -> None:
        """Reset all tasks."""
        self._tasks = []
        self._completed_history = []
        self._save()
        logger.info("Todo list reset")
