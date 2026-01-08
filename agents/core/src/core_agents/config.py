"""
Centralized Configuration Management for Kubani Agents.

This module provides a single source of truth for all configuration across
the agent ecosystem. Configuration is type-safe via Pydantic and supports:

- Environment variables (with KUBANI_ prefix)
- .env files (auto-loaded)
- Default values for development
- Validation at startup

All agents should use get_config() to access configuration:

    from core_agents.config import get_config

    config = get_config()

    # LLM settings
    model_url = config.vllm_api_url
    model_id = config.default_model_id

    # Event bus
    redis = Redis.from_url(config.redis_url)

    # Memory/skills
    qdrant_url = config.qdrant_url

Environment-Specific Configuration:
    # .env.development
    KUBANI_LOG_LEVEL=DEBUG
    KUBANI_VLLM_API_URL=http://localhost:8000/v1

    # .env.production (via Kubernetes ConfigMap/Secret)
    KUBANI_LOG_LEVEL=INFO
    KUBANI_VLLM_API_URL=http://llm-api.vllm.svc.cluster.local:8000/v1
    KUBANI_ENABLE_TRACING=true

Testing:
    @pytest.fixture
    def test_config():
        return CoreConfig(
            redis_url="redis://localhost:6379/1",
            log_level="DEBUG",
        )
"""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class LLMConfig(BaseSettings):
    """
    LLM (vLLM) configuration settings.

    These settings control the connection to the vLLM inference server
    and default model parameters.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # vLLM API connection
    vllm_api_url: str = Field(
        default="http://llm-api.vllm.svc.cluster.local:8000/v1",
        description="vLLM API endpoint URL",
    )
    default_model_id: str = Field(
        default="Qwen/Qwen3-14B-FP8",
        description="Default model identifier",
    )
    model_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Default sampling temperature",
    )
    model_max_tokens: int = Field(
        default=4096,
        ge=1,
        le=32768,
        description="Maximum tokens to generate",
    )


class EmbeddingsConfig(BaseSettings):
    """
    Embeddings model configuration settings.

    Used for semantic search in skills library and memory systems.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    embeddings_api_url: str = Field(
        default="http://embeddings-api.vllm.svc.cluster.local:8000/v1",
        description="Embeddings API endpoint URL",
    )
    embeddings_model: str = Field(
        default="Qwen/Qwen3-Embedding-0.6B",
        description="Embeddings model identifier",
    )
    embeddings_dimensions: int = Field(
        default=1024,
        ge=64,
        le=8192,
        description="Embedding vector dimensions",
    )


class EventBusConfig(BaseSettings):
    """
    Event Bus (Redis Streams) configuration settings.

    Controls the central event bus for agent communication.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://redis.database.svc.cluster.local:6379",
        description="Redis connection URL",
    )
    event_stream_name: str = Field(
        default="kubani:events",
        description="Redis stream name for events",
    )
    event_retention_hours: int = Field(
        default=168,  # 7 days
        ge=1,
        description="Event retention period in hours",
    )
    event_consumer_group: str = Field(
        default="kubani-agents",
        description="Redis consumer group name",
    )


class SkillLibraryConfig(BaseSettings):
    """
    Skill Library (Qdrant) configuration settings.

    Controls the vector database for skill semantic search.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qdrant_url: str = Field(
        default="http://qdrant.database.svc.cluster.local:6333",
        description="Qdrant server URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key (optional)",
    )
    skill_collection_name: str = Field(
        default="skills",
        description="Qdrant collection for skills",
    )
    memory_collection_name: str = Field(
        default="mem0",
        description="Qdrant collection for agent memory",
    )


class GraphMemoryConfig(BaseSettings):
    """
    Graph Memory (Neo4j) configuration settings.

    Used for relationship tracking between entities.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neo4j_url: str = Field(
        default="bolt://neo4j.database.svc.cluster.local:7687",
        description="Neo4j bolt URL",
    )
    neo4j_username: str = Field(
        default="neo4j",
        description="Neo4j username",
    )
    neo4j_password: str = Field(
        default="",
        description="Neo4j password",
    )


class ApprovalConfig(BaseSettings):
    """
    Approval System (Discord) configuration settings.

    Controls human-in-the-loop approval workflows.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_webhook_url: str | None = Field(
        default=None,
        description="Discord webhook URL for notifications",
    )
    discord_approval_webhook_url: str | None = Field(
        default=None,
        description="Discord webhook URL for approvals",
    )
    approval_timeout_seconds: int = Field(
        default=3600,  # 1 hour
        ge=60,
        description="Approval request timeout in seconds",
    )


class ObservabilityConfig(BaseSettings):
    """
    Observability configuration settings.

    Controls logging, metrics, and tracing.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Log level",
    )
    prometheus_port: int = Field(
        default=9090,
        ge=1024,
        le=65535,
        description="Prometheus metrics port",
    )
    enable_tracing: bool = Field(
        default=False,
        description="Enable distributed tracing",
    )
    enable_debug_hooks: bool = Field(
        default=False,
        description="Enable verbose debug logging in agent hooks",
    )


class TemporalConfig(BaseSettings):
    """
    Temporal workflow orchestration configuration settings.
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    temporal_url: str = Field(
        default="temporal.temporal.svc.cluster.local:7233",
        description="Temporal server URL",
    )
    temporal_namespace: str = Field(
        default="default",
        description="Temporal namespace",
    )
    temporal_task_queue_prefix: str = Field(
        default="kubani",
        description="Prefix for Temporal task queues",
    )


