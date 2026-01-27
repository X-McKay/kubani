"""
Kubani Framework.

Provides shared libraries and base classes for building agents and syndicates:

- **config**: Unified configuration system
- **mcp**: MCP client for tool access
- **events**: Event bus for inter-agent communication
- **a2a**: Agent-to-Agent protocol support
- **memory**: Hierarchical memory systems
- **learning**: Continuous learning system
- **observability**: Metrics and tracing
- **testing**: Test utilities and mocks

Usage:
    from framework import get_config
    from framework.mcp import get_mcp_client
    from framework.events import EventBus
"""

from .config import (
    DiscordConfig,
    EmbeddingsConfig,
    FeatureFlags,
    KubaniConfig,
    LearningConfig,
    LLMConfig,
    LocalDevConfig,
    MCPServerConfig,
    MemoryConfig,
    Neo4jConfig,
    ObservabilityConfig,
    QdrantConfig,
    RedisConfig,
    RegistryConfig,
    TemporalConfig,
    TracesConfig,
    configure_for_local_dev,
    get_config,
    get_discord_config,
    get_embeddings_config,
    get_learning_config,
    get_llm_config,
    get_mcp_config,
    get_memory_config,
    get_registry_config,
    get_temporal_config,
    is_local_dev,
    is_production,
    reload_config,
)
from .protocols import ConfigProtocol, LLMProtocol, SkillExecutorProtocol

__all__ = [
    # Main configuration
    "KubaniConfig",
    "get_config",
    "reload_config",
    "configure_for_local_dev",
    # Sub-configurations
    "MCPServerConfig",
    "TemporalConfig",
    "QdrantConfig",
    "Neo4jConfig",
    "RedisConfig",
    "MemoryConfig",
    "LLMConfig",
    "EmbeddingsConfig",
    "DiscordConfig",
    "RegistryConfig",
    "LearningConfig",
    "ObservabilityConfig",
    "LocalDevConfig",
    "TracesConfig",
    "FeatureFlags",
    # Convenience functions
    "get_llm_config",
    "get_memory_config",
    "get_temporal_config",
    "get_discord_config",
    "get_mcp_config",
    "get_registry_config",
    "get_learning_config",
    "get_embeddings_config",
    "is_production",
    "is_local_dev",
    # Protocols for testing
    "LLMProtocol",
    "SkillExecutorProtocol",
    "ConfigProtocol",
]
