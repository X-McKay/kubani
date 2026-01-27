# kubani/workflows/agent_auto/services/protocols.py
"""Protocol definitions for service dependencies.

These protocols define the interfaces that services depend on,
allowing for easy testing with mock implementations.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM client implementations."""

    async def complete(self, prompt: str) -> str:
        """Generate a completion for the given prompt."""
        ...


@runtime_checkable
class FileSystem(Protocol):
    """Protocol for file system operations."""

    def read(self, path: str) -> str:
        """Read content from a file."""
        ...

    def write(self, path: str, content: str) -> None:
        """Write content to a file."""
        ...

    def exists(self, path: str) -> bool:
        """Check if a path exists."""
        ...

    def mkdir(self, path: str) -> None:
        """Create a directory (and parents if needed)."""
        ...


@dataclass
class SkillInfo:
    """Information about a skill."""

    name: str
    description: str = ""
    version: str = "1.0.0"


@runtime_checkable
class SkillRepository(Protocol):
    """Protocol for skill repository operations."""

    def get_skills_by_name(self, names: list[str]) -> list[SkillInfo]:
        """Get skills by their names."""
        ...

    def list_skills(self) -> list[SkillInfo]:
        """List all available skills."""
        ...


@dataclass
class AgentRunResult:
    """Result from running an agent."""

    output: str
    invoked_skills: list[str]
    success: bool = True
    error: str | None = None


@runtime_checkable
class AgentRunner(Protocol):
    """Protocol for running agent sandboxes."""

    async def run(self, agent_path: str, prompt: str) -> AgentRunResult:
        """Run an agent with the given prompt and return the result."""
        ...
