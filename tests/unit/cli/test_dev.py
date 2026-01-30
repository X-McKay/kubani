"""Tests for kubani dev command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kubani.cli.cli import app

runner = CliRunner()


class TestDevCommandRegistration:
    """Tests for dev command registration and help."""

    def test_command_exists(self):
        """Test dev command is registered."""
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "Run an agent or syndicate locally" in result.stdout

    def test_help_shows_options(self):
        """Test help shows all expected options."""
        result = runner.invoke(app, ["dev", "--help"])
        assert "--workflow" in result.stdout
        assert "--publish" in result.stdout
        assert "--mcp" in result.stdout
        assert "--no-mcp" in result.stdout
        assert "--json" in result.stdout


class TestTargetDetection:
    """Tests for detect_target function."""

    def test_detect_agent(self, tmp_path: Path):
        """Test detecting an agent target."""
        from kubani.cli.dev import detect_target

        # Create agent structure
        agent_path = tmp_path / "kubani" / "agents" / "test_agent"
        agent_path.mkdir(parents=True)
        (agent_path / "agent.py").touch()

        target_type, path = detect_target("test-agent", tmp_path)

        assert target_type == "agent"
        assert path == agent_path

    def test_detect_syndicate(self, tmp_path: Path):
        """Test detecting a syndicate target."""
        from kubani.cli.dev import detect_target

        # Create syndicate structure
        syndicate_path = tmp_path / "kubani" / "syndicates" / "test_syndicate"
        syndicate_path.mkdir(parents=True)
        (syndicate_path / "config.yaml").write_text("name: test-syndicate\n")

        target_type, path = detect_target("test-syndicate", tmp_path)

        assert target_type == "syndicate"
        assert path == syndicate_path

    def test_target_not_found(self, tmp_path: Path):
        """Test error when target doesn't exist."""
        from kubani.cli.dev import detect_target

        # Create empty kubani directory
        (tmp_path / "kubani" / "agents").mkdir(parents=True)
        (tmp_path / "kubani" / "syndicates").mkdir(parents=True)

        with pytest.raises(ValueError, match="not found"):
            detect_target("nonexistent-agent", tmp_path)

    def test_detect_agent_with_underscores(self, tmp_path: Path):
        """Test detecting agent with underscores in directory name."""
        from kubani.cli.dev import detect_target

        # Create agent with underscore name
        agent_path = tmp_path / "kubani" / "agents" / "feed_collector"
        agent_path.mkdir(parents=True)
        (agent_path / "agent.py").touch()

        target_type, path = detect_target("feed-collector", tmp_path)

        assert target_type == "agent"
        assert path == agent_path


