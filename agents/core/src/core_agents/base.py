"""
Shared utilities for core agents.

Provides model creation and agent configuration.
Uses centralized configuration from core_agents.config.
"""

import logging
from collections.abc import Callable

from strands import Agent
from strands.models.openai import OpenAIModel

from core_agents.config_unified import get_config

logger = logging.getLogger(__name__)


def create_model(
    base_url: str | None = None,
    model_id: str | None = None,
    api_key: str = "not-needed",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> OpenAIModel:
    """
    Create the LLM model provider for agents.

    Uses vLLM with OpenAI-compatible API by default.
    Optimized for fast, deterministic responses.
    Defaults are loaded from centralized configuration.

    Args:
        base_url: API base URL (defaults to config.vllm_api_url)
        model_id: Model ID (defaults to config.default_model_id)
        api_key: API key (defaults to "not-needed" for local vLLM)
        temperature: Sampling temperature (defaults to config.model_temperature)
        max_tokens: Maximum tokens (defaults to config.model_max_tokens)

    Returns:
        Configured OpenAIModel instance
    """
    config = get_config()
    url = base_url or config.vllm_api_url
    model = model_id or config.default_model_id
    temp = temperature if temperature is not None else config.model_temperature
    tokens = max_tokens if max_tokens is not None else config.model_max_tokens

    logger.info(f"Creating model provider: {model} at {url}")

    # Note: Must set stream=True because Strands SDK always adds stream_options
    # which vLLM rejects when stream=False
    return OpenAIModel(
        client_args={
            "base_url": url,
            "api_key": api_key,
        },
        model_id=model,
        params={
            "temperature": temp,
            "max_tokens": tokens,
            "stream": True,
        },
    )


def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list,
    model: OpenAIModel | None = None,
    hooks: list | None = None,
    hooks_factory: Callable[[], list] | None = None,
    enable_observability: bool = True,
    observability_debug: bool | None = None,
) -> Agent:
    """
    Create a Strands agent with standard configuration.

    Args:
        name: Agent name (used for identification in swarm)
        description: Brief description of agent's role
        system_prompt: The agent's system prompt
        tools: List of tools available to this agent
        model: LLM model provider (created if not provided)
        hooks: Pre-configured hooks list
        hooks_factory: Factory function to create hooks (called if hooks not provided)
        enable_observability: Add observability hooks for metrics (default: True)
        observability_debug: Enable verbose debug logging (defaults to config.enable_debug_hooks)

    Returns:
        Configured Strands Agent
    """
    agent_model = model or create_model()

    # Get hooks from factory if not provided directly
    agent_hooks = hooks
    if agent_hooks is None and hooks_factory is not None:
        agent_hooks = hooks_factory()

    # Add observability hooks if enabled
    if enable_observability:
        from core_agents.observability import create_observability_hooks

        # Use centralized config for debug flag if not explicitly specified
        config = get_config()
        debug = (
            observability_debug if observability_debug is not None else config.enable_debug_hooks
        )
        obs_hooks = create_observability_hooks(enable_debug_logging=debug)
        agent_hooks = [obs_hooks] if agent_hooks is None else list(agent_hooks) + [obs_hooks]

    return Agent(
        model=agent_model,
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=list(tools),
        hooks=agent_hooks,
    )
