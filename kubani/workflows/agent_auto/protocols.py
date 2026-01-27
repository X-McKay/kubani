"""Protocol definitions for service dependencies.

These protocols define the interfaces that services depend on,
allowing for easy testing with mock implementations.

Common protocols are imported from kubani.framework.protocols.
Agent-specific protocols are defined here.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Re-export common protocols from framework
from kubani.framework.protocols import (
    FileSystemProtocol,
    LLMProtocol,
)

# Aliases for backwards compatibility
LLMClient = LLMProtocol
FileSystem = FileSystemProtocol


# =============================================================================
# Agent-specific Protocols
# =============================================================================


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


__all__ = [
    # Framework protocols (canonical names)
    "LLMProtocol",
    "FileSystemProtocol",
    # Backwards compatibility aliases
    "LLMClient",
    "FileSystem",
    # Agent-specific types
    "SkillInfo",
    "SkillRepository",
    "AgentRunResult",
    "AgentRunner",
]
