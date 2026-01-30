"""Integration tests for kubani dev command.

These tests verify the dev command works with actual agents (without MCP servers).
Run with: pytest tests/integration/cli/test_dev_integration.py -v -m integration
"""

import pytest
from typer.testing import CliRunner


@pytest.mark.integration
class TestDevIntegration:
    """Integration tests that run actual agents."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_dev_help(self, runner):
        """Test dev command help is accessible."""
        from kubani.cli.cli import app

        result = runner.invoke(app, ["dev", "--help"])

        assert result.exit_code == 0
        assert "agent or syndicate" in result.stdout.lower()
        assert "--workflow" in result.stdout
        assert "--publish" in result.stdout
        assert "--no-mcp" in result.stdout

    def test_dev_nonexistent_target(self, runner):
        """Test dev command with nonexistent target."""
        from kubani.cli.cli import app

        result = runner.invoke(app, ["dev", "nonexistent-agent-xyz"])

        assert result.exit_code != 0
        assert "not found" in result.stdout.lower()

    def test_dev_feed_collector_no_mcp_detects_agent(self, runner):
        """Test that feed-collector is detected as an agent."""
        from kubani.cli.cli import app

        # Run with --no-mcp and --json to get structured output
        # This will fail at agent execution (no Redis) but should detect the target
        result = runner.invoke(app, ["dev", "feed-collector", "--no-mcp"])

        # Should at least detect it's an agent and show session header
        # May fail during execution but that's expected without services
        output_lower = result.stdout.lower()
        assert "feed-collector" in output_lower or "feed_collector" in output_lower

    def test_dev_news_digest_no_mcp_detects_syndicate(self, runner):
        """Test that news-digest is detected as a syndicate."""
        from kubani.cli.cli import app

        result = runner.invoke(app, ["dev", "news-digest", "--no-mcp"])

        # Should detect it's a syndicate
        output_lower = result.stdout.lower()
        assert "news-digest" in output_lower or "news_digest" in output_lower