class TestConfigLoading:
    """Tests for load_config function."""

    def test_load_default_config(self, tmp_path: Path):
        """Test loading configuration returns a KubaniConfig instance."""
        import os

        from kubani.cli.dev import load_config
        from kubani.framework.config import KubaniConfig

        # Create default config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default.yaml").write_text(
            """
environment: development
llm:
  api_url: http://localhost:8000/v1
  model: test-model
"""
        )

        # Clear any existing config dir env var
        old_config_dir = os.environ.get("KUBANI_CONFIG_DIR")
        try:
            os.environ.pop("KUBANI_CONFIG_DIR", None)
            config = load_config(tmp_path)

            assert isinstance(config, KubaniConfig)
            assert config.environment == "development"
            assert config.llm.api_url == "http://localhost:8000/v1"
        finally:
            if old_config_dir:
                os.environ["KUBANI_CONFIG_DIR"] = old_config_dir

    def test_load_local_overrides(self, tmp_path: Path):
        """Test local config overrides default via framework config."""
        import os

        from kubani.cli.dev import load_config
        from kubani.framework.config import KubaniConfig

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default.yaml").write_text(
            """
environment: development
llm:
  api_url: http://localhost:8000/v1
  model: default-model
"""
        )
        (config_dir / "local.yaml").write_text(
            """
llm:
  api_url: https://llm.example.com/v1
"""
        )

        # Clear any existing config dir env var
        old_config_dir = os.environ.get("KUBANI_CONFIG_DIR")
        try:
            os.environ.pop("KUBANI_CONFIG_DIR", None)
            config = load_config(tmp_path)

            assert isinstance(config, KubaniConfig)
            # Default environment since local.yaml didn't override it
            assert config.environment == "development"
            assert config.llm.api_url == "https://llm.example.com/v1"
            # Model from default should be preserved (deep merge)
            assert config.llm.model == "default-model"
        finally:
            if old_config_dir:
                os.environ["KUBANI_CONFIG_DIR"] = old_config_dir

    def test_load_missing_config_returns_defaults(self, tmp_path: Path):
        """Test loading with missing config files returns defaults."""
        import os

        from kubani.cli.dev import load_config
        from kubani.framework.config import KubaniConfig

        # Clear any existing config dir env var and point to empty dir
        old_config_dir = os.environ.get("KUBANI_CONFIG_DIR")
        try:
            os.environ["KUBANI_CONFIG_DIR"] = str(tmp_path / "nonexistent")
            config = load_config(tmp_path)

            # Should return a valid config with defaults
            assert isinstance(config, KubaniConfig)
            # Default environment from KubaniConfig class
            assert config.environment == "development"
        finally:
            if old_config_dir:
                os.environ["KUBANI_CONFIG_DIR"] = old_config_dir
            else:
                os.environ.pop("KUBANI_CONFIG_DIR", None)


class TestMCPServerDetection:
    """Tests for get_required_mcp_servers function."""

    def test_agent_with_mcp_servers(self, tmp_path: Path):
        """Test getting MCP servers from agent config."""
        from kubani.cli.dev import get_required_mcp_servers

        agent_path = tmp_path / "test_agent"
        agent_path.mkdir()
        (agent_path / "config.yaml").write_text(
            """
name: test-agent
mcp_servers:
  - discord-mcp-server
  - memory-mcp
"""
        )

        servers = get_required_mcp_servers("agent", agent_path)

        assert "discord" in servers
        assert "memory" in servers

    def test_agent_without_mcp_servers(self, tmp_path: Path):
        """Test agent with no MCP servers defined."""
        from kubani.cli.dev import get_required_mcp_servers

        agent_path = tmp_path / "test_agent"
        agent_path.mkdir()
        (agent_path / "config.yaml").write_text(
            """
name: test-agent
mcp_servers: []
"""
        )

        servers = get_required_mcp_servers("agent", agent_path)

        assert servers == []

    def test_missing_config(self, tmp_path: Path):
        """Test handling missing config file."""
        from kubani.cli.dev import get_required_mcp_servers

        agent_path = tmp_path / "test_agent"
        agent_path.mkdir()

        servers = get_required_mcp_servers("agent", agent_path)

        assert servers == []


