"""Protocol definitions for dependency injection and testing.

These protocols define contracts for external dependencies, allowing
capabilities to be tested with mock implementations.

Usage:
    from kubani.framework.protocols import LLMProtocol, FileSystemProtocol

    def my_function(llm: LLMProtocol):
        result = await llm.chat([{"role": "user", "content": "Hello"}])
        return result

    # In tests:
    from kubani.framework.testing.mocks import MockLLM
    result = await my_function(MockLLM(responses=["Hi there!"]))
"""

from typing import Any, Protocol, runtime_checkable

# =============================================================================
# LLM Protocols
# =============================================================================


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for LLM chat interactions.

    This is the primary LLM interface used across Kubani.
    FrameworkLLM implements this protocol.
    """

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send chat completion request, return content string."""
        ...

    async def chat_structured[T](
        self,
        messages: list[dict[str, str]],
        output_model: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Send chat completion and return validated structured output.

        Uses Strands structured_output_model to guarantee type-safe responses.
        """
        ...


# =============================================================================
# File System Protocol
# =============================================================================


@runtime_checkable
class FileSystemProtocol(Protocol):
    """Protocol for file system operations.

    Defines the interface for file I/O operations. Use DefaultFileSystem
    for production and MockFileSystem for testing.

    Example:
        from kubani.framework.utils import DefaultFileSystem
        from kubani.framework.protocols import FileSystemProtocol

        def process_files(fs: FileSystemProtocol):
            content = fs.read("input.txt")
            fs.write("output.txt", content.upper())
    """

    def read(self, path: str) -> str:
        """Read file content as a string."""
        ...

    def write(self, path: str, content: str) -> None:
        """Write content to a file, creating parent directories if needed."""
        ...

    def exists(self, path: str) -> bool:
        """Check if a file or directory exists."""
        ...

    def mkdir(self, path: str) -> None:
        """Create a directory and parents if needed."""
        ...

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List files matching a glob pattern."""
        ...

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        ...

    def move(self, src: str, dst: str) -> None:
        """Move file or directory from src to dst."""
        ...

    def list_dir(self, path: str) -> list[str]:
        """List directory contents (names only)."""
        ...

    def delete(self, path: str) -> None:
        """Delete a file or directory."""
        ...


# =============================================================================
# Discord Protocol
# =============================================================================


@runtime_checkable
class DiscordClientProtocol(Protocol):
    """Protocol for Discord messaging operations.

    Defines the interface for sending notifications to Discord.
    """

    async def send_embed(
        self,
        channel_name: str,
        embed: dict[str, Any],
    ) -> dict[str, Any]:
        """Send an embed message to a Discord channel.

        Returns dict with 'message_id' and 'channel_id'.
        """
        ...

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Add a reaction to a message."""
        ...

    async def await_reaction(
        self,
        channel_id: str,
        message_id: str,
        valid_emojis: list[str],
        timeout_seconds: int = 300,
    ) -> dict[str, Any] | None:
        """Wait for a reaction on a message.

        Returns dict with 'emoji' and 'user_name', or None if timeout.
        """
        ...


# =============================================================================
# Registry Protocol
# =============================================================================


@runtime_checkable
class RegistryClientProtocol(Protocol):
    """Protocol for registry operations (skills, agents)."""

    async def sync_skill(
        self,
        skill_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Sync a skill to the registry."""
        ...

    async def sync_agent(
        self,
        agent_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Sync an agent to the registry."""
        ...


# =============================================================================
# Other Protocols
# =============================================================================


@runtime_checkable
class SkillExecutorProtocol(Protocol):
    """Protocol for skill execution."""

    async def execute(
        self,
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a skill and return results."""
        ...


@runtime_checkable
class ConfigProtocol(Protocol):
    """Protocol for configuration access."""

    @property
    def llm_api_url(self) -> str: ...

    @property
    def llm_model(self) -> str: ...

    @property
    def llm_temperature(self) -> float: ...


__all__ = [
    "LLMProtocol",
    "FileSystemProtocol",
    "DiscordClientProtocol",
    "RegistryClientProtocol",
    "SkillExecutorProtocol",
    "ConfigProtocol",
]
