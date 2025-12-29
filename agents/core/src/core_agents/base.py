"""
Shared utilities for core agents.

Provides model creation and agent configuration.
"""

import logging
import os
from collections.abc import Callable

from strands import Agent
from strands.models.openai import OpenAIModel

logger = logging.getLogger(__name__)


def create_model(
    base_url: str | None = None,
    model_id: str | None = None,
    api_key: str = "not-needed",
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> OpenAIModel:
    """
    Create the LLM model provider for agents.

    Uses vLLM with OpenAI-compatible API by default.
    Optimized for fast, deterministic responses.

    Args:
        base_url: API base URL (defaults to VLLM_API_URL env var)
        model_id: Model ID (defaults to VLLM_MODEL env var)
        api_key: API key (defaults to "not-needed" for local vLLM)
        temperature: Sampling temperature (lower = more deterministic)
        max_tokens: Maximum tokens to generate

    Returns:
        Configured OpenAIModel instance
    """
    url = base_url or os.environ.get(
        "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
    )
    model = model_id or os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

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
            "temperature": temperature,
            "max_tokens": max_tokens,
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
    observability_debug: bool = False,
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
        observability_debug: Enable verbose debug logging in observability hooks

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

        obs_hooks = create_observability_hooks(enable_debug_logging=observability_debug)
        agent_hooks = [obs_hooks] if agent_hooks is None else list(agent_hooks) + [obs_hooks]

    return Agent(
        model=agent_model,
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=list(tools),
        hooks=agent_hooks,
    )