class TestEnvironmentSetup:
    """Tests for set_environment_from_config function."""

    def test_set_llm_config(self):
        """Test setting LLM environment variables."""
        import os
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        from kubani.cli.dev import set_environment_from_config
        from kubani.framework.config import (
            DiscordConfig,
            EmbeddingsConfig,
            KubaniConfig,
            LLMConfig,
            MCPServerConfig,
            MemoryConfig,
        )

        # Create a mock KubaniConfig with test values
        config = MagicMock(spec=KubaniConfig)
        config.llm = MagicMock(spec=LLMConfig)
        config.llm.api_url = "https://llm.test.com/v1"
        config.llm.model = "test-model"
        config.embeddings = MagicMock(spec=EmbeddingsConfig)
        config.embeddings.api_url = ""
        config.embeddings.model = ""
        config.mcp = MagicMock(spec=MCPServerConfig)
        config.mcp.discord_url = ""
        config.mcp.memory_url = ""
        config.mcp.temporal_url = ""
        config.mcp.qdrant_url = ""
        config.discord = MagicMock(spec=DiscordConfig)
        config.discord.bot_token = SecretStr("")
        config.discord.guild_id = ""
        config.discord.digest_channel = ""
        config.discord.breaking_news_channel = ""
        config.memory = MagicMock(spec=MemoryConfig)
        config.memory.qdrant = MagicMock()
        config.memory.qdrant.url = ""
        config.memory.qdrant.api_key = None
        config.memory.redis = MagicMock()
        config.memory.redis.url = ""

        # Clear any existing values
        os.environ.pop("VLLM_API_URL", None)
        os.environ.pop("VLLM_MODEL", None)

        set_environment_from_config(config, {})

        assert os.environ["VLLM_API_URL"] == "https://llm.test.com/v1"
        assert os.environ["VLLM_MODEL"] == "test-model"

    def test_set_mcp_urls(self):
        """Test setting MCP URL environment variables."""
        import os
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        from kubani.cli.dev import set_environment_from_config
        from kubani.framework.config import (
            DiscordConfig,
            EmbeddingsConfig,
            KubaniConfig,
            LLMConfig,
            MCPServerConfig,
            MemoryConfig,
        )

        # Create a mock KubaniConfig
        config = MagicMock(spec=KubaniConfig)
        config.llm = MagicMock(spec=LLMConfig)
        config.llm.api_url = ""
        config.llm.model = ""
        config.embeddings = MagicMock(spec=EmbeddingsConfig)
        config.embeddings.api_url = ""
        config.embeddings.model = ""
        config.mcp = MagicMock(spec=MCPServerConfig)
        config.mcp.discord_url = ""
        config.mcp.memory_url = ""
        config.mcp.temporal_url = ""
        config.mcp.qdrant_url = ""
        config.discord = MagicMock(spec=DiscordConfig)
        config.discord.bot_token = SecretStr("")
        config.discord.guild_id = ""
        config.discord.digest_channel = ""
        config.discord.breaking_news_channel = ""
        config.memory = MagicMock(spec=MemoryConfig)
        config.memory.qdrant = MagicMock()
        config.memory.qdrant.url = ""
        config.memory.qdrant.api_key = None
        config.memory.redis = MagicMock()
        config.memory.redis.url = ""

        mcp_urls = {
            "discord": "http://localhost:8084",
            "memory": "http://localhost:8083",
        }

        set_environment_from_config(config, mcp_urls)

        assert os.environ["MCP_DISCORD_URL"] == "http://localhost:8084"
        assert os.environ["MCP_MEMORY_URL"] == "http://localhost:8083"


class TestAgentMethodDetection:
    """Tests for _detect_agent_method function."""

    def test_known_agents(self):
        """Test method detection for known agents."""
        from kubani.cli.dev import _detect_agent_method

        assert _detect_agent_method("FeedCollectorAgent") == "collect"
        assert _detect_agent_method("ContentAnalystAgent") == "full_analysis"
        assert _detect_agent_method("DigestPublisherAgent") == "compose_and_publish"
        assert _detect_agent_method("CriticAgent") == "evaluate_recent_executions"

    def test_unknown_agent_defaults_to_run(self):
        """Test unknown agents default to 'run' method."""
        from kubani.cli.dev import _detect_agent_method

        assert _detect_agent_method("UnknownAgent") == "run"


class TestDataclassConversion:
    """Tests for dataclass to dict conversion."""

    def test_simple_dataclass(self):
        """Test converting simple dataclass."""
        from dataclasses import dataclass

        from kubani.cli.dev import _dataclass_to_dict

        @dataclass
        class TestResult:
            name: str
            count: int

        result = TestResult(name="test", count=42)
        converted = _dataclass_to_dict(result)

        assert converted == {"name": "test", "count": 42}

    def test_nested_dataclass(self):
        """Test converting nested dataclasses."""
        from dataclasses import dataclass

        from kubani.cli.dev import _dataclass_to_dict

        @dataclass
        class Inner:
            value: str

        @dataclass
        class Outer:
            inner: Inner
            name: str

        result = Outer(inner=Inner(value="test"), name="outer")
        converted = _dataclass_to_dict(result)

        assert converted == {"inner": {"value": "test"}, "name": "outer"}

    def test_dataclass_with_list(self):
        """Test converting dataclass with list field."""
        from dataclasses import dataclass, field

        from kubani.cli.dev import _dataclass_to_dict

        @dataclass
        class Item:
            name: str

        @dataclass
        class Container:
            items: list[Item] = field(default_factory=list)

        result = Container(items=[Item(name="a"), Item(name="b")])
        converted = _dataclass_to_dict(result)

        assert converted == {"items": [{"name": "a"}, {"name": "b"}]}


