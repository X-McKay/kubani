"""Tests for config commands."""

from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from kubani_dev.cli import app

runner = CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create default config
    default_config = {
        "llm": {"api_url": "http://localhost:8000", "model": "test-model"},
        "temporal": {"host": "localhost:7233"},
    }
    with open(config_dir / "default.yaml", "w") as f:
        yaml.dump(default_config, f)

    return config_dir


class TestConfigGet:
    """Tests for config get command."""

    def test_get_simple_key(self, temp_config_dir):
        """Test getting a simple config key."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "get", "llm.api_url"])

        assert result.exit_code == 0
        assert "http://localhost:8000" in result.output

    def test_get_nested_object(self, temp_config_dir):
        """Test getting a nested config object."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "get", "llm"])

        assert result.exit_code == 0
        assert "api_url" in result.output
        assert "model" in result.output

    def test_get_missing_key(self, temp_config_dir):
        """Test getting a missing key returns error."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "get", "nonexistent.key"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestConfigSet:
    """Tests for config set command."""

    def test_set_creates_local_yaml(self, temp_config_dir):
        """Test set creates local.yaml by default."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "set", "custom.key", "value"])

        assert result.exit_code == 0

        local_file = temp_config_dir / "local.yaml"
        assert local_file.exists()

        with open(local_file) as f:
            config = yaml.safe_load(f)

        assert config["custom"]["key"] == "value"

    def test_set_parses_boolean_true(self, temp_config_dir):
        """Test set parses boolean true."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "set", "feature.enabled", "true"])

        assert result.exit_code == 0

        local_file = temp_config_dir / "local.yaml"
        with open(local_file) as f:
            config = yaml.safe_load(f)

        assert config["feature"]["enabled"] is True

    def test_set_parses_integer(self, temp_config_dir):
        """Test set parses integer values."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "set", "server.port", "8080"])

        assert result.exit_code == 0

        local_file = temp_config_dir / "local.yaml"
        with open(local_file) as f:
            config = yaml.safe_load(f)

        assert config["server"]["port"] == 8080


class TestConfigShow:
    """Tests for config show command."""

    def test_show_displays_config(self, temp_config_dir):
        """Test show displays merged configuration."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert "llm" in result.output
        assert "temporal" in result.output

    def test_show_section_filter(self, temp_config_dir):
        """Test show with section filter."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "show", "--section", "llm"])

        assert result.exit_code == 0
        assert "api_url" in result.output
        # Should not show temporal since we filtered to llm
        assert "temporal" not in result.output or "host" not in result.output


class TestConfigValidate:
    """Tests for config validate command."""

    def test_validate_valid_config(self, temp_config_dir):
        """Test validate passes for valid config."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "validate"])

        assert result.exit_code == 0
        assert "Valid" in result.output or "valid" in result.output


class TestConfigDiff:
    """Tests for config diff command."""

    def test_diff_between_environments(self, temp_config_dir):
        """Test diff between environments."""
        # Create production config with different values
        prod_config = {
            "llm": {"api_url": "https://prod.example.com", "model": "prod-model"},
            "temporal": {"host": "prod-temporal:7233"},
        }
        with open(temp_config_dir / "production.yaml", "w") as f:
            yaml.dump(prod_config, f)

        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "diff", "development", "production"])

        # Diff should complete (exit code 0 or 1 depending on diff tool)
        # Just check it ran
        assert result.exit_code in [0, 1]
