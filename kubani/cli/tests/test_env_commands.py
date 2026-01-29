"""Tests for env commands."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kubani.cli.cli import app

runner = CliRunner()


@pytest.fixture
def temp_env_setup(tmp_path):
    """Create temporary environment setup."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create default and production configs
    (config_dir / "default.yaml").write_text("llm:\n  model: default")
    (config_dir / "production.yaml").write_text("llm:\n  model: prod")

    env_file = tmp_path / ".kubani-env"

    return config_dir, env_file


class TestEnvList:
    """Tests for env list command."""

    def test_list_shows_environments(self, temp_env_setup):
        """Test list shows available environments."""
        config_dir, env_file = temp_env_setup

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "development" in result.output
        assert "production" in result.output

    def test_list_shows_active_environment(self, temp_env_setup):
        """Test list marks active environment."""
        config_dir, env_file = temp_env_setup
        env_file.write_text("production")

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        # Production should be marked as active
        assert "production" in result.output


class TestEnvUse:
    """Tests for env use command."""

    def test_use_switches_environment(self, temp_env_setup):
        """Test use switches to specified environment."""
        config_dir, env_file = temp_env_setup

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "use", "production"])

        assert result.exit_code == 0
        assert "production" in result.output
        assert env_file.read_text() == "production"

    def test_use_invalid_environment(self, temp_env_setup):
        """Test use with invalid environment fails gracefully."""
        config_dir, env_file = temp_env_setup

        # Remove all config files to simulate no valid config
        for f in config_dir.glob("*.yaml"):
            f.unlink()

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "use", "nonexistent"])

        assert result.exit_code == 1
        assert "No config found" in result.output or "not found" in result.output.lower()


class TestEnvShow:
    """Tests for env show command."""

    def test_show_current_environment(self, temp_env_setup):
        """Test show displays current environment details."""
        config_dir, env_file = temp_env_setup
        env_file.write_text("development")

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "show"])

        assert result.exit_code == 0
        assert "development" in result.output
        assert "Environment" in result.output


class TestEnvInit:
    """Tests for env init command."""

    def test_init_creates_new_environment(self, temp_env_setup):
        """Test init creates new environment config."""
        config_dir, env_file = temp_env_setup

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "init", "staging"])

        assert result.exit_code == 0
        assert "Created" in result.output

        staging_file = config_dir / "staging.yaml"
        assert staging_file.exists()

    def test_init_copies_from_source(self, temp_env_setup):
        """Test init copies from specified source."""
        config_dir, env_file = temp_env_setup

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "init", "staging", "--copy-from", "production"])

        assert result.exit_code == 0

        staging_file = config_dir / "staging.yaml"
        content = staging_file.read_text()
        assert "prod" in content  # Should have production's model value

    def test_init_existing_environment_fails(self, temp_env_setup):
        """Test init fails for existing environment."""
        config_dir, env_file = temp_env_setup

        with patch("kubani.cli.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani.cli.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "init", "production"])

        assert result.exit_code == 1
        assert "already exists" in result.output
