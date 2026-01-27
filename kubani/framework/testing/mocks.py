"""Mock implementations for testing.

Usage:
    from kubani.framework.testing.mocks import MockLLM, MockSkillExecutor

    @pytest.fixture
    def mock_llm():
        return MockLLM(responses=["Expected response"])

    async def test_my_function(mock_llm):
        result = await my_function(mock_llm)
        assert result == "Expected response"
        assert mock_llm.call_count == 1
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockLLM:
    """Mock LLM for testing."""

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
class MockConfig:
    """Mock configuration for testing."""

    llm_api_url: str = "http://localhost:8000/v1"
    llm_model: str = "test-model"
    llm_temperature: float = 0.0
