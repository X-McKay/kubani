"""
Unified Configuration Management for Kubani Agents.

Provides a hierarchical, type-safe configuration system that loads settings from
multiple sources in a defined order:
1. Base defaults (config.default.yaml)
2. Environment-specific config (config.{env}.yaml)
3. Environment variables
4. Local overrides (config.local.yaml - gitignored)

This enables seamless switching between local development and cluster deployment.
"""

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalConfig(BaseSettings):
    """Temporal workflow engine configuration."""

    host: str = Field(default="localhost:7233", description="Temporal frontend address")
    namespace: str = Field(default="default", description="Temporal namespace")
    task_queue: str = Field(default="kubani-tasks", description="Default task queue")
    enabled: bool = Field(default=True, description="Whether to use Temporal")

    model_config = SettingsConfigDict(env_prefix="TEMPORAL_")


class MemoryConfig(BaseSettings):
    """Memory and knowledge storage configuration."""

    # Qdrant for vector/semantic memory
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_collection: str = Field(default="kubani_memory", description="Default collection")

    # Neo4j for graph memory
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="", description="Neo4j password")

    # Redis for cache and pub/sub
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")

    model_config = SettingsConfigDict(env_prefix="MEMORY_")


class RegistryConfig(BaseSettings):
    """Metadata registry configuration."""

    url: str = Field(default="http://localhost:8000", description="Registry API URL")
    sync_on_startup: bool = Field(default=True, description="Sync skills on startup")
    heartbeat_interval: int = Field(default=30, description="Heartbeat interval in seconds")

    model_config = SettingsConfigDict(env_prefix="REGISTRY_")


class DiscordConfig(BaseSettings):
    """Discord integration configuration."""

    # MCP server for Discord
    mcp_url: str = Field(default="http://localhost:8080", description="Discord MCP URL")

    # Channel IDs for different purposes
    alerts_channel: str = Field(default="", description="Channel for alerts")
    digest_channel: str = Field(default="", description="Channel for news digests")
    breaking_news_channel: str = Field(default="", description="Channel for breaking news")
    learning_channel: str = Field(default="", description="Channel for learning proposals")
    approvals_channel: str = Field(default="", description="Channel for approval requests")

    # Webhook URLs (fallback)
    webhook_url: str = Field(default="", description="Default webhook URL")

    model_config = SettingsConfigDict(env_prefix="DISCORD_")


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    provider: Literal["vllm", "openai", "anthropic", "bedrock"] = Field(
        default="vllm", description="LLM provider"
    )
    api_url: str = Field(default="http://localhost:8000/v1", description="LLM API URL")
    api_key: str = Field(default="", description="API key if required")
    model: str = Field(default="Qwen/Qwen3-14B", description="Default model")
    temperature: float = Field(default=0.7, description="Default temperature")
    max_tokens: int = Field(default=4096, description="Default max tokens")

    model_config = SettingsConfigDict(env_prefix="LLM_")


class EmbeddingsConfig(BaseSettings):
    """Embeddings API configuration."""

    api_url: str = Field(default="http://localhost:8001/v1", description="Embeddings API URL")
    model: str = Field(default="BAAI/bge-large-en-v1.5", description="Embeddings model")

    model_config = SettingsConfigDict(env_prefix="EMBEDDINGS_")


class LearningConfig(BaseSettings):
    """Continuous learning system configuration."""

    enabled: bool = Field(default=True, description="Enable continuous learning")
    critic_enabled: bool = Field(default=True, description="Enable critic agent")
    reflection_enabled: bool = Field(default=True, description="Enable reflection agent")
    auto_approve_threshold: float = Field(
        default=0.95, description="Confidence threshold for auto-approval"
    )
    require_discord_approval: bool = Field(
        default=True, description="Require Discord approval for new skills"
    )
    min_examples_for_skill: int = Field(
        default=3, description="Minimum examples before proposing a skill"
    )

    model_config = SettingsConfigDict(env_prefix="LEARNING_")


class LocalDevConfig(BaseSettings):
    """Local development specific configuration."""

    tunnel_enabled: bool = Field(default=False, description="Enable cluster tunnel")
    tunnel_method: Literal["telepresence", "kubectl-forward", "none"] = Field(
        default="none", description="Tunnel method"
    )
    output_mode: Literal["console", "discord", "both"] = Field(
        default="console", description="Output mode for agent responses"
    )
    mock_services: bool = Field(default=False, description="Use mock services")

    model_config = SettingsConfigDict(env_prefix="LOCAL_")


class KubaniConfig(BaseSettings):
    """
    Main Kubani configuration.

    Aggregates all sub-configurations and handles loading from multiple sources.
    """

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )

    # Sub-configurations
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    local_dev: LocalDevConfig = Field(default_factory=LocalDevConfig)

    # Agent-specific
    agent_name: str = Field(default="kubani-agent", description="Agent name")
    agent_version: str = Field(default="0.1.0", description="Agent version")
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = SettingsConfigDict(
        env_prefix="KUBANI_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def load_yaml_configs(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Load configuration from YAML files before environment variables."""
        config_dir = Path(os.getenv("KUBANI_CONFIG_DIR", "."))

        # Load in order: defaults -> environment -> local overrides
        yaml_files = [
            config_dir / "config.default.yaml",
            config_dir / f"config.{os.getenv('KUBANI_ENVIRONMENT', 'development')}.yaml",
            config_dir / "config.local.yaml",
        ]

        merged = {}
        for yaml_file in yaml_files:
            if yaml_file.exists():
                with open(yaml_file) as f:
                    yaml_config = yaml.safe_load(f) or {}
                    merged = deep_merge(merged, yaml_config)

        # Environment variables override YAML
        return deep_merge(merged, values)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# Global configuration instance (lazy loaded)
_config: KubaniConfig | None = None


def get_config() -> KubaniConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = KubaniConfig()
    return _config


def reload_config() -> KubaniConfig:
    """Reload configuration from all sources."""
    global _config
    _config = KubaniConfig()
    return _config


def configure_for_local_dev(
    temporal: Literal["local", "cluster"] = "local",
    output: Literal["console", "discord", "both"] = "console",
    tunnel: bool = False,
) -> KubaniConfig:
    """
    Configure settings optimized for local development.

    Args:
        temporal: Whether to use local or cluster Temporal
        output: Where to send agent output
        tunnel: Whether to enable cluster tunnel

    Returns:
        Configured KubaniConfig instance
    """
    global _config

    # Set environment variables for local dev
    os.environ["KUBANI_ENVIRONMENT"] = "development"
    os.environ["LOCAL_OUTPUT_MODE"] = output
    os.environ["LOCAL_TUNNEL_ENABLED"] = str(tunnel).lower()

    if temporal == "local":
        os.environ["TEMPORAL_HOST"] = "localhost:7233"
    else:
        # Cluster Temporal - requires tunnel
        os.environ["TEMPORAL_HOST"] = "temporal-frontend.temporal.svc.cluster.local:7233"
        os.environ["LOCAL_TUNNEL_ENABLED"] = "true"

    _config = KubaniConfig()
    return _config
