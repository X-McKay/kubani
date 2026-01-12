"""
Tests for the unified configuration system.

Tests cover:
- Configuration loading from YAML files
- Environment variable overrides
- Pydantic validation
- MCP server configuration
- Helper functions
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


class TestConfigUnified:
    """Tests for the unified configuration system."""

    def test_default_config_loads(self):
        """Test that default configuration loads without errors."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert config.environment == "development"
        assert config.agent_name == "kubani-agent"
        # Log level may be overridden by environment
        assert config.log_level in ["INFO", "DEBUG"]

    def test_nested_environment_variable_override(self):
        """Test that nested environment variables work with __ delimiter."""
        import importlib
        import core_agents.config_unified as config_module
        
        with patch.dict(os.environ, {
            "KUBANI_LLM__API_URL": "http://test-llm:8000/v1",
            "KUBANI_LLM__MODEL": "test-model",
            "KUBANI_TEMPORAL__HOST": "test-temporal:7233",
        }, clear=False):
            importlib.reload(config_module)
            config = config_module.KubaniConfig()
            
            assert config.llm.api_url == "http://test-llm:8000/v1"
            assert config.llm.model == "test-model"
            assert config.temporal.host == "test-temporal:7233"

    def test_mcp_config_defaults(self):
        """Test MCP server configuration defaults."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert config.mcp.temporal_enabled is True
        assert config.mcp.qdrant_enabled is True
        assert config.mcp.memory_enabled is True
        assert config.mcp.discord_enabled is True
        assert "localhost" in config.mcp.temporal_url

    def test_get_mcp_servers(self):
        """Test the get_mcp_servers helper method."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        servers = config.get_mcp_servers()
        
        assert "temporal" in servers
        assert "qdrant" in servers
        assert "memory" in servers
        assert "discord" in servers

    def test_temporal_config_computed_fields(self):
        """Test Temporal configuration computed fields."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert config.temporal.grpc_url == f"grpc://{config.temporal.host}"

    def test_qdrant_config_computed_fields(self):
        """Test Qdrant configuration computed fields."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert "http://" in config.memory.qdrant.url
        assert str(config.memory.qdrant.port) in config.memory.qdrant.url

    def test_redis_config_url_without_password(self):
        """Test Redis URL generation without password."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert "redis://" in config.memory.redis.url
        assert "@" not in config.memory.redis.url  # No password

    def test_llm_config_validation(self):
        """Test LLM configuration validation."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert config.llm.temperature >= 0.0
        assert config.llm.temperature <= 2.0
        assert config.llm.max_tokens >= 1

    def test_learning_config_defaults(self):
        """Test learning configuration defaults."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        assert config.learning.enabled is True
        assert config.learning.critic_enabled is True
        assert config.learning.reflection_enabled is True
        assert config.learning.auto_approve_threshold >= 0.0
        assert config.learning.auto_approve_threshold <= 1.0

    def test_local_dev_config_defaults(self):
        """Test local development configuration defaults."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config = config_module.KubaniConfig()
        
        # Default is disabled unless explicitly enabled
        assert config.local_dev.output_mode in ["console", "discord", "both"]

    def test_get_config_singleton(self):
        """Test that get_config returns a singleton."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config1 = config_module.get_config()
        config2 = config_module.get_config()
        
        assert config1 is config2

    def test_reload_config(self):
        """Test that reload_config creates a fresh instance."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        config1 = config_module.get_config()
        config2 = config_module.reload_config()
        
        # After reload, get_config should return the new instance
        config3 = config_module.get_config()
        assert config2 is config3

    def test_yaml_config_loading(self):
        """Test loading configuration from YAML files."""
        import importlib
        import core_agents.config_unified as config_module
        
        # Create a temporary config file
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.default.yaml"
            config_file.write_text(yaml.dump({
                "environment": "development",
                "agent_name": "yaml-test-agent",
                "llm": {
                    "api_url": "http://yaml-llm:8000/v1",
                },
            }))
            
            with patch.dict(os.environ, {"KUBANI_CONFIG_DIR": tmpdir}, clear=False):
                importlib.reload(config_module)
                config = config_module.KubaniConfig()
                
                assert config.environment == "development"
                assert config.agent_name == "yaml-test-agent"
                assert config.llm.api_url == "http://yaml-llm:8000/v1"

    def test_deep_merge(self):
        """Test the deep_merge utility function."""
        from core_agents.config_unified import deep_merge
        
        base = {
            "a": 1,
            "b": {"c": 2, "d": 3},
            "e": [1, 2, 3],
        }
        override = {
            "a": 10,
            "b": {"c": 20},
            "f": 4,
        }
        
        result = deep_merge(base, override)
        
        assert result["a"] == 10  # Overridden
        assert result["b"]["c"] == 20  # Nested override
        assert result["b"]["d"] == 3  # Preserved from base
        assert result["e"] == [1, 2, 3]  # Preserved
        assert result["f"] == 4  # Added from override


class TestConvenienceFunctions:
    """Tests for convenience accessor functions."""

    def test_get_llm_config(self):
        """Test get_llm_config returns LLM configuration."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        llm_config = config_module.get_llm_config()
        
        assert llm_config.api_url is not None
        assert llm_config.model is not None

    def test_get_memory_config(self):
        """Test get_memory_config returns memory configuration."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        memory_config = config_module.get_memory_config()
        
        assert memory_config.qdrant is not None
        assert memory_config.neo4j is not None
        assert memory_config.redis is not None

    def test_get_temporal_config(self):
        """Test get_temporal_config returns Temporal configuration."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        temporal_config = config_module.get_temporal_config()
        
        assert temporal_config.host is not None
        assert temporal_config.namespace is not None

    def test_get_discord_config(self):
        """Test get_discord_config returns Discord configuration."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        discord_config = config_module.get_discord_config()
        
        assert discord_config is not None

    def test_get_mcp_config(self):
        """Test get_mcp_config returns MCP server configuration."""
        import importlib
        import core_agents.config_unified as config_module
        importlib.reload(config_module)
        
        mcp_config = config_module.get_mcp_config()
        
        assert mcp_config.temporal_url is not None
        assert mcp_config.qdrant_url is not None
        assert mcp_config.memory_url is not None