class CoreConfig(BaseSettings):
    """
    Core configuration for all Kubani agents.

    This is the main configuration class that composes all sub-configurations.
    Use get_config() to access the singleton instance.

    Example:
        config = get_config()
        print(config.vllm_api_url)
        print(config.redis_url)
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM Configuration ---
    vllm_api_url: str = Field(
        default="http://llm-api.vllm.svc.cluster.local:8000/v1",
        description="vLLM API endpoint URL",
    )
    default_model_id: str = Field(
        default="Qwen/Qwen3-14B-FP8",
        description="Default model identifier",
    )
    model_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Default sampling temperature",
    )
    model_max_tokens: int = Field(
        default=4096,
        ge=1,
        le=32768,
        description="Maximum tokens to generate",
    )

    # --- Embeddings Configuration ---
    embeddings_api_url: str = Field(
        default="http://embeddings-api.vllm.svc.cluster.local:8000/v1",
        description="Embeddings API endpoint URL",
    )
    embeddings_model: str = Field(
        default="Qwen/Qwen3-Embedding-0.6B",
        description="Embeddings model identifier",
    )
    embeddings_dimensions: int = Field(
        default=1024,
        ge=64,
        le=8192,
        description="Embedding vector dimensions",
    )

    # --- Event Bus (Redis) ---
    redis_url: str = Field(
        default="redis://redis.database.svc.cluster.local:6379",
        description="Redis connection URL",
    )
    event_stream_name: str = Field(
        default="kubani:events",
        description="Redis stream name for events",
    )
    event_retention_hours: int = Field(
        default=168,  # 7 days
        ge=1,
        description="Event retention period in hours",
    )
    event_consumer_group: str = Field(
        default="kubani-agents",
        description="Redis consumer group name",
    )

    # --- Skill Library (Qdrant) ---
    qdrant_url: str = Field(
        default="http://qdrant.database.svc.cluster.local:6333",
        description="Qdrant server URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key (optional)",
    )
    skill_collection_name: str = Field(
        default="skills",
        description="Qdrant collection for skills",
    )
    memory_collection_name: str = Field(
        default="mem0",
        description="Qdrant collection for agent memory",
    )

    # --- Graph Memory (Neo4j) ---
    neo4j_url: str = Field(
        default="bolt://neo4j.database.svc.cluster.local:7687",
        description="Neo4j bolt URL",
    )
    neo4j_username: str = Field(
        default="neo4j",
        description="Neo4j username",
    )
    neo4j_password: str = Field(
        default="",
        description="Neo4j password",
    )

    # --- Approval System (Discord) ---
    discord_webhook_url: str | None = Field(
        default=None,
        description="Discord webhook URL for notifications",
    )
    discord_approval_webhook_url: str | None = Field(
        default=None,
        description="Discord webhook URL for approvals",
    )
    approval_timeout_seconds: int = Field(
        default=3600,  # 1 hour
        ge=60,
        description="Approval request timeout in seconds",
    )

    # --- Observability ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Log level",
    )
    prometheus_port: int = Field(
        default=9090,
        ge=1024,
        le=65535,
        description="Prometheus metrics port",
    )
    enable_tracing: bool = Field(
        default=False,
        description="Enable distributed tracing",
    )
    enable_debug_hooks: bool = Field(
        default=False,
        description="Enable verbose debug logging in agent hooks",
    )

    # --- Temporal ---
    temporal_url: str = Field(
        default="temporal.temporal.svc.cluster.local:7233",
        description="Temporal server URL",
    )
    temporal_namespace: str = Field(
        default="default",
        description="Temporal namespace",
    )
    temporal_task_queue_prefix: str = Field(
        default="kubani",
        description="Prefix for Temporal task queues",
    )

    # --- A2A Communication ---
    a2a_default_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Default timeout for A2A calls in seconds",
    )
    a2a_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retries for A2A calls",
    )

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


# Global config instance (cached)
_config: CoreConfig | None = None


def get_config() -> CoreConfig:
    """
    Get the global configuration instance.

    Returns a cached singleton instance of CoreConfig. Configuration
    is loaded from environment variables and .env files.

    Returns:
        CoreConfig singleton instance

    Example:
        config = get_config()
        print(config.vllm_api_url)
        print(config.redis_url)
    """
    global _config
    if _config is None:
        _config = CoreConfig()
        logger.info(
            f"Loaded configuration: model={_config.default_model_id}, log_level={_config.log_level}"
        )
    return _config


def reset_config() -> None:
    """
    Reset the global configuration instance.

    Primarily used in testing to allow configuration changes between tests.
    """
    global _config
    _config = None


@lru_cache
def get_config_cached() -> CoreConfig:
    """
    Get configuration with LRU caching.

    This is an alternative to get_config() that uses functools.lru_cache
    for caching. Use this when you want immutable configuration.

    Returns:
        CoreConfig cached instance
    """
    return CoreConfig()


# Convenience functions for common configuration access patterns


def get_vllm_url() -> str:
    """Get the vLLM API URL."""
    return get_config().vllm_api_url


def get_model_id() -> str:
    """Get the default model ID."""
    return get_config().default_model_id


def get_redis_url() -> str:
    """Get the Redis URL."""
    return get_config().redis_url


def get_qdrant_url() -> str:
    """Get the Qdrant URL."""
    return get_config().qdrant_url


def get_temporal_url() -> str:
    """Get the Temporal URL."""
    return get_config().temporal_url


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return get_config().log_level == "DEBUG"
