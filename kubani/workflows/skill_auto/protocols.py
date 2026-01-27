"""Protocol definitions for external dependencies.

These protocols define the contracts for external dependencies used by
the capability layer. By programming to these protocols, capabilities can be
easily tested with mock implementations.
"""

from typing import Any, Protocol


class LLMClient(Protocol):
    """
    Protocol for LLM client used by capabilities.

    This defines the minimal interface needed to interact with an LLM.
    The interface is async and returns strings directly, matching
    kubani.framework.llm.FrameworkLLM.
    """

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Make a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-1.0), None for default
            max_tokens: Maximum tokens in response, None for default

        Returns:
            Response content as string.
        """
        ...


class FileSystem(Protocol):
    """
    Protocol for file system operations.

    This defines the minimal interface needed for file I/O.
    Implementations can use the real filesystem or an in-memory mock.
    """

    def read(self, path: str) -> str:
        """
        Read file content as a string.

        Args:
            path: Path to the file to read

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    def write(self, path: str, content: str) -> None:
        """
        Write content to a file.

        Args:
            path: Path to the file to write
            content: Content to write
        """
        ...

    def exists(self, path: str) -> bool:
        """
        Check if a file or directory exists.

        Args:
            path: Path to check

        Returns:
            True if the path exists
        """
        ...

    def mkdir(self, path: str, parents: bool = True) -> None:
        """
        Create a directory.

        Args:
            path: Directory path to create
            parents: If True, create parent directories as needed
        """
        ...

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """
        List files in a directory matching a glob pattern.

        Args:
            path: Directory path
            pattern: Glob pattern to match (default: "*")

        Returns:
            List of matching file paths
        """
        ...

    def copy(self, src: str, dst: str) -> None:
        """
        Copy file from src to dst.

        Args:
            src: Source file path
            dst: Destination file path
        """
        ...

    def move(self, src: str, dst: str) -> None:
        """
        Move file/directory from src to dst.

        Args:
            src: Source path
            dst: Destination path
        """
        ...

    def list_dir(self, path: str) -> list[str]:
        """
        List files in directory (just names, not full paths).

        Args:
            path: Directory path

        Returns:
            List of file/directory names
        """
        ...

    def delete(self, path: str) -> None:
        """
        Delete a file.

        Args:
            path: Path to the file to delete
        """
        ...


class DiscordClient(Protocol):
    """
    Protocol for Discord messaging operations.

    This defines the interface for sending notifications to Discord.
    """

    async def send_embed(
        self,
        channel_name: str,
        embed: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send an embed message to a Discord channel.

        Args:
            channel_name: Name of the channel to send to
            embed: Embed dict with title, description, color, fields, etc.

        Returns:
            Dict with 'message_id' and 'channel_id' of the sent message
        """
        ...

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """
        Add a reaction to a message.

        Args:
            channel_id: Channel ID containing the message
            message_id: Message ID to react to
            emoji: Emoji to add
        """
        ...

    async def await_reaction(
        self,
        channel_id: str,
        message_id: str,
        valid_emojis: list[str],
        timeout_seconds: int = 300,
    ) -> dict[str, Any] | None:
        """
        Wait for a reaction on a message.

        Args:
            channel_id: Channel ID to watch
            message_id: Message ID to watch
            valid_emojis: List of valid emoji reactions
            timeout_seconds: How long to wait

        Returns:
            Dict with 'emoji' and 'user_name', or None if timeout
        """
        ...


class RegistryClient(Protocol):
    """
    Protocol for skill registry operations.

    This defines the interface for syncing skills to the registry.
    """

    async def sync_skill(
        self,
        skill_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Sync a skill to the registry.

        Args:
            skill_path: Path to the skill directory
            metadata: Skill metadata to register

        Returns:
            Dict with sync status and registry ID
        """
        ...


__all__ = [
    "LLMClient",
    "FileSystem",
    "DiscordClient",
    "RegistryClient",
]
