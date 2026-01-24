"""
Tests for configuration loading and management.
"""


from framework.config import reload_config


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