class TestDevSessionIntegration:
    """Integration tests for run_dev_session."""

    @pytest.mark.asyncio
    async def test_target_not_found_returns_error(self, tmp_path: Path):
        """Test run_dev_session returns error for missing target."""
        from kubani.cli.dev import run_dev_session

        # Mock find_project_root to return our temp directory
        with patch("kubani.cli.dev.find_project_root", return_value=tmp_path):
            # Create minimal structure
            (tmp_path / "kubani" / "agents").mkdir(parents=True)
            (tmp_path / "kubani" / "syndicates").mkdir(parents=True)
            (tmp_path / "config").mkdir()

            exit_code = await run_dev_session(
                target="nonexistent",
                workflow=False,
                publish=False,
                mcp_servers=None,
                no_mcp=True,
                json_output=True,
            )

            assert exit_code == 1


class TestCLIInvocation:
    """Tests for CLI invocation with various options."""

    def test_target_not_found_cli(self):
        """Test CLI returns error for nonexistent target."""
        result = runner.invoke(app, ["dev", "nonexistent-agent-xyz", "--no-mcp"])
        assert result.exit_code != 0
        assert "not found" in result.stdout.lower()

    def test_json_output_flag(self):
        """Test --json flag is accepted."""
        result = runner.invoke(app, ["dev", "nonexistent", "--json", "--no-mcp"])
        # Should fail but with JSON output
        assert result.exit_code != 0
        # Output should be parseable as JSON

        # The error message should be in JSON format
        assert "error" in result.stdout.lower() or "{" in result.stdout


class TestDisplayFunctions:
    """Tests for display helper functions."""

    def test_display_collection_results(self, capsys):
        """Test display of collection results."""
        from kubani.cli.dev import display_collection_results

        result = {
            "total_collected": 10,
            "sources_fetched": 5,
            "seen_filtered": 3,
            "failed_feeds": 1,
            "articles": [{"title": "Test Article", "source": "Test Source"}],
        }

        display_collection_results(result)

        captured = capsys.readouterr()
        assert "10" in captured.out
        assert "5" in captured.out

    def test_display_analysis_results(self, capsys):
        """Test display of analysis results."""
        from kubani.cli.dev import display_analysis_results

        result = {
            "processed_articles": [
                {"title": "Article 1", "importance_score": 8},
                {"title": "Article 2", "importance_score": 6},
            ],
            "trends": [{"topic": "AI", "status": "hot", "article_count": 5}],
            "breaking_articles": [],
            "articles_analyzed": 2,
            "articles_failed": 0,
            "duplicates_filtered": 0,
        }

        display_analysis_results(result)

        captured = capsys.readouterr()
        assert "2" in captured.out  # Articles processed

    def test_display_digest_results_dry_run(self, capsys):
        """Test display of digest results in dry run mode."""
        from kubani.cli.dev import display_digest_results

        result = {
            "dry_run": True,
            "would_publish_to": "ai-news",
            "digest_id": "test-123",
            "total_articles": 5,
            "formatted_content": "# Test Digest\n\nThis is a test.",
        }

        display_digest_results(result, dry_run=True)

        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "ai-news" in captured.out

    def test_display_digest_results_published(self, capsys):
        """Test display of digest results when published."""
        from kubani.cli.dev import display_digest_results

        result = {
            "success": True,
            "channel": "ai-news",
            "chunks_sent": 2,
            "message_id": "12345",
        }

        display_digest_results(result, dry_run=False)

        captured = capsys.readouterr()
        assert "published" in captured.out.lower()
        assert "ai-news" in captured.out
