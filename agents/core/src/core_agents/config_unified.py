"""
Unified Configuration Management for Kubani Agents.

Provides a hierarchical, type-safe configuration system using pydantic-settings
that loads settings from multiple sources in a defined order:

1. Default values (defined in model fields)
2. Base YAML config (config/default.yaml)
3. Environment-specific YAML config (config/{env}.yaml)
4. Environment variables (with KUBANI_ prefix)
5. Local overrides YAML (config/local.yaml - gitignored)

This enables seamless switching between local development and cluster deployment.

Usage:
    from core_agents.config_unified import get_config

    config = get_config()
    print(config.llm.api_url)
    print(config.memory.qdrant_url)
    print(config.mcp.temporal_url)
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# =============================================================================
# MCP Server Configuration
# =============================================================================


class MCPServerConfig(BaseSettings):
    """Configuration for MCP server connections."""

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        extra="ignore",
    )

    # Temporal MCP
    temporal_url: str = Field(
        default="http://localhost:8081",
        description="Temporal MCP server URL",
    )
    temporal_enabled: bool = Field(
        default=True,
        description="Enable Temporal MCP server",
    )

    # Qdrant MCP
    qdrant_url: str = Field(
        default="http://localhost:8082",
        description="Qdrant MCP server URL",
    )
    qdrant_enabled: bool = Field(
        default=True,
        description="Enable Qdrant MCP server",
    )

    # Memory MCP (unified memory interface)
    memory_url: str = Field(
        default="http://localhost:8083",
        description="Memory MCP server URL",
    )
    memory_enabled: bool = Field(
        default=True,
        description="Enable Memory MCP server",
    )

    # Discord MCP
    discord_url: str = Field(
        default="http://localhost:8084",
        description="Discord MCP server URL",
    )
    discord_enabled: bool = Field(
        default=True,
        description="Enable Discord MCP server",
    )

    # Registry MCP
    registry_url: str = Field(
        default="http://localhost:8085",
        description="Registry MCP server URL",
    )
    registry_enabled: bool = Field(
        default=True,
        description="Enable Registry MCP server",
    )


# =============================================================================
# Service Configuration (Backend Services)
# =============================================================================


class TemporalConfig(BaseSettings):
    """Temporal workflow engine configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TEMPORAL_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(
        default="localhost:7233",
        description="Temporal frontend gRPC address",
    )
    namespace: str = Field(
        default="default",
        description="Temporal namespace",
    )
    task_queue: str = Field(
        default="kubani-tasks",
        description="Default task queue name",
    )
    enabled: bool = Field(
        default=True,
        description="Whether to use Temporal for workflow orchestration",
    )
    ui_url: str = Field(
        default="http://localhost:8080",
        description="Temporal UI URL for debugging",
    )

    @computed_field
    @property
    def grpc_url(self) -> str:
        """Get the full gRPC URL."""
        return f"grpc://{self.host}"


class QdrantConfig(BaseSettings):
    """Qdrant vector database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="Qdrant host")
    port: int = Field(default=6333, description="Qdrant HTTP port")
    grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    api_key: SecretStr | None = Field(default=None, description="Qdrant API key")
    prefer_grpc: bool = Field(default=True, description="Prefer gRPC over HTTP")
    use_https: bool = Field(default=False, description="Use HTTPS for connections")

    # Collection names
    skills_collection: str = Field(default="skills", description="Skills collection")
    memory_collection: str = Field(default="kubani_memory", description="Memory collection")
    learnings_collection: str = Field(default="learnings", description="Learnings collection")

    @computed_field
    @property
    def url(self) -> str:
        """Get the HTTP URL."""
        scheme = "https" if self.use_https or self.port == 443 else "http"
        return f"{scheme}://{self.host}:{self.port}"

    @computed_field
    @property
    def grpc_url(self) -> str:
        """Get the gRPC URL."""
        return f"{self.host}:{self.grpc_port}"


class Neo4jConfig(BaseSettings):
    """Neo4j graph database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        env_file=".env",
        extra="ignore",
    )

    uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j bolt URI",
    )
    user: str = Field(default="neo4j", description="Neo4j username")
    password: SecretStr = Field(default=SecretStr(""), description="Neo4j password")
    database: str = Field(default="neo4j", description="Neo4j database name")


