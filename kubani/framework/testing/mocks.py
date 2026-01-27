"""Mock implementations for testing.

Usage:
    from kubani.framework.testing.mocks import MockLLM, MockFileSystem

    @pytest.fixture
    def mock_llm():
        return MockLLM(responses=["Expected response"])

    @pytest.fixture
    def mock_fs():
        return MockFileSystem()

    async def test_my_function(mock_llm, mock_fs):
        mock_fs.files["input.txt"] = "hello"
        result = await my_function(mock_llm, mock_fs)
        assert result == "Expected response"
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockLLM:
    """Mock LLM for testing.

    Implements LLMProtocol. Cycles through responses list.

    Example:
        llm = MockLLM(responses=["First", "Second"])
        assert await llm.chat([...]) == "First"
        assert await llm.chat([...]) == "Second"
        assert await llm.chat([...]) == "First"  # cycles
    """

    responses: list[str] = field(default_factory=lambda: ["Mock response"])
    call_count: int = 0
    calls: list[dict] = field(default_factory=list)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Return next response from queue."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return response


@dataclass
class MockFileSystem:
    """In-memory file system mock for testing.

    Implements FileSystemProtocol using dictionaries.

    Example:
        fs = MockFileSystem()
        fs.write("test.txt", "content")
        assert fs.read("test.txt") == "content"
        assert fs.exists("test.txt")

        # Pre-populate files
        fs = MockFileSystem(files={"config.yaml": "key: value"})
    """

    files: dict[str, str] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)
    call_log: list[tuple[str, Any]] = field(default_factory=list)

    def read(self, path: str) -> str:
        """Read file content."""
        self.call_log.append(("read", path))
        if path not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        """Write content to file."""
        self.call_log.append(("write", (path, content)))
        # Auto-create parent directories
        parts = path.rsplit("/", 1)
        if len(parts) > 1:
            self.directories.add(parts[0])
        self.files[path] = content

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        self.call_log.append(("exists", path))
        return path in self.files or path in self.directories

    def mkdir(self, path: str) -> None:
        """Create directory."""
        self.call_log.append(("mkdir", path))
        self.directories.add(path)

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List files matching pattern."""
        self.call_log.append(("list_files", (path, pattern)))
        import fnmatch

        prefix = path.rstrip("/") + "/"
        matches = []
        for filepath in self.files:
            if filepath.startswith(prefix):
                relative = filepath[len(prefix) :]
                # Only match files directly in path (not nested)
                if "/" not in relative and fnmatch.fnmatch(relative, pattern):
                    matches.append(filepath)
        return matches

    def copy(self, src: str, dst: str) -> None:
        """Copy file."""
        self.call_log.append(("copy", (src, dst)))
        if src not in self.files:
            raise FileNotFoundError(f"Source file not found: {src}")
        self.files[dst] = self.files[src]

    def move(self, src: str, dst: str) -> None:
        """Move file."""
        self.call_log.append(("move", (src, dst)))
        if src not in self.files:
            raise FileNotFoundError(f"Source file not found: {src}")
        self.files[dst] = self.files[src]
        del self.files[src]

    def list_dir(self, path: str) -> list[str]:
        """List directory contents."""
        self.call_log.append(("list_dir", path))
        prefix = path.rstrip("/") + "/"
        names = set()
        for filepath in self.files:
            if filepath.startswith(prefix):
                relative = filepath[len(prefix) :]
                # Get first component
                name = relative.split("/")[0]
                names.add(name)
        return list(names)

    def delete(self, path: str) -> None:
        """Delete file or directory."""
        self.call_log.append(("delete", path))
        if path in self.files:
            del self.files[path]
        elif path in self.directories:
            self.directories.remove(path)
            # Also remove files in directory
            prefix = path.rstrip("/") + "/"
            to_delete = [f for f in self.files if f.startswith(prefix)]
            for f in to_delete:
                del self.files[f]


@dataclass
class MockSkillExecutor:
    """Mock skill executor for testing."""

    results: dict[str, dict] = field(default_factory=dict)
    call_count: int = 0
    calls: list[dict] = field(default_factory=list)

    async def execute(
        self,
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return mock result for skill."""
        self.calls.append(
            {
                "skill_path": skill_path,
                "context": context,
                "timeout": timeout,
            }
        )
        self.call_count += 1
        return self.results.get(skill_path, {"success": True, "output": "mock"})


@dataclass
class MockDiscordClient:
    """Mock Discord client for testing."""

    sent_messages: list[dict] = field(default_factory=list)
    reactions: dict[str, list[str]] = field(default_factory=dict)
    reaction_responses: dict[str, dict] = field(default_factory=dict)
    message_counter: int = 0

    async def send_embed(
        self,
        channel_name: str,
        embed: dict[str, Any],
    ) -> dict[str, Any]:
        """Record sent message and return mock IDs."""
        self.message_counter += 1
        msg_id = f"mock_msg_{self.message_counter}"
        self.sent_messages.append(
            {
                "channel_name": channel_name,
                "embed": embed,
                "message_id": msg_id,
            }
        )
        return {"message_id": msg_id, "channel_id": f"mock_channel_{channel_name}"}

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Record reaction."""
        key = f"{channel_id}:{message_id}"
        if key not in self.reactions:
            self.reactions[key] = []
        self.reactions[key].append(emoji)

    async def await_reaction(
        self,
        channel_id: str,
        message_id: str,
        valid_emojis: list[str],
        timeout_seconds: int = 300,
    ) -> dict[str, Any] | None:
        """Return pre-configured reaction response."""
        key = f"{channel_id}:{message_id}"
        return self.reaction_responses.get(key)


@dataclass
class MockConfig:
    """Mock configuration for testing."""

    llm_api_url: str = "http://localhost:8000/v1"
    llm_model: str = "test-model"
    llm_temperature: float = 0.0


__all__ = [
    "MockLLM",
    "MockFileSystem",
    "MockSkillExecutor",
    "MockDiscordClient",
    "MockConfig",
]
