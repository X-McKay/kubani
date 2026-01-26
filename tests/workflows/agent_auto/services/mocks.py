# tests/workflows/agent_auto/services/mocks.py
"""Mock implementations of service protocols for testing."""

from kubani.workflows.agent_auto.services.protocols import (
    AgentRunResult,
    SkillInfo,
)


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, response_to_return: str = "mock response"):
        self.response_to_return = response_to_return
        self.calls: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response_to_return


class MockFileSystem:
    """Mock file system for testing."""

    def __init__(self):
        self.files: dict[str, str] = {}
        self.directories: set[str] = set()

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def exists(self, path: str) -> bool:
        return path in self.files or path in self.directories

    def mkdir(self, path: str) -> None:
        self.directories.add(path)


class MockSkillRepository:
    """Mock skill repository for testing."""

    def __init__(self, existing_skills: list[dict] | None = None):
        self._skills = [
            SkillInfo(
                name=s.get("name", ""),
                description=s.get("description", ""),
                version=s.get("version", "1.0.0"),
            )
            for s in (existing_skills or [])
        ]

    def get_skills_by_name(self, names: list[str]) -> list[SkillInfo]:
        return [s for s in self._skills if s.name in names]

    def list_skills(self) -> list[SkillInfo]:
        return self._skills


class MockAgentRunner:
    """Mock agent runner for testing."""

    def __init__(
        self,
        output: str = "mock output",
        invoked_skills: list[str] | None = None,
    ):
        self.default_output = output
        self.default_skills = invoked_skills or []
        self.calls: list[tuple[str, str]] = []
        # Map prompt to specific results for more complex testing
        self.results_by_prompt: dict[str, AgentRunResult] = {}

    def set_result_for_prompt(
        self,
        prompt: str,
        output: str,
        invoked_skills: list[str],
        success: bool = True,
    ) -> None:
        """Configure a specific result for a specific prompt."""
        self.results_by_prompt[prompt] = AgentRunResult(
            output=output,
            invoked_skills=invoked_skills,
            success=success,
        )

    async def run(self, agent_path: str, prompt: str) -> AgentRunResult:
        self.calls.append((agent_path, prompt))

        if prompt in self.results_by_prompt:
            return self.results_by_prompt[prompt]

        return AgentRunResult(
            output=self.default_output,
            invoked_skills=self.default_skills,
            success=True,
        )
