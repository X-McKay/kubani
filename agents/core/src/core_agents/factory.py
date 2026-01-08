"""
Agent Factory for standardized agent and swarm creation.

Provides unified factory patterns for creating Strands agents and swarms
with consistent configuration, observability, and tooling.

Usage:
    from core_agents.factory import AgentFactory, AgentConfig, SwarmConfig

    # Create a single agent
    factory = AgentFactory()
    agent = factory.create_agent(AgentConfig(
        name="my-agent",
        description="My agent description",
        system_prompt="You are a helpful assistant.",
        tools=[my_tool],
    ))

    # Create a swarm
    swarm = factory.create_swarm(SwarmConfig(
        agents=[agent1, agent2, agent3],
        entry_point=agent1,
        max_handoffs=10,
    ))

    # Using centralized configuration
    from core_agents.config import get_config

    config = get_config()
    factory = AgentFactory(
        default_model_config=ModelConfig(
            base_url=config.vllm_api_url,
            model_id=config.default_model_id,
            temperature=config.model_temperature,
            max_tokens=config.model_max_tokens,
        )
    )
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from strands import Agent
from strands.models.openai import OpenAIModel
from strands.multiagent import Swarm

from core_agents.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """
    Configuration for LLM model creation.

    Attributes:
        base_url: API endpoint URL (defaults to centralized config)
        model_id: Model identifier (defaults to centralized config)
        api_key: API key (defaults to "not-needed" for local vLLM)
        temperature: Sampling temperature (0.0-1.0, lower = more deterministic)
        max_tokens: Maximum tokens to generate
        stream: Whether to stream responses (required True for vLLM + Strands)
    """

    base_url: str | None = None
    model_id: str | None = None
    api_key: str = "not-needed"
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = True

    def __post_init__(self):
        """Resolve defaults from centralized configuration."""
        config = get_config()
        if self.base_url is None:
            self.base_url = config.vllm_api_url
        if self.model_id is None:
            self.model_id = config.default_model_id
        if self.temperature is None:
            self.temperature = config.model_temperature
        if self.max_tokens is None:
            self.max_tokens = config.model_max_tokens


@dataclass
class AgentConfig:
    """
    Configuration for single agent creation.

    Attributes:
        name: Agent name (used for identification in swarm)
        description: Brief description of agent's role
        system_prompt: The agent's system prompt
        tools: List of tools available to this agent
        model_config: Model configuration (uses defaults if not provided)
        hooks: Pre-configured hooks list
        hooks_factory: Factory function to create hooks (called if hooks not provided)
        enable_observability: Add observability hooks for metrics (default: True)
        observability_debug: Enable verbose debug logging in observability hooks
        mcp_clients: List of MCP clients to add as tools
    """

    name: str
    description: str
    system_prompt: str
    tools: list[Any] = field(default_factory=list)
    model_config: ModelConfig | None = None
    hooks: list[Any] | None = None
    hooks_factory: Callable[[], list[Any]] | None = None
    enable_observability: bool = True
    observability_debug: bool = False
    mcp_clients: list[Any] = field(default_factory=list)


@dataclass
class SwarmConfig:
    """
    Configuration for swarm creation.

    Attributes:
        agents: List of agents in the swarm
        entry_point: The agent that receives initial requests
        max_handoffs: Maximum number of agent handoffs (default: 10)
        max_iterations: Total execution cap (default: 20)
        execution_timeout: Total timeout in seconds (default: 300)
        node_timeout: Per-agent turn timeout in seconds (default: 120)
        repetitive_handoff_window: Window for detecting repetitive handoffs (default: 8)
        repetitive_handoff_min_unique: Minimum unique agents in window (default: 3)
    """

    agents: list[Agent]
    entry_point: Agent
    max_handoffs: int = 10
    max_iterations: int = 20
    execution_timeout: float = 300.0
    node_timeout: float = 120.0
    repetitive_handoff_window: int = 8
    repetitive_handoff_min_unique: int = 3


class AgentFactory:
    """
    Factory for creating standardized Strands agents and swarms.

    Provides consistent agent creation with:
    - Automatic observability hooks
    - Standard model configuration
    - MCP client integration
    - Swarm guardrails

    Can be used directly or subclassed for domain-specific factories.
    """

    def __init__(
        self,
        default_model_config: ModelConfig | None = None,
        default_observability: bool = True,
    ):
        """
        Initialize the factory.

        Args:
            default_model_config: Default model config for all agents
            default_observability: Whether to enable observability by default
        """
        self._default_model_config = default_model_config or ModelConfig()
        self._default_observability = default_observability
        self._model_cache: dict[str, OpenAIModel] = {}

    def create_model(self, config: ModelConfig | None = None) -> OpenAIModel:
        """
        Create an LLM model provider.

        Args:
            config: Model configuration (uses defaults if not provided)

        Returns:
            Configured OpenAIModel instance
        """
        cfg = config or self._default_model_config

        # Create cache key
        cache_key = f"{cfg.base_url}:{cfg.model_id}:{cfg.temperature}:{cfg.max_tokens}"

        # Return cached model if available
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        logger.info(f"Creating model provider: {cfg.model_id} at {cfg.base_url}")

        model = OpenAIModel(
            client_args={
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
            },
            model_id=cfg.model_id,
            params={
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "stream": cfg.stream,
            },
        )

        self._model_cache[cache_key] = model
        return model

    def create_agent(self, config: AgentConfig) -> Agent:
        """
        Create a Strands agent with standard configuration.

        Args:
            config: Agent configuration

        Returns:
            Configured Strands Agent
        """
        # Create or use provided model
        model = self.create_model(config.model_config)

        # Build tools list (include MCP clients)
        agent_tools = list(config.tools)
        for mcp_client in config.mcp_clients:
            agent_tools.append(mcp_client)

        # Get hooks from factory if not provided directly
        agent_hooks = config.hooks
        if agent_hooks is None and config.hooks_factory is not None:
            agent_hooks = config.hooks_factory()

        # Add observability hooks if enabled
        enable_obs = config.enable_observability and self._default_observability
        if enable_obs:
            from core_agents.observability import create_observability_hooks

            obs_hooks = create_observability_hooks(
                enable_debug_logging=config.observability_debug,
            )
            agent_hooks = [obs_hooks] if agent_hooks is None else list(agent_hooks) + [obs_hooks]

        logger.debug(f"Creating agent: {config.name}")

        return Agent(
            model=model,
            name=config.name,
            description=config.description,
            system_prompt=config.system_prompt,
            tools=agent_tools,
            hooks=agent_hooks,
        )

    def create_swarm(self, config: SwarmConfig) -> Swarm:
        """
        Create a Strands swarm with standard guardrails.

        Args:
            config: Swarm configuration

        Returns:
            Configured Strands Swarm
        """
        logger.info(
            f"Creating swarm with {len(config.agents)} agents, "
            f"entry_point={config.entry_point.name}"
        )

        return Swarm(
            config.agents,
            entry_point=config.entry_point,
            max_handoffs=config.max_handoffs,
            max_iterations=config.max_iterations,
            execution_timeout=config.execution_timeout,
            node_timeout=config.node_timeout,
            repetitive_handoff_detection_window=config.repetitive_handoff_window,
            repetitive_handoff_min_unique_agents=config.repetitive_handoff_min_unique,
        )


# Singleton factory instance for convenience
_default_factory: AgentFactory | None = None


def get_agent_factory() -> AgentFactory:
    """
    Get the default agent factory singleton.

    Returns:
        AgentFactory singleton instance
    """
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory()
    return _default_factory


def create_model(config: ModelConfig | None = None) -> OpenAIModel:
    """
    Convenience function to create a model using the default factory.

    Args:
        config: Model configuration (uses defaults if not provided)

    Returns:
        Configured OpenAIModel instance
    """
    return get_agent_factory().create_model(config)


def create_agent(config: AgentConfig) -> Agent:
    """
    Convenience function to create an agent using the default factory.

    Args:
        config: Agent configuration

    Returns:
        Configured Strands Agent
    """
    return get_agent_factory().create_agent(config)


def create_swarm(config: SwarmConfig) -> Swarm:
    """
    Convenience function to create a swarm using the default factory.

    Args:
        config: Swarm configuration

    Returns:
        Configured Strands Swarm
    """
    return get_agent_factory().create_swarm(config)


# Quick agent creation for simple cases (backward compatible API)
def quick_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list[Any],
    **kwargs,
) -> Agent:
    """
    Quick agent creation with minimal configuration.

    This provides a simpler API for creating agents without needing
    to construct an AgentConfig explicitly.

    Args:
        name: Agent name
        description: Agent description
        system_prompt: System prompt
        tools: List of tools
        **kwargs: Additional AgentConfig fields

    Returns:
        Configured Strands Agent
    """
    config = AgentConfig(
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=tools,
        **kwargs,
    )
    return get_agent_factory().create_agent(config)
