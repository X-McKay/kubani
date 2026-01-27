"""Protocol definitions for dependency injection and testing.

Usage:
    from kubani.framework.protocols import LLMProtocol

    def my_function(llm: LLMProtocol):
        result = await llm.chat([{"role": "user", "content": "Hello"}])
        return result

    # In tests:
    from kubani.framework.testing.mocks import MockLLM
    result = await my_function(MockLLM(responses=["Hi there!"]))
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for LLM chat interactions."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send chat completion request, return content string."""
        ...


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
