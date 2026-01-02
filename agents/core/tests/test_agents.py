"""Tests for core agents."""


class TestDiscordAgent:
    """Tests for DiscordAgent."""

    def test_discord_agent_import(self):
        """Test that DiscordAgent can be imported."""
        from core_agents import DiscordAgent

        assert DiscordAgent is not None

    def test_discord_agent_attributes(self):
        """Test DiscordAgent has expected attributes."""
        from core_agents import DiscordAgent

        agent = DiscordAgent()
        assert agent.NAME == "discord"
        assert agent.DESCRIPTION == "Publish summaries and alerts to Discord"


class TestMemoryAgent:
    """Tests for MemoryAgent."""

    def test_memory_agent_import(self):
        """Test that MemoryAgent can be imported."""
        from core_agents import MemoryAgent

        assert MemoryAgent is not None


class TestUtilities:
    """Tests for utility functions."""

    def test_create_model_import(self):
        """Test that create_model can be imported."""
        from core_agents import create_model

        assert create_model is not None

    def test_create_agent_import(self):
        """Test that create_agent can be imported."""
        from core_agents import create_agent

        assert create_agent is not None

    def test_discord_notify_import(self):
        """Test that discord_notify tool can be imported."""
        from core_agents import discord_notify

        assert discord_notify is not None


class TestDiscordUtils:
    """Tests for Discord utility functions."""

    def test_discord_embed_import(self):
        """Test that DiscordEmbed can be imported."""
        from core_agents import DiscordEmbed

        assert DiscordEmbed is not None

    def test_colors_import(self):
        """Test that Colors can be imported."""
        from core_agents import Colors

        assert Colors is not None
        assert Colors.SUCCESS == 0x57F287
        assert Colors.ERROR == 0xED4245

    def test_send_discord_message_sync_import(self):
        """Test that send_discord_message_sync can be imported."""
        from core_agents import send_discord_message_sync

        assert send_discord_message_sync is not None

    def test_post_discord_message_alias(self):
        """Test that post_discord_message is an alias for send_discord_message_sync."""
        from core_agents import post_discord_message, send_discord_message_sync

        assert post_discord_message is send_discord_message_sync

    def test_discord_embed_to_dict(self):
        """Test DiscordEmbed.to_dict() method."""
        from core_agents import DiscordEmbed

        embed = DiscordEmbed(
            title="Test Title",
            description="Test Description",
            color=0xFF0000,
        )
        result = embed.to_dict()
        assert result["title"] == "Test Title"
        assert result["description"] == "Test Description"
        assert result["color"] == 0xFF0000


class TestTemporalUtils:
    """Tests for Temporal utility functions."""

    def test_get_temporal_client_import(self):
        """Test that get_temporal_client can be imported."""
        from core_agents import get_temporal_client

        assert get_temporal_client is not None

    def test_get_local_temporal_client_import(self):
        """Test that get_local_temporal_client can be imported."""
        from core_agents import get_local_temporal_client

        assert get_local_temporal_client is not None