class RedisConfig(BaseSettings):
    """Redis cache and pub/sub configuration."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: SecretStr | None = Field(default=None, description="Redis password")

    # Stream configuration
    event_stream: str = Field(default="kubani:events", description="Event stream name")
    consumer_group: str = Field(default="kubani-agents", description="Consumer group")

    @computed_field
    @property
    def url(self) -> str:
        """Get the Redis URL."""
        if self.password:
            return f"redis://:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class MemoryConfig(BaseSettings):
    """Unified memory configuration combining all memory backends."""

    model_config = SettingsConfigDict(
        env_prefix="MEMORY_",
        env_file=".env",
        extra="ignore",
    )

    # Sub-configurations
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)

    # Memory settings
    default_ttl_days: int = Field(default=90, description="Default TTL for memories")
    consolidation_threshold: int = Field(
        default=100,
        description="Number of similar memories before consolidation",
    )


# =============================================================================
# LLM Configuration
# =============================================================================


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        extra="ignore",
    )

    provider: Literal["vllm", "openai", "anthropic", "bedrock"] = Field(
        default="vllm",
        description="LLM provider type",
    )
    api_url: str = Field(
        default="http://localhost:8000/v1",
        description="LLM API base URL",
    )
    api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key for authentication",
    )
    model: str = Field(
        default="nvidia/Qwen3-14B-FP4",
        description="Default model identifier",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Default sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        le=128000,
        description="Maximum tokens to generate",
    )
    timeout: float = Field(
        default=120.0,
        description="Request timeout in seconds",
    )


class EmbeddingsConfig(BaseSettings):
    """Embeddings API configuration."""

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDINGS_",
        env_file=".env",
        extra="ignore",
    )

    api_url: str = Field(
        default="http://localhost:8001/v1",
        description="Embeddings API base URL",
    )
    model: str = Field(
        default="BAAI/bge-large-en-v1.5",
        description="Embeddings model identifier",
    )
    dimensions: int = Field(
        default=1024,
        description="Embedding vector dimensions",
    )
    batch_size: int = Field(
        default=32,
        description="Batch size for embedding requests",
    )

    # Known model dimensions for auto-detection
    KNOWN_DIMENSIONS: dict[str, int] = {
        "Qwen/Qwen3-Embedding-0.6B": 1024,
        "Qwen/Qwen3-Embedding-4B": 2560,
        "Qwen/Qwen3-Embedding-8B": 4096,
        "BAAI/bge-large-en-v1.5": 1024,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-small-en-v1.5": 384,
    }

    def get_dimensions_for_model(self, model: str | None = None) -> int:
        """Get dimensions for a model, with auto-detection for known models."""
        model_name = model or self.model
        return self.KNOWN_DIMENSIONS.get(model_name, self.dimensions)


# =============================================================================
# Discord Configuration
# =============================================================================


class DiscordConfig(BaseSettings):
    """Discord integration configuration."""

    model_config = SettingsConfigDict(
        env_prefix="DISCORD_",
        env_file=".env",
        extra="ignore",
    )

    bot_token: SecretStr = Field(
        default=SecretStr(""),
        description="Discord bot token",
    )

    # Channel IDs for different purposes
    alerts_channel: str = Field(default="", description="Channel for alerts")
    digest_channel: str = Field(default="", description="Channel for news digests")
    breaking_news_channel: str = Field(default="", description="Channel for breaking news")
    learning_channel: str = Field(default="", description="Channel for learning proposals")
    approvals_channel: str = Field(default="", description="Channel for approval requests")
    evaluations_channel: str = Field(default="", description="Channel for evaluation results")
    general_channel: str = Field(default="", description="General discussion channel")

    # Guild configuration
    guild_id: str = Field(default="", description="Discord server/guild ID")

    # Webhook URLs (alternative to bot)
    alerts_webhook: str = Field(default="", description="Webhook URL for alerts")
    news_webhook: str = Field(default="", description="Webhook URL for news")


# =============================================================================
# Registry Configuration
# =============================================================================


class RegistryConfig(BaseSettings):
    """Registry service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="REGISTRY_",
        env_file=".env",
        extra="ignore",
    )

    url: str = Field(
        default="http://localhost:8000",
        description="Registry service URL",
    )
    enabled: bool = Field(
        default=True,
        description="Enable registry integration",
    )
    heartbeat_interval: float = Field(
        default=30.0,
        description="Heartbeat interval in seconds",
    )
    heartbeat_timeout: int = Field(
        default=90,
        description="Seconds before agent is marked unhealthy",
    )
    retry_max_attempts: int = Field(
        default=5,
        description="Maximum retry attempts for registration",
    )
    retry_base_delay: float = Field(
        default=1.0,
        description="Base delay for exponential backoff",
    )
    timeout: float = Field(
        default=10.0,
        description="Request timeout in seconds",
    )

    # Database (for registry service itself)
    database_url: str = Field(
        default="postgresql://kubani:kubani@localhost:5432/kubani_registry",  # pragma: allowlist secret
        description="PostgreSQL connection URL",
    )
    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements",
    )


