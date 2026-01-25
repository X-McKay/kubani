"""
Tests for configuration loading and management.
"""

import pytest

from kubani.framework.config import get_config, reload_config


class TestConfigLoading:
    """Test configuration hierarchy and loading"""

    def test_default_values_when_no_files_exist(self, isolated_config_dir, monkeypatch):
        """Config should load with defaults when no YAML files exist"""
        # Clear any cached config
        monkeypatch.setattr("framework.config._config", None)

        # Load config (no YAML files in isolated_config_dir)
        config = reload_config()

        # Should have default values
        assert config.environment == "development"
        assert config.agent_name == "kubani-agent"
        assert config.log_level == "INFO"
        assert config.llm.provider == "vllm"
        assert config.temporal.namespace == "default"

    def test_yaml_files_load_in_correct_order(
        self, isolated_config_dir, create_yaml_config, monkeypatch
    ):
        """YAML files should load: default.yaml -> {env}.yaml -> local.yaml"""
        monkeypatch.setattr("framework.config._config", None)

        # Create default.yaml
        create_yaml_config(
            "default.yaml",
            {
                "environment": "development",
                "agent_name": "from-default",
                "log_level": "INFO",
            },
        )

        # Create development.yaml (should override agent_name)
        create_yaml_config(
            "development.yaml",
            {
                "agent_name": "from-development",
                "log_level": "DEBUG",
            },
        )

        # Create local.yaml (should override log_level)
        create_yaml_config(
            "local.yaml",
            {
                "log_level": "WARNING",
            },
        )

        config = reload_config()

        # local.yaml wins for log_level
        assert config.log_level == "WARNING"
        # development.yaml wins for agent_name
        assert config.agent_name == "from-development"

    def test_environment_variables_override_yaml(
        self, isolated_config_dir, create_yaml_config, monkeypatch
    ):
        """Environment variables should override YAML config"""
        monkeypatch.setattr("framework.config._config", None)

        # Create YAML with agent_name
        create_yaml_config(
            "default.yaml",
            {
                "agent_name": "from-yaml",
                "log_level": "INFO",
            },
        )

        # Set env var
        monkeypatch.setenv("KUBANI_AGENT_NAME", "from-env")

        config = reload_config()

        # Env var should win
        assert config.agent_name == "from-env"
        # YAML value preserved where no env var
        assert config.log_level == "INFO"

    def test_nested_env_vars_with_double_underscore(self, isolated_config_dir, monkeypatch):
        """Nested config via env vars using __ delimiter"""
        monkeypatch.setattr("framework.config._config", None)

        # Set nested env vars
        monkeypatch.setenv("KUBANI_LLM__API_URL", "http://custom:9000/v1")
        monkeypatch.setenv("KUBANI_MEMORY__QDRANT__HOST", "custom-qdrant")

        config = reload_config()

        assert config.llm.api_url == "http://custom:9000/v1"
        assert config.memory.qdrant.host == "custom-qdrant"


class TestConfigValidation:
    """Test pydantic validation and error cases"""

    def test_invalid_log_level_raises_validation_error(self, isolated_config_dir, monkeypatch):
        """Invalid log level should raise ValidationError"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_LOG_LEVEL", "INVALID")

        with pytest.raises(Exception):  # Pydantic ValidationError
            reload_config()

        # Clean up for teardown
        monkeypatch.delenv("KUBANI_LOG_LEVEL", raising=False)

    def test_invalid_environment_raises_validation_error(self, isolated_config_dir, monkeypatch):
        """Invalid environment should raise ValidationError"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_ENVIRONMENT", "invalid-env")

        with pytest.raises(Exception):  # Pydantic ValidationError
            reload_config()

        # Clean up for teardown
        monkeypatch.delenv("KUBANI_ENVIRONMENT", raising=False)

    def test_invalid_port_raises_validation_error(self, isolated_config_dir, monkeypatch):
        """Invalid port number should raise ValidationError"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_MEMORY__QDRANT__PORT", "not_a_number")

        with pytest.raises(Exception):  # Pydantic ValidationError
            reload_config()

        # Clean up for teardown
        monkeypatch.delenv("KUBANI_MEMORY__QDRANT__PORT", raising=False)


class TestComputedFields:
    """Test @computed_field properties"""

    def test_temporal_grpc_url_from_host(self, isolated_config_dir, monkeypatch):
        """Temporal grpc_url should be computed from host"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_TEMPORAL__HOST", "temporal.example.com:7233")

        config = reload_config()

        assert config.temporal.grpc_url == "grpc://temporal.example.com:7233"

    def test_qdrant_url_with_https_when_use_https_true(self, isolated_config_dir, monkeypatch):
        """Qdrant URL should use https when use_https=true"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_MEMORY__QDRANT__USE_HTTPS", "true")
        monkeypatch.setenv("KUBANI_MEMORY__QDRANT__HOST", "qdrant.example.com")
        monkeypatch.setenv("KUBANI_MEMORY__QDRANT__PORT", "6333")

        config = reload_config()

        assert config.memory.qdrant.url == "https://qdrant.example.com:6333"

    def test_redis_url_includes_password_when_set(self, isolated_config_dir, monkeypatch):
        """Redis URL should include password when set"""
        monkeypatch.setattr("framework.config._config", None)
        monkeypatch.setenv("KUBANI_MEMORY__REDIS__HOST", "redis.example.com")
        monkeypatch.setenv("KUBANI_MEMORY__REDIS__PORT", "6379")
        monkeypatch.setenv("KUBANI_MEMORY__REDIS__PASSWORD", "secret123")
        monkeypatch.setenv("KUBANI_MEMORY__REDIS__DB", "0")

        config = reload_config()

        assert "secret123" in config.memory.redis.url
        assert config.memory.redis.url.startswith("redis://:secret123@")

    def test_get_mcp_servers_returns_enabled_servers(self, isolated_config_dir, monkeypatch):
        """get_mcp_servers() should return only enabled MCP servers"""
        monkeypatch.setattr("framework.config._config", None)
        # Enable only temporal and discord
        monkeypatch.setenv("KUBANI_MCP__TEMPORAL_ENABLED", "true")
        monkeypatch.setenv("KUBANI_MCP__DISCORD_ENABLED", "true")
        monkeypatch.setenv("KUBANI_MCP__QDRANT_ENABLED", "false")
        monkeypatch.setenv("KUBANI_MCP__MEMORY_ENABLED", "false")

        config = reload_config()
        servers = config.get_mcp_servers()

        # Should only have enabled servers
        assert "temporal" in servers
        assert "discord" in servers
        assert "qdrant" not in servers
        assert "memory" not in servers


class TestConfigSingleton:
    """Test get_config() and reload_config()"""

    def test_get_config_returns_same_instance(self, isolated_config_dir, monkeypatch):
        """get_config() should return the same instance"""
        monkeypatch.setattr("framework.config._config", None)

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reload_config_clears_cache(self, isolated_config_dir, create_yaml_config, monkeypatch):
        """reload_config() should create a new instance"""
        monkeypatch.setattr("framework.config._config", None)

        # Create initial config
        create_yaml_config("default.yaml", {"agent_name": "first"})
        config1 = reload_config()

        # Modify YAML
        create_yaml_config("default.yaml", {"agent_name": "second"})
        config2 = reload_config()

        # Should be new instance with new value
        assert config1 is not config2
        assert config2.agent_name == "second"
