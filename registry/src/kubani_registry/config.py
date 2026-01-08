"""Configuration management for the registry service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Registry service configuration."""

    model_config = SettingsConfigDict(
        env_prefix="REGISTRY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://kubani:kubani@localhost:5432/kubani_registry",  # pragma: allowlist secret
        description="PostgreSQL connection URL",
    )
    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL for caching and heartbeats",
    )

    # Server
    host: str = Field(
        default="0.0.0.0",
        description="Server host",
    )
    port: int = Field(
        default=8000,
        description="Server port",
    )

    # Heartbeat
    heartbeat_timeout_seconds: int = Field(
        default=90,
        description="Seconds before agent is marked unhealthy",
    )
    heartbeat_check_interval: int = Field(
        default=30,
        description="Seconds between heartbeat checks",
    )

    # Health checking
    health_check_interval: int = Field(
        default=60,
        description="Seconds between endpoint health checks",
    )
    health_check_timeout: int = Field(
        default=10,
        description="Timeout for health check requests",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Log level",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
