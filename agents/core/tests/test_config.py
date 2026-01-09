"""
Tests for centralized configuration management.

Tests the CoreConfig class and related utilities:
- Default values
- Environment variable loading
- Configuration caching
- Sub-configuration extraction
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from core_agents.config import (
    ApprovalConfig,
    CoreConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphMemoryConfig,
    LLMConfig,
    ObservabilityConfig,
    SkillLibraryConfig,
    TemporalConfig,
    get_config,
    get_model_id,
    get_qdrant_url,
    get_redis_url,
    get_temporal_url,
    get_vllm_url,
    is_debug_enabled,
    reset_config,
)


class TestCoreConfigDefaults:
    """Test default configuration values."""

    def setup_method(self):
        """Clear config cache and relevant env vars before each test."""
        reset_config()
        # Store original env vars to restore later
        self._orig_env = {}
        # Clear both legacy and KUBANI_ prefixed env vars
        env_vars_to_clear = [
            "VLLM_API_URL",
            "VLLM_MODEL",
            "EMBEDDINGS_API_URL",
            "REDIS_URL",
            "QDRANT_URL",
            "NEO4J_URL",
            "TEMPORAL_URL",
            "KUBANI_VLLM_API_URL",
            "KUBANI_DEFAULT_MODEL_ID",
            "KUBANI_EMBEDDINGS_API_URL",
            "KUBANI_REDIS_URL",
            "KUBANI_QDRANT_URL",
            "KUBANI_NEO4J_URL",
            "KUBANI_TEMPORAL_URL",
            "KUBANI_LOG_LEVEL",
            "KUBANI_ENABLE_DEBUG_HOOKS",
        ]
        for var in env_vars_to_clear:
            if var in os.environ:
                self._orig_env[var] = os.environ.pop(var)
        reset_config()  # Reset again after clearing env vars

    def teardown_method(self):
        """Restore original env vars."""
        reset_config()
        for var, value in self._orig_env.items():
            os.environ[var] = value

    def test_llm_defaults(self):
        """LLM configuration has sensible defaults."""
        config = CoreConfig()

        # Check for sensible defaults (cluster service URLs)
        assert "llm" in config.vllm_api_url.lower() or "8000" in config.vllm_api_url
        assert "Qwen" in config.default_model_id
        assert 0.0 <= config.model_temperature <= 1.0
        assert config.model_max_tokens > 0

    def test_embeddings_defaults(self):
        """Embeddings configuration has sensible defaults."""
        config = CoreConfig()

        assert "embeddings" in config.embeddings_api_url
        assert "Embedding" in config.embeddings_model
        assert 64 <= config.embeddings_dimensions <= 8192

    def test_event_bus_defaults(self):
        """Event bus configuration has sensible defaults."""
        config = CoreConfig()

        assert "redis" in config.redis_url
        assert "kubani" in config.event_stream_name
        assert config.event_retention_hours >= 1

    def test_skill_library_defaults(self):
        """Skill library configuration has sensible defaults."""
        config = CoreConfig()

        assert "qdrant" in config.qdrant_url
        assert config.skill_collection_name == "skills"
        assert config.memory_collection_name == "mem0"

    def test_graph_memory_defaults(self):
        """Graph memory configuration has sensible defaults."""
        config = CoreConfig()

        assert "neo4j" in config.neo4j_url
        assert config.neo4j_username == "neo4j"

    def test_approval_defaults(self):
        """Approval configuration has sensible defaults."""
        config = CoreConfig()

        assert config.discord_webhook_url is None  # Optional
        assert config.approval_timeout_seconds >= 60

    def test_observability_defaults(self):
        """Observability configuration has sensible defaults."""
        config = CoreConfig()

        assert config.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert 1024 <= config.prometheus_port <= 65535
        assert config.enable_tracing is False  # Default off

    def test_temporal_defaults(self):
        """Temporal configuration has sensible defaults."""
        config = CoreConfig()

        assert "temporal" in config.temporal_url
        assert config.temporal_namespace == "default"

    def test_a2a_defaults(self):
        """A2A configuration has sensible defaults."""
        config = CoreConfig()

        assert config.a2a_default_timeout > 0
        assert config.a2a_max_retries >= 0


class TestCoreConfigEnvironment:
    """Test configuration loading from environment variables."""

    def test_vllm_url_from_env(self):
        """KUBANI_VLLM_API_URL overrides default."""
        with patch.dict(os.environ, {"KUBANI_VLLM_API_URL": "http://localhost:8000/v1"}):
            config = CoreConfig()
            assert config.vllm_api_url == "http://localhost:8000/v1"

    def test_model_id_from_env(self):
        """KUBANI_DEFAULT_MODEL_ID overrides default."""
        with patch.dict(os.environ, {"KUBANI_DEFAULT_MODEL_ID": "gpt-4"}):
            config = CoreConfig()
            assert config.default_model_id == "gpt-4"

    def test_redis_url_from_env(self):
        """KUBANI_REDIS_URL overrides default."""
        with patch.dict(os.environ, {"KUBANI_REDIS_URL": "redis://localhost:6379/1"}):
            config = CoreConfig()
            assert config.redis_url == "redis://localhost:6379/1"

    def test_log_level_from_env(self):
        """KUBANI_LOG_LEVEL overrides default."""
        with patch.dict(os.environ, {"KUBANI_LOG_LEVEL": "DEBUG"}):
            config = CoreConfig()
            assert config.log_level == "DEBUG"

    def test_enable_tracing_from_env(self):
        """KUBANI_ENABLE_TRACING overrides default."""
        with patch.dict(os.environ, {"KUBANI_ENABLE_TRACING": "true"}):
            config = CoreConfig()
            assert config.enable_tracing is True


class TestCoreConfigValidation:
    """Test configuration validation."""

    def test_temperature_validation(self):
        """Temperature must be between 0.0 and 2.0."""
        with pytest.raises(ValueError):
            CoreConfig(model_temperature=-0.1)

        with pytest.raises(ValueError):
            CoreConfig(model_temperature=2.1)

        # Valid values should work
        config = CoreConfig(model_temperature=0.0)
        assert config.model_temperature == 0.0

        config = CoreConfig(model_temperature=2.0)
        assert config.model_temperature == 2.0

    def test_max_tokens_validation(self):
        """Max tokens must be positive."""
        with pytest.raises(ValueError):
            CoreConfig(model_max_tokens=0)

        config = CoreConfig(model_max_tokens=1)
        assert config.model_max_tokens == 1

    def test_log_level_validation(self):
        """Log level must be a valid level."""
        with pytest.raises(ValueError):
            CoreConfig(log_level="INVALID")

        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = CoreConfig(log_level=level)
            assert config.log_level == level


class TestSubConfigurations:
    """Test extraction of sub-configurations."""

    @pytest.fixture
    def core_config(self):
        return CoreConfig()

    def test_get_llm_config(self, core_config):
        """LLM sub-config extracts correct fields."""
        llm_config = core_config.get_llm_config()

        assert isinstance(llm_config, LLMConfig)
        assert llm_config.vllm_api_url == core_config.vllm_api_url
        assert llm_config.default_model_id == core_config.default_model_id
        assert llm_config.model_temperature == core_config.model_temperature
        assert llm_config.model_max_tokens == core_config.model_max_tokens

    def test_get_embeddings_config(self, core_config):
        """Embeddings sub-config extracts correct fields."""
        emb_config = core_config.get_embeddings_config()

        assert isinstance(emb_config, EmbeddingsConfig)
        assert emb_config.embeddings_api_url == core_config.embeddings_api_url
        assert emb_config.embeddings_model == core_config.embeddings_model
        assert emb_config.embeddings_dimensions == core_config.embeddings_dimensions

    def test_get_event_bus_config(self, core_config):
        """Event bus sub-config extracts correct fields."""
        bus_config = core_config.get_event_bus_config()

        assert isinstance(bus_config, EventBusConfig)
        assert bus_config.redis_url == core_config.redis_url
        assert bus_config.event_stream_name == core_config.event_stream_name

    def test_get_skill_library_config(self, core_config):
        """Skill library sub-config extracts correct fields."""
        skill_config = core_config.get_skill_library_config()

        assert isinstance(skill_config, SkillLibraryConfig)
        assert skill_config.qdrant_url == core_config.qdrant_url
        assert skill_config.skill_collection_name == core_config.skill_collection_name

    def test_get_graph_memory_config(self, core_config):
        """Graph memory sub-config extracts correct fields."""
        graph_config = core_config.get_graph_memory_config()

        assert isinstance(graph_config, GraphMemoryConfig)
        assert graph_config.neo4j_url == core_config.neo4j_url
        assert graph_config.neo4j_username == core_config.neo4j_username

    def test_get_approval_config(self, core_config):
        """Approval sub-config extracts correct fields."""
        approval_config = core_config.get_approval_config()

        assert isinstance(approval_config, ApprovalConfig)
        assert approval_config.discord_webhook_url == core_config.discord_webhook_url
        assert approval_config.approval_timeout_seconds == core_config.approval_timeout_seconds

    def test_get_observability_config(self, core_config):
        """Observability sub-config extracts correct fields."""
        obs_config = core_config.get_observability_config()

        assert isinstance(obs_config, ObservabilityConfig)
        assert obs_config.log_level == core_config.log_level
        assert obs_config.prometheus_port == core_config.prometheus_port
        assert obs_config.enable_tracing == core_config.enable_tracing

    def test_get_temporal_config(self, core_config):
        """Temporal sub-config extracts correct fields."""
        temp_config = core_config.get_temporal_config()

        assert isinstance(temp_config, TemporalConfig)
        assert temp_config.temporal_url == core_config.temporal_url
        assert temp_config.temporal_namespace == core_config.temporal_namespace


class TestConfigSingleton:
    """Test configuration singleton pattern."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_get_config_returns_same_instance(self):
        """get_config() returns the same instance on multiple calls."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reset_config_clears_singleton(self):
        """reset_config() clears the singleton."""
        config1 = get_config()
        reset_config()
        config2 = get_config()

        # New instance created
        assert config1 is not config2


class TestConvenienceFunctions:
    """Test convenience functions for common config access."""

    def setup_method(self):
        """Reset config, clear env vars, and change to temp dir to avoid .env loading."""
        reset_config()
        # Store original working directory
        self._orig_cwd = os.getcwd()
        # Store original env vars to restore later
        self._orig_env = {}
        # Clear both legacy and KUBANI_ prefixed env vars
        env_vars_to_clear = [
            "VLLM_API_URL",
            "VLLM_MODEL",
            "EMBEDDINGS_API_URL",
            "REDIS_URL",
            "QDRANT_URL",
            "NEO4J_URL",
            "TEMPORAL_URL",
            "KUBANI_VLLM_API_URL",
            "KUBANI_DEFAULT_MODEL_ID",
            "KUBANI_EMBEDDINGS_API_URL",
            "KUBANI_REDIS_URL",
            "KUBANI_QDRANT_URL",
            "KUBANI_NEO4J_URL",
            "KUBANI_TEMPORAL_URL",
            "KUBANI_LOG_LEVEL",
            "KUBANI_ENABLE_DEBUG_HOOKS",
        ]
        for var in env_vars_to_clear:
            if var in os.environ:
                self._orig_env[var] = os.environ.pop(var)
        # Change to temp directory to prevent .env file loading
        self._temp_dir = tempfile.mkdtemp()
        os.chdir(self._temp_dir)
        reset_config()  # Reset again after clearing env vars and changing dir

    def teardown_method(self):
        os.chdir(self._orig_cwd)
        reset_config()
        for var, value in self._orig_env.items():
            os.environ[var] = value

    def test_get_vllm_url(self):
        """get_vllm_url returns correct value."""
        url = get_vllm_url()
        # Check for sensible LLM URL (cluster or localhost)
        assert "llm" in url.lower() or "8000" in url

    def test_get_model_id(self):
        """get_model_id returns correct value."""
        model_id = get_model_id()
        assert "Qwen" in model_id

    def test_get_redis_url(self):
        """get_redis_url returns correct value."""
        url = get_redis_url()
        assert "redis" in url

    def test_get_qdrant_url(self):
        """get_qdrant_url returns correct value."""
        url = get_qdrant_url()
        assert "qdrant" in url

    def test_get_temporal_url(self):
        """get_temporal_url returns correct value."""
        url = get_temporal_url()
        assert "temporal" in url

    def test_is_debug_enabled_false_by_default(self):
        """is_debug_enabled returns False by default."""
        assert is_debug_enabled() is False

    def test_is_debug_enabled_true_when_debug(self):
        """is_debug_enabled returns True when log level is DEBUG."""
        with patch.dict(os.environ, {"KUBANI_LOG_LEVEL": "DEBUG"}):
            reset_config()
            assert is_debug_enabled() is True


class TestConfigForTesting:
    """Test patterns for using configuration in tests."""

    def test_config_can_be_overridden(self):
        """Configuration can be created with custom values for testing."""
        test_config = CoreConfig(
            vllm_api_url="http://localhost:8000/v1",
            redis_url="redis://localhost:6379/1",
            log_level="DEBUG",
            enable_tracing=True,
        )

        assert test_config.vllm_api_url == "http://localhost:8000/v1"
        assert test_config.redis_url == "redis://localhost:6379/1"
        assert test_config.log_level == "DEBUG"
        assert test_config.enable_tracing is True

    def test_config_fixture_pattern(self):
        """Demonstrates fixture pattern for tests."""
        # In conftest.py, you would have:
        # @pytest.fixture
        # def test_config():
        #     return CoreConfig(
        #         redis_url="redis://localhost:6379/1",
        #         log_level="DEBUG",
        #     )

        test_config = CoreConfig(
            redis_url="redis://localhost:6379/1",
            log_level="DEBUG",
        )

        # Test code would receive this via fixture injection
        assert "localhost" in test_config.redis_url
