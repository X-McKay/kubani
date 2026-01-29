"""Tests for kubani agent CLI commands."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kubani.cli.cli import get_click_app


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


# Get the Click app with all commands registered
cli = get_click_app()


class TestAgentDraftCommand:
    """Test agent draft command."""

    def test_draft_requires_name(self, cli_runner):
        """Draft command should require --name option."""
        result = cli_runner.invoke(
            cli,
            ["agent", "draft", "--description", "A test agent"],
        )
        assert result.exit_code != 0
        assert "name" in result.output.lower() or "required" in result.output.lower()

    def test_draft_requires_description(self, cli_runner):
        """Draft command should require --description option."""
        result = cli_runner.invoke(
            cli,
            ["agent", "draft", "--name", "test-agent"],
        )
        assert result.exit_code != 0
        assert "description" in result.output.lower() or "required" in result.output.lower()

    def test_draft_shows_panel_before_connecting(self, cli_runner):
        """Draft command should show config panel before trying to connect."""
        # This will fail to connect but should show the panel first
        result = cli_runner.invoke(
            cli,
            [
                "agent",
                "draft",
                "--name",
                "test-agent",
                "--description",
                "A test agent",
                "--temporal-address",
                "invalid:7233",
            ],
        )
        # Should show the configuration panel
        assert "test-agent" in result.output
        assert "A test agent" in result.output

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_draft_accepts_all_options(self, mock_run, cli_runner):
        """Draft command should accept all configuration options."""
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            [
                "agent",
                "draft",
                "--name",
                "test-agent",
                "--description",
                "A test agent",
                "--target-accuracy",
                "0.9",
                "--max-iterations",
                "10",
                "--non-interactive",
            ],
        )
        # Command should have been invoked
        assert mock_run.called

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_draft_shows_target_accuracy_in_panel(self, mock_run, cli_runner):
        """Draft command should display target accuracy in config panel."""
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            [
                "agent",
                "draft",
                "--name",
                "test-agent",
                "--description",
                "A test agent",
                "--target-accuracy",
                "0.9",
            ],
        )
        # Should show the target accuracy
        assert "90%" in result.output or "0.9" in result.output


class TestAgentStatusCommand:
    """Test agent status command."""

    def test_status_requires_agent_name(self, cli_runner):
        """Status command should require agent name argument."""
        result = cli_runner.invoke(cli, ["agent", "status"])
        assert result.exit_code != 0

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_status_accepts_agent_name(self, mock_run, cli_runner):
        """Status command should accept agent name as positional arg."""
        mock_run.return_value = None

        result = cli_runner.invoke(cli, ["agent", "status", "my-agent"])
        assert mock_run.called

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_status_accepts_json_output(self, mock_run, cli_runner):
        """Status command should accept --json flag."""
        mock_run.return_value = None

        result = cli_runner.invoke(cli, ["agent", "status", "my-agent", "--json"])
        assert mock_run.called

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_status_accepts_temporal_address(self, mock_run, cli_runner):
        """Status command should accept --temporal-address option."""
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            ["agent", "status", "my-agent", "--temporal-address", "custom:7233"],
        )
        assert mock_run.called


class TestAgentCancelCommand:
    """Test agent cancel command."""

    def test_cancel_requires_agent_name(self, cli_runner):
        """Cancel command should require agent name argument."""
        result = cli_runner.invoke(cli, ["agent", "cancel"])
        assert result.exit_code != 0

    def test_cancel_prompts_for_confirmation(self, cli_runner):
        """Cancel command should prompt for confirmation by default."""
        result = cli_runner.invoke(
            cli,
            ["agent", "cancel", "my-agent"],
            input="n\n",  # Decline confirmation
        )
        # Should show confirmation prompt and cancel
        assert "cancel" in result.output.lower() or "Cancelled" in result.output

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_cancel_force_skips_confirmation(self, mock_run, cli_runner):
        """Cancel command with --force should skip confirmation."""
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            ["agent", "cancel", "my-agent", "--force"],
        )
        assert mock_run.called

    @patch("kubani.cli.commands.agent.asyncio.run")
    def test_cancel_accepts_temporal_address(self, mock_run, cli_runner):
        """Cancel command should accept --temporal-address option."""
        mock_run.return_value = None

        result = cli_runner.invoke(
            cli,
            ["agent", "cancel", "my-agent", "--force", "--temporal-address", "custom:7233"],
        )
        assert mock_run.called


class TestAgentListCommand:
    """Test agent list command."""

    def test_list_runs_without_error(self, cli_runner):
        """List command should run without errors."""
        result = cli_runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0

    def test_list_shows_table_or_message(self, cli_runner):
        """List command should show table or informative message."""
        result = cli_runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        # Should show column headers or agents not found message
        assert (
            "Name" in result.output
            or "name" in result.output.lower()
            or "not found" in result.output.lower()
        )


class TestAgentRunCommand:
    """Test agent run command."""

    def test_run_requires_agent_name(self, cli_runner):
        """Run command should require agent name argument."""
        result = cli_runner.invoke(cli, ["agent", "run"])
        assert result.exit_code != 0

    def test_run_accepts_mode_option(self, cli_runner):
        """Run command should accept --mode option."""
        # This will fail to find agent but should parse args correctly
        result = cli_runner.invoke(
            cli,
            ["agent", "run", "nonexistent-agent", "--mode", "local"],
        )
        # Should show error about agent not found, not about invalid mode
        assert "not found" in result.output.lower() or "nonexistent" in result.output.lower()


class TestAgentInfoCommand:
    """Test agent info command."""

    def test_info_requires_agent_name(self, cli_runner):
        """Info command should require agent name argument."""
        result = cli_runner.invoke(cli, ["agent", "info"])
        assert result.exit_code != 0

    def test_info_shows_error_for_nonexistent(self, cli_runner):
        """Info command should show error for nonexistent agent."""
        result = cli_runner.invoke(cli, ["agent", "info", "nonexistent-agent"])
        assert "not found" in result.output.lower()


class TestAgentEvalCommand:
    """Test agent eval command."""

    def test_eval_requires_agent_name(self, cli_runner):
        """Eval command should require agent name argument."""
        result = cli_runner.invoke(cli, ["agent", "eval"])
        assert result.exit_code != 0

    def test_eval_accepts_suite_option(self, cli_runner, tmp_path):
        """Eval command should accept --suite option."""
        # Create a minimal suite file
        suite_file = tmp_path / "suite.yaml"
        suite_file.write_text("scenarios: []")

        result = cli_runner.invoke(
            cli,
            ["agent", "eval", "nonexistent-agent", "--suite", str(suite_file)],
        )
        # Should parse suite correctly and either find agent or report no scenarios
        assert result.exit_code == 0 or "not found" in result.output.lower()
        # Verify suite was parsed
        assert str(suite_file) in result.output or "scenarios" in result.output.lower()
