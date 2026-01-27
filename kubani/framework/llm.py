"""LLM utilities using Strands Agent SDK.

This module provides a simple interface for LLM interactions that:
1. Uses Strands SDK internally (agentic by nature)
2. Implements LLMProtocol for testability
3. Gets configuration from kubani.framework.config

Usage:
    from kubani.framework.llm import get_llm, FrameworkLLM

    # Simple usage
    llm = get_llm()
    response = await llm.chat([{"role": "user", "content": "Hello"}])

    # With dependency injection
    async def my_function(llm: LLMProtocol):
        return await llm.chat(messages)

    # In production
    await my_function(get_llm())

    # In tests
    await my_function(MockLLM(responses=["test"]))
"""

import logging
from dataclasses import dataclass

from strands import Agent

from kubani.framework.config import get_llm_config

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat completion with metadata."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class FrameworkLLM:
    """
    LLM wrapper using Strands SDK.

    Implements LLMProtocol for dependency injection and testing.
    Uses Strands Agent for agentic workflows - even simple chat completions
    benefit from the agent abstraction for consistency across Kubani.
    """

    def __init__(
        self,
        model: str | None = None,
        api_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """
        Initialize LLM wrapper.

        If parameters not provided, uses kubani.framework.config.
        """
        config = get_llm_config()

        self.model = model or config.model
        self.api_url = api_url or config.api_url
        self.temperature = temperature if temperature is not None else config.temperature
        self.max_tokens = max_tokens or config.max_tokens

        self._agent: Agent | None = None
        self._current_system_prompt: str | None = None

    def _get_agent(self, system_prompt: str | None = None) -> Agent:
        """
        Get or create Strands Agent.

        Creates a new agent if system prompt changes.
        Uses OpenAIModel to connect to vLLM or other OpenAI-compatible endpoints.
        """
        from strands.models.openai import OpenAIModel

        # Create new agent if system prompt changed or first call
        if self._agent is None or system_prompt != self._current_system_prompt:
            self._current_system_prompt = system_prompt

            # Create OpenAI-compatible model pointing to our vLLM endpoint
            model = OpenAIModel(
                client_args={
                    "api_key": "not-needed",  # vLLM doesn't require API key
                    "base_url": self.api_url,
                },
                model_id=self.model,
            )

            self._agent = Agent(
                model=model,
                system_prompt=system_prompt or "",
            )
        return self._agent

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Send chat completion and return content.

        Implements LLMProtocol interface.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (currently not passed to Strands)
            max_tokens: Max tokens (uses instance default if not specified)

        Returns:
            Response content as string
        """
        # Extract system and user messages
        system_messages = [m for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] == "user"]

        if not user_messages:
            raise ValueError("No user message in messages list")

        # Get system prompt if present
        system_prompt = system_messages[-1]["content"] if system_messages else None

        # Get agent with appropriate system prompt
        agent = self._get_agent(system_prompt)

        # Use the last user message as the prompt
        prompt = user_messages[-1]["content"]

        # Run the agent asynchronously
        try:
            result = await agent.invoke_async(prompt)
            # Strands Agent returns AgentResult - extract text content
            # The result.message is typically a dict with 'role' and 'content'
            if hasattr(result, "message"):
                message = result.message
                # Handle dict-style message
                if isinstance(message, dict):
                    content = message.get("content", [])
                    if isinstance(content, list) and content:
                        # Get text from first content block
                        text_block = content[0]
                        if isinstance(text_block, dict):
                            return text_block.get("text", str(message))
                        return str(text_block)
                    return str(content)
                return str(message)
            return str(result)
        except Exception as e:
            logger.error(f"Strands Agent error: {e}")
            raise

    async def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Chat with full response metadata."""
        content = await self.chat(messages, temperature, max_tokens)
        return ChatResponse(
            content=content,
            model=self.model,
            # Token counts would come from Strands internals if available
        )


# Global instance
_llm: FrameworkLLM | None = None


def get_llm() -> FrameworkLLM:
    """Get global LLM instance configured from framework."""
    global _llm
    if _llm is None:
        _llm = FrameworkLLM()
    return _llm


def reset_llm() -> None:
    """Reset global LLM (useful after config changes)."""
    global _llm
    _llm = None
