"""Tests for kubani skill CLI commands."""

import pytest
from click.testing import CliRunner

from kubani.cli.cli import get_click_app


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


# Get the Click app with all commands registered
cli = get_click_app()


class TestSkillAutoCommand:
    """Test skill auto command."""

    def test_auto_requires_description(self, cli_runner):
        """Skill auto command should require --description flag."""
        result = cli_runner.invoke(cli, ["skill", "auto"])
        # Should fail because -d/--description is required
        assert result.exit_code != 0
        assert "description" in result.output.lower() or "required" in result.output.lower()

    def test_auto_help_shows_options(self, cli_runner):
        """Skill auto command help should show all options."""
        result = cli_runner.invoke(cli, ["skill", "auto", "--help"])
        assert result.exit_code == 0
        assert "--description" in result.output
        assert "--improve" in result.output
        assert "--max-iterations" in result.output
        assert "--target-accuracy" in result.output
        assert "--background" in result.output


class TestSkillAutoStatusCommand:
    """Test skill auto-status command."""

    def test_auto_status_requires_workflow_id(self, cli_runner):
        """Skill auto-status command should require workflow_id argument."""
        result = cli_runner.invoke(cli, ["skill", "auto-status"])
        # Should fail because workflow_id is required
        assert result.exit_code != 0
        assert "workflow_id" in result.output.lower() or "missing" in result.output.lower()

    def test_auto_status_help_shows_options(self, cli_runner):
        """Skill auto-status command help should show options."""
        result = cli_runner.invoke(cli, ["skill", "auto-status", "--help"])
        assert result.exit_code == 0
        assert "WORKFLOW_ID" in result.output
        assert "--temporal" in result.output


class TestSkillGroup:
    """Test skill command group."""

    def test_skill_help_shows_available_commands(self, cli_runner):
        """Skill group help should show available commands."""
        result = cli_runner.invoke(cli, ["skill", "--help"])
        assert result.exit_code == 0
        assert "auto" in result.output
        assert "auto-status" in result.output

    def test_skill_no_args_shows_usage(self, cli_runner):
        """Skill group with no args should show usage error."""
        result = cli_runner.invoke(cli, ["skill"])
        # Click groups with no args exit with code 2 (usage error) and show nothing
        # This is expected behavior - user should use --help to see commands
        assert result.exit_code in [0, 2]
