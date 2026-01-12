"""
Centralized Configuration Management for Kubani Agents.

This module provides backward-compatible access to the unified configuration system.
All new code should use the unified config directly:

    from core_agents.config_unified import get_config, KubaniConfig

Legacy code can continue using this module during migration:

    from core_agents.config import get_config

Configuration is loaded from multiple sources in order:
1. config.default.yaml - Base defaults
2. config.{environment}.yaml - Environment-specific
3. Environment variables (KUBANI_ prefix)
4. config.local.yaml - Local overrides (gitignored)
"""

import logging
import warnings
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Import from unified config
from core_agents.config_unified import (
    KubaniConfig,
    TemporalConfig as UnifiedTemporalConfig,
    MemoryConfig as UnifiedMemoryConfig,
    RegistryConfig as UnifiedRegistryConfig,
    DiscordConfig as UnifiedDiscordConfig,
    LLMConfig as UnifiedLLMConfig,
    EmbeddingsConfig as UnifiedEmbeddingsConfig,
    LearningConfig as UnifiedLearningConfig,
    LocalDevConfig as UnifiedLocalDevConfig,
    get_config as get_unified_config,
    reload_config,
    configure_for_local_dev,
)

logger = logging.getLogger(__name__)

# Re-export unified config classes for new code
__all__ = [
    # New unified config
    "KubaniConfig",
    "get_config",
    "reload_config",
    "configure_for_local_dev",
    # Legacy compatibility
    "CoreConfig",
    "LLMConfig",
    "EmbeddingsConfig",
    "EventBusConfig",
    "SkillLibraryConfig",
    "GraphMemoryConfig",
    "ApprovalConfig",
    "ObservabilityConfig",
    "TemporalConfig",
    "RegistryConfig",
    # Convenience functions
    "get_vllm_url",
    "get_model_id",
    "get_redis_url",
    "get_qdrant_url",
    "get_temporal_url",
    "is_debug_enabled",
    "get_registry_url",
    "is_registry_enabled",
]


# =============================================================================
# Legacy Configuration Classes (for backward compatibility)
# =============================================================================


class LLMConfig(BaseSettings):
    """Legacy LLM configuration - use KubaniConfig.llm instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    vllm_api_url: str = Field(default="http://localhost:8000/v1")
    default_model_id: str = Field(default="Qwen/Qwen3-14B")
    model_temperature: float = Field(default=0.7)
    model_max_tokens: int = Field(default=4096)


class EmbeddingsConfig(BaseSettings):
    """Legacy embeddings configuration - use KubaniConfig.embeddings instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    embeddings_api_url: str = Field(default="http://localhost:8001/v1")
    embeddings_model: str = Field(default="BAAI/bge-large-en-v1.5")
    embeddings_dimensions: int = Field(default=1024)


class EventBusConfig(BaseSettings):
    """Legacy event bus configuration - use KubaniConfig.memory instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = Field(default="redis://localhost:6379")
    event_stream_name: str = Field(default="kubani:events")
    event_retention_hours: int = Field(default=168)
    event_consumer_group: str = Field(default="kubani-agents")


class SkillLibraryConfig(BaseSettings):
    """Legacy skill library configuration - use KubaniConfig.memory instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str | None = Field(default=None)
    skill_collection_name: str = Field(default="skills")
    memory_collection_name: str = Field(default="kubani_memory")


class GraphMemoryConfig(BaseSettings):
    """Legacy graph memory configuration - use KubaniConfig.memory instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    neo4j_url: str = Field(default="bolt://localhost:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")


class ApprovalConfig(BaseSettings):
    """Legacy approval configuration - use KubaniConfig.discord instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    discord_webhook_url: str | None = Field(default=None)
    discord_approval_webhook_url: str | None = Field(default=None)
    approval_timeout_seconds: int = Field(default=3600)