# =============================================================================
# Learning Configuration
# =============================================================================


class LearningConfig(BaseSettings):
    """Continuous learning system configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LEARNING_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(
        default=True,
        description="Enable continuous learning",
    )

    # Critic agent settings
    critic_interval_hours: int = Field(
        default=1,
        description="Hours between critic evaluations",
    )
    critic_min_interactions: int = Field(
        default=10,
        description="Minimum interactions before critique",
    )

    # Reflection settings
    reflection_interval_hours: int = Field(
        default=6,
        description="Hours between reflection cycles",
    )
    reflection_min_learnings: int = Field(
        default=5,
        description="Minimum learnings before reflection",
    )

    # Skill synthesis settings
    synthesis_confidence_threshold: float = Field(
        default=0.8,
        description="Minimum confidence for skill synthesis",
    )
    synthesis_min_examples: int = Field(
        default=3,
        description="Minimum examples before synthesis",
    )

    # Approval settings
    approval_timeout_hours: int = Field(
        default=72,
        description="Hours before approval times out",
    )
    auto_approve_threshold: float = Field(
        default=0.95,
        description="Confidence threshold for auto-approval",
    )


# =============================================================================
# Observability Configuration
# =============================================================================


class ObservabilityConfig(BaseSettings):
    """Observability and monitoring configuration."""

    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY_",
        env_file=".env",
        extra="ignore",
    )

    tracing_enabled: bool = Field(
        default=True,
        description="Enable distributed tracing",
    )
    metrics_enabled: bool = Field(
        default=True,
        description="Enable metrics collection",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP tracing endpoint",
    )
    debug_hooks: bool = Field(
        default=False,
        description="Enable verbose debug logging in agent hooks",
    )


# =============================================================================
# Local Development Configuration
# =============================================================================


class LocalDevConfig(BaseSettings):
    """Local development configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LOCAL_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(
        default=False,
        description="Enable local development mode",
    )
    output_mode: Literal["console", "discord", "both"] = Field(
        default="console",
        description="Where to send agent output",
    )
    tunnel_enabled: bool = Field(
        default=False,
        description="Enable cluster service tunneling",
    )
    mock_services: bool = Field(
        default=False,
        description="Use mock services instead of real ones",
    )
    hot_reload: bool = Field(
        default=True,
        description="Enable hot-reload on file changes",
    )
    auto_eval: bool = Field(
        default=True,
        description="Run evaluations automatically on changes",
    )
    eval_subset: str = Field(
        default="smoke",
        description="Which test suite to run automatically",
    )


# =============================================================================
# Main Configuration Class
# =============================================================================


