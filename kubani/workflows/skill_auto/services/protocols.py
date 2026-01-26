"""Protocol definitions for external dependencies.

These protocols define the contracts for external dependencies used by
the service layer. By programming to these protocols, services can be
easily tested with mock implementations.
"""

from typing import Any, Protocol


class LLMClient(Protocol):
    """
    Protocol for LLM client used by services.

    This defines the minimal interface needed to interact with an LLM.
    Implementations can wrap OpenAI, vLLM, or any other LLM provider.
    """

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Make a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response

        Returns:
            Dict with at least 'content' key containing the response text.
            May also include 'tokens' dict with usage info.
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

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """
        List files in a directory matching a pattern.

        Args:
            path: Directory path
            pattern: Glob pattern to match (default: "*")

        Returns:
            List of matching file paths
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
            Dict with 'message_id' of the sent message
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


__all__ = [
    "LLMClient",
    "FileSystem",
    "DiscordClient",
]