class ObservabilityConfig(BaseSettings):
    """Legacy observability configuration - use KubaniConfig directly."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    prometheus_port: int = Field(default=9090)
    enable_tracing: bool = Field(default=False)
    enable_debug_hooks: bool = Field(default=False)


class TemporalConfig(BaseSettings):
    """Legacy Temporal configuration - use KubaniConfig.temporal instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    temporal_url: str = Field(default="localhost:7233")
    temporal_namespace: str = Field(default="default")
    temporal_task_queue_prefix: str = Field(default="kubani")


class RegistryConfig(BaseSettings):
    """Legacy registry configuration - use KubaniConfig.registry instead."""

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    registry_enabled: bool = Field(default=True)
    registry_url: str = Field(default="http://localhost:8000")
    registry_heartbeat_interval: float = Field(default=30.0)
    registry_retry_max_attempts: int = Field(default=5)
    registry_retry_base_delay: float = Field(default=2.0)
    registry_timeout: float = Field(default=30.0)


class CoreConfig(BaseSettings):
    """
    Legacy core configuration class.

    This class is maintained for backward compatibility. New code should use
    KubaniConfig directly via get_config().

    Migration guide:
        # Old way
        from core_agents.config import get_config
        config = get_config()
        url = config.vllm_api_url

        # New way
        from core_agents.config_unified import get_config
        config = get_config()
        url = config.llm.api_url
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        extra="ignore",
    )

    # LLM
    vllm_api_url: str = Field(default="http://localhost:8000/v1")
    default_model_id: str = Field(default="Qwen/Qwen3-14B")
    model_temperature: float = Field(default=0.7)
    model_max_tokens: int = Field(default=4096)

    # Embeddings
    embeddings_api_url: str = Field(default="http://localhost:8001/v1")
    embeddings_model: str = Field(default="BAAI/bge-large-en-v1.5")
    embeddings_dimensions: int = Field(default=1024)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379")
    event_stream_name: str = Field(default="kubani:events")
    event_retention_hours: int = Field(default=168)
    event_consumer_group: str = Field(default="kubani-agents")

    # Qdrant
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str | None = Field(default=None)
    skill_collection_name: str = Field(default="skills")
    memory_collection_name: str = Field(default="kubani_memory")

    # Neo4j
    neo4j_url: str = Field(default="bolt://localhost:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")

    # Discord
    discord_webhook_url: str | None = Field(default=None)
    discord_approval_webhook_url: str | None = Field(default=None)
    approval_timeout_seconds: int = Field(default=3600)

    # Observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    prometheus_port: int = Field(default=9090)
    enable_tracing: bool = Field(default=False)
    enable_debug_hooks: bool = Field(default=False)

    # Temporal
    temporal_url: str = Field(default="localhost:7233")
    temporal_namespace: str = Field(default="default")
    temporal_task_queue_prefix: str = Field(default="kubani")

    # A2A
    a2a_default_timeout: float = Field(default=30.0)
    a2a_max_retries: int = Field(default=3)

    # Registry
    registry_enabled: bool = Field(default=True)
    registry_url: str = Field(default="http://localhost:8000")
    registry_heartbeat_interval: float = Field(default=30.0)
    registry_retry_max_attempts: int = Field(default=5)
    registry_retry_base_delay: float = Field(default=2.0)
    registry_timeout: float = Field(default=30.0)

    def get_llm_config(self) -> LLMConfig:
        """Get LLM-specific configuration."""
        return LLMConfig(
            vllm_api_url=self.vllm_api_url,
            default_model_id=self.default_model_id,
            model_temperature=self.model_temperature,
            model_max_tokens=self.model_max_tokens,
        )

    def get_embeddings_config(self) -> EmbeddingsConfig:
        """Get embeddings-specific configuration."""
        return EmbeddingsConfig(
            embeddings_api_url=self.embeddings_api_url,
            embeddings_model=self.embeddings_model,
            embeddings_dimensions=self.embeddings_dimensions,
        )

    def get_event_bus_config(self) -> EventBusConfig:
        """Get event bus configuration."""
        return EventBusConfig(
            redis_url=self.redis_url,
            event_stream_name=self.event_stream_name,
            event_retention_hours=self.event_retention_hours,
            event_consumer_group=self.event_consumer_group,
        )

    def get_skill_library_config(self) -> SkillLibraryConfig:
        """Get skill library configuration."""
        return SkillLibraryConfig(
            qdrant_url=self.qdrant_url,
            qdrant_api_key=self.qdrant_api_key,
            skill_collection_name=self.skill_collection_name,
            memory_collection_name=self.memory_collection_name,
        )

    def get_graph_memory_config(self) -> GraphMemoryConfig:
        """Get graph memory configuration."""
        return GraphMemoryConfig(
            neo4j_url=self.neo4j_url,
            neo4j_username=self.neo4j_username,
            neo4j_password=self.neo4j_password,
        )

    def get_approval_config(self) -> ApprovalConfig:
        """Get approval system configuration."""
        return ApprovalConfig(
            discord_webhook_url=self.discord_webhook_url,
            discord_approval_webhook_url=self.discord_approval_webhook_url,
            approval_timeout_seconds=self.approval_timeout_seconds,
        )

    def get_observability_config(self) -> ObservabilityConfig:
        """Get observability configuration."""
        return ObservabilityConfig(
            log_level=self.log_level,
            prometheus_port=self.prometheus_port,
            enable_tracing=self.enable_tracing,
            enable_debug_hooks=self.enable_debug_hooks,
        )

    def get_temporal_config(self) -> TemporalConfig:
        """Get Temporal configuration."""
        return TemporalConfig(
            temporal_url=self.temporal_url,
            temporal_namespace=self.temporal_namespace,
            temporal_task_queue_prefix=self.temporal_task_queue_prefix,
        )

    def get_registry_config(self) -> RegistryConfig:
        """Get registry service configuration."""
        return RegistryConfig(
            registry_enabled=self.registry_enabled,
            registry_url=self.registry_url,
            registry_heartbeat_interval=self.registry_heartbeat_interval,
            registry_retry_max_attempts=self.registry_retry_max_attempts,
            registry_retry_base_delay=self.registry_retry_base_delay,
            registry_timeout=self.registry_timeout,
        )


# =============================================================================
# Configuration Access Functions
# =============================================================================

# Global config instance
_legacy_config: CoreConfig | None = None


def get_config() -> KubaniConfig:
    """
    Get the global configuration instance.

    Returns the unified KubaniConfig. For legacy CoreConfig access,
    use get_legacy_config() instead.

    Returns:
        KubaniConfig singleton instance
    """
    return get_unified_config()


def get_legacy_config() -> CoreConfig:
    """
    Get the legacy CoreConfig instance.

    This is provided for backward compatibility during migration.
    New code should use get_config() which returns KubaniConfig.

    Returns:
        CoreConfig singleton instance
    """
    global _legacy_config
    if _legacy_config is None:
        warnings.warn(
            "get_legacy_config() is deprecated. Use get_config() with KubaniConfig instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _legacy_config = CoreConfig()
    return _legacy_config


def reset_config() -> None:
    """Reset the global configuration instance."""
    global _legacy_config
    _legacy_config = None
    reload_config()


@lru_cache
def get_config_cached() -> KubaniConfig:
    """Get configuration with LRU caching."""
    return get_unified_config()


# =============================================================================
# Convenience Functions
# =============================================================================


def get_vllm_url() -> str:
    """Get the vLLM API URL."""
    return get_config().llm.api_url


def get_model_id() -> str:
    """Get the default model ID."""
    return get_config().llm.model


def get_redis_url() -> str:
    """Get the Redis URL."""
    cfg = get_config().memory
    return f"redis://{cfg.redis_host}:{cfg.redis_port}/{cfg.redis_db}"


def get_qdrant_url() -> str:
    """Get the Qdrant URL."""
    cfg = get_config().memory
    return f"http://{cfg.qdrant_host}:{cfg.qdrant_port}"


def get_temporal_url() -> str:
    """Get the Temporal URL."""
    return get_config().temporal.host


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return get_config().log_level == "DEBUG"


def get_registry_url() -> str:
    """Get the Registry service URL."""
    return get_config().registry.url


def is_registry_enabled() -> bool:
    """Check if registry integration is enabled."""
    return get_config().registry.sync_on_startup