class KubaniConfig(BaseSettings):
    """
    Main Kubani configuration.

    Aggregates all sub-configurations and handles loading from multiple sources.
    Configuration is loaded in this order (later sources override earlier):

    1. Default values defined in field definitions
    2. config/default.yaml
    3. config/{environment}.yaml
    4. Environment variables (KUBANI_ prefix, nested with __)
    5. config/local.yaml (gitignored)

    Example:
        config = get_config()
        print(config.llm.api_url)
        print(config.memory.qdrant.url)
        print(config.mcp.temporal_url)
    """

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Deployment environment",
    )

    # Agent identity
    agent_name: str = Field(
        default="kubani-agent",
        description="Agent name for registration",
    )
    agent_version: str = Field(
        default="0.1.0",
        description="Agent version",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_format: Literal["json", "text"] = Field(
        default="text",
        description="Log output format",
    )

    # MCP Servers
    mcp: MCPServerConfig = Field(default_factory=MCPServerConfig)

    # Backend Services
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # AI/ML
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)

    # Integrations
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)

    # Features
    learning: LearningConfig = Field(default_factory=LearningConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # Development
    local_dev: LocalDevConfig = Field(default_factory=LocalDevConfig)

    @model_validator(mode="before")
    @classmethod
    def load_yaml_configs(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Load configuration from YAML files before environment variables."""
        config_dir = Path(os.getenv("KUBANI_CONFIG_DIR", "config"))
        environment = os.getenv("KUBANI_ENVIRONMENT", "development")

        # Load in order: defaults -> environment -> local overrides
        yaml_files = [
            config_dir / "default.yaml",
            config_dir / f"{environment}.yaml",
            config_dir / "local.yaml",
        ]

        merged: dict[str, Any] = {}
        for yaml_file in yaml_files:
            if yaml_file.exists():
                try:
                    with open(yaml_file) as f:
                        yaml_config = yaml.safe_load(f) or {}
                        merged = deep_merge(merged, yaml_config)
                        logger.debug(f"Loaded config from {yaml_file}")
                except Exception as e:
                    logger.warning(f"Failed to load {yaml_file}: {e}")

        # Environment variables and explicit values override YAML
        return deep_merge(merged, values)

    def get_mcp_servers(self) -> dict[str, str]:
        """Get a mapping of enabled MCP servers to their URLs."""
        servers = {}
        if self.mcp.temporal_enabled:
            servers["temporal"] = self.mcp.temporal_url
        if self.mcp.qdrant_enabled:
            servers["qdrant"] = self.mcp.qdrant_url
        if self.mcp.memory_enabled:
            servers["memory"] = self.mcp.memory_url
        if self.mcp.discord_enabled:
            servers["discord"] = self.mcp.discord_url
        if self.mcp.registry_enabled:
            servers["registry"] = self.mcp.registry_url
        return servers

    def get_mem0_config(self, collection_name: str = "mem0") -> dict[str, Any]:
        """
        Get mem0-compatible configuration from unified config.

        This provides a bridge to the mem0 library configuration format,
        using the unified config values.

        Args:
            collection_name: Qdrant collection name for mem0

        Returns:
            Dict configuration suitable for Memory.from_config()
        """
        qdrant_config: dict[str, Any] = {
            "url": self.memory.qdrant.url,
            "collection_name": collection_name,
            "embedding_model_dims": self.embeddings.get_dimensions_for_model(),
        }
        if self.memory.qdrant.api_key:
            qdrant_config["api_key"] = self.memory.qdrant.api_key.get_secret_value()

        return {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": self.llm.model,
                    "api_key": self.llm.api_key.get_secret_value() or "not-needed",
                    "openai_base_url": self.llm.api_url,
                    "temperature": 0.1,
                },
            },
            "embedder": {
                "provider": "lmstudio",
                "config": {
                    "model": self.embeddings.model,
                    "embedding_dims": self.embeddings.get_dimensions_for_model(),
                    "lmstudio_base_url": self.embeddings.api_url,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": qdrant_config,
            },
            "version": "v1.1",
        }

    def get_graph_mem0_config(self, collection_name: str = "mem0") -> dict[str, Any]:
        """
        Get mem0-compatible configuration with Neo4j graph store.

        Args:
            collection_name: Qdrant collection name for mem0

        Returns:
            Dict configuration suitable for Memory.from_config() with graph memory
        """
        config = self.get_mem0_config(collection_name)
        config["graph_store"] = {
            "provider": "neo4j",
            "config": {
                "url": self.memory.neo4j.uri,
                "username": self.memory.neo4j.user,
                "password": self.memory.neo4j.password.get_secret_value(),
            },
        }
        return config


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# =============================================================================
# Configuration Access Functions
# =============================================================================

# Global configuration instance (lazy loaded)
_config: KubaniConfig | None = None


def get_config() -> KubaniConfig:
    """
    Get the global configuration instance.

    Returns a singleton instance of KubaniConfig. Configuration is loaded
    from YAML files and environment variables on first access.

    Returns:
        KubaniConfig singleton instance
    """
    global _config
    if _config is None:
        _config = KubaniConfig()
        logger.info(
            f"Loaded configuration: env={_config.environment}, "
            f"agent={_config.agent_name}, log_level={_config.log_level}"
        )
    return _config


@lru_cache(maxsize=1)
def get_config_cached() -> KubaniConfig:
    """Get configuration with LRU caching (immutable)."""
    return KubaniConfig()


def reload_config() -> KubaniConfig:
    """
    Reload configuration from all sources.

    Clears the cached configuration and reloads from YAML files
    and environment variables.

    Returns:
        Fresh KubaniConfig instance
    """
    global _config
    get_config_cached.cache_clear()
    _config = KubaniConfig()
    logger.info("Configuration reloaded")
    return _config


def configure_for_local_dev(
    temporal: Literal["local", "cluster"] = "local",
    output: Literal["console", "discord", "both"] = "console",
    tunnel: bool = False,
    mock_services: bool = False,
) -> KubaniConfig:
    """
    Configure settings optimized for local development.

    Sets environment variables and reloads configuration for local
    development with the specified options.

    Args:
        temporal: Whether to use local or cluster Temporal
        output: Where to send agent output
        tunnel: Whether to enable cluster tunnel
        mock_services: Whether to use mock services

    Returns:
        Configured KubaniConfig instance
    """
    # Set environment variables for local dev
    os.environ["KUBANI_ENVIRONMENT"] = "development"
    os.environ["LOCAL_ENABLED"] = "true"
    os.environ["LOCAL_OUTPUT_MODE"] = output
    os.environ["LOCAL_TUNNEL_ENABLED"] = str(tunnel).lower()
    os.environ["LOCAL_MOCK_SERVICES"] = str(mock_services).lower()

    if temporal == "local":
        os.environ["TEMPORAL_HOST"] = "localhost:7233"
    else:
        # Cluster Temporal - requires tunnel or Tailscale
        os.environ["TEMPORAL_HOST"] = "temporal.almckay.io:7233"
        if not tunnel:
            logger.warning("Cluster Temporal selected but tunnel not enabled")

    return reload_config()


# =============================================================================
# Convenience Functions
# =============================================================================


def get_llm_config() -> LLMConfig:
    """Get LLM configuration."""
    return get_config().llm


def get_memory_config() -> MemoryConfig:
    """Get memory configuration."""
    return get_config().memory


def get_temporal_config() -> TemporalConfig:
    """Get Temporal configuration."""
    return get_config().temporal


def get_discord_config() -> DiscordConfig:
    """Get Discord configuration."""
    return get_config().discord


def get_mcp_config() -> MCPServerConfig:
    """Get MCP server configuration."""
    return get_config().mcp


def get_registry_config() -> RegistryConfig:
    """Get registry configuration."""
    return get_config().registry


def get_learning_config() -> LearningConfig:
    """Get learning configuration."""
    return get_config().learning


def get_embeddings_config() -> EmbeddingsConfig:
    """Get embeddings configuration."""
    return get_config().embeddings


def is_production() -> bool:
    """Check if running in production environment."""
    return get_config().environment == "production"


def is_local_dev() -> bool:
    """Check if running in local development mode."""
    return get_config().local_dev.enabled
