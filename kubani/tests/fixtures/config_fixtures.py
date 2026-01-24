"""
Shared fixtures for testing configuration loading and management.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch) -> Generator[Path, None, None]:
    """
    Provides a clean, isolated config directory for testing.

    Sets KUBANI_CONFIG_DIR environment variable to point to temporary directory
    and reloads the global config singleton to ensure tests get a fresh config.

    Usage:
        def test_config_loading(isolated_config_dir):
            # Config will load from isolated_config_dir
            config = get_config()
    """
    from kubani.framework.config import reload_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("KUBANI_CONFIG_DIR", str(config_dir))

    # Clear global singleton to force reload from new directory
    reload_config()

    yield config_dir

    # Cleanup: reload config to reset state
    reload_config()


@pytest.fixture
def sample_config_yaml():
    """
    Returns a sample config structure for testing.

    Usage:
        def test_yaml_loading(isolated_config_dir, sample_config_yaml):
            yaml_file = isolated_config_dir / "default.yaml"
            with open(yaml_file, 'w') as f:
                yaml.dump(sample_config_yaml, f)
    """
    return {
        "environment": "test",
        "agent_name": "test-agent",
        "log_level": "DEBUG",
        "llm": {
            "api_url": "http://test-llm:8000/v1",
            "model": "test-model",
        },
        "memory": {
            "qdrant": {
                "host": "test-qdrant",
                "port": 6333,
            },
            "redis": {
                "host": "test-redis",
                "port": 6379,
            },
        },
        "mcp": {
            "temporal_url": "http://test-temporal:8081",
            "qdrant_url": "http://test-qdrant:8082",
        },
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Factory fixture for setting environment variables.

    Usage:
        def test_env_override(mock_env_vars):
            mock_env_vars(log_level="INFO", agent_name="test")
            # Sets KUBANI_LOG_LEVEL=INFO, KUBANI_AGENT_NAME=test
    """

    def _set(**kwargs):
        for key, value in kwargs.items():
            env_key = f"KUBANI_{key.upper()}"
            monkeypatch.setenv(env_key, str(value))

    return _set


@pytest.fixture
def create_yaml_config(isolated_config_dir):
    """
    Factory fixture for creating YAML config files.

    Usage:
        def test_loading(create_yaml_config):
            create_yaml_config("default.yaml", {"environment": "test"})
            create_yaml_config("local.yaml", {"log_level": "DEBUG"})
    """

    def _create(filename: str, content: dict):
        yaml_file = isolated_config_dir / filename
        with open(yaml_file, "w") as f:
            yaml.dump(content, f)
        return yaml_file

    return _create
