"""
Integration tests for Discord MCP Server.

These tests use a mock Discord API to test the server's functionality.
Use docker-compose.integration.yml to start the mock API.

Run with: uv run pytest tests/test_integration.py -v

Note: These tests are simplified since we're using a mock API.
For full integration testing, use a real Discord test server.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

# Set mock environment variables
os.environ["DISCORD_BOT_TOKEN"] = "mock-token-for-testing"
os.environ["DISCORD_GUILD_ID"] = "123456789"


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord client for testing."""
    client = MagicMock(spec=discord.Client)
    client.is_ready = MagicMock(return_value=True)
    client.user = MagicMock()
    client.user.id = 123456789
    client.user.name = "test-bot"
    
    # Mock guild
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    client.guilds = [guild]
    
    # Mock channel
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111111111
    channel.name = "test-channel"
    channel.guild = guild
    channel.category = None
    channel.topic = "Test channel topic"
    channel.position = 0
    
    guild.channels = [channel]
    guild.text_channels = [channel]
    
    client.get_channel = MagicMock(return_value=channel)
    client.get_guild = MagicMock(return_value=guild)
    
    return client


@pytest.fixture
def mock_message():
    """Create a mock Discord message."""
    msg = MagicMock(spec=discord.Message)
    msg.id = 987654321
    msg.channel = MagicMock()
    msg.channel.id = 111111111
    msg.content = "Test message"
    msg.author = MagicMock()
    msg.author.id = 123456789
    msg.author.display_name = "test-bot"
    msg.author.bot = True
    msg.created_at = MagicMock()
    msg.embeds = []
    msg.reference = None
    msg.reactions = []
    return msg


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_message_integration(mock_discord_client, mock_message):
    """
    Test sending a message with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    # Create a mock DiscordClient
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        
        # Mock send method
        channel = mock_discord_client.get_channel(111111111)
        channel.send = AsyncMock(return_value=mock_message)
        
        # Send message
        result = await client.send_message(channel, content="Test message")
        
        assert result is not None
        assert result.id == 987654321
        assert result.content == "Test message"
        channel.send.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_messages_integration(mock_discord_client, mock_message):
    """
    Test retrieving messages with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        
        # Mock history method
        channel = mock_discord_client.get_channel(111111111)
        
        async def mock_history(limit):
            """Mock async iterator for message history."""
            for _ in range(min(limit, 3)):
                yield mock_message
        
        channel.history = MagicMock(return_value=mock_history(10))
        
        # Get messages
        messages = await client.get_messages(channel, limit=10)
        
        assert len(messages) > 0
        assert all(isinstance(m, discord.Message) for m in messages)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_and_get_reactions_integration(mock_discord_client, mock_message):
    """
    Test adding and getting reactions with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        
        # Mock add_reaction
        mock_message.add_reaction = AsyncMock()
        
        # Add reaction
        await client.add_reaction(mock_message, "👍")
        
        mock_message.add_reaction.assert_called_once_with("👍")
        
        # Mock reactions
        mock_reaction = MagicMock(spec=discord.Reaction)
        mock_reaction.emoji = "👍"
        mock_reaction.count = 1
        
        mock_user = MagicMock()
        mock_user.display_name = "test-user"
        mock_user.id = 999999999
        
        async def mock_users():
            """Mock async iterator for reaction users."""
            yield mock_user
        
        mock_reaction.users = MagicMock(return_value=mock_users())
        mock_message.reactions = [mock_reaction]
        
        # Get reactions
        reactions = await client.get_reactions(mock_message)
        
        assert "👍" in reactions
        assert len(reactions["👍"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_channel_operations_integration(mock_discord_client):
    """
    Test channel operations with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        client._guild = mock_discord_client.guilds[0]
        
        # List channels
        channels = await client.list_channels()
        
        assert len(channels) > 0
        assert all(isinstance(c, discord.TextChannel) for c in channels)
        
        # Mock create_text_channel
        new_channel = MagicMock(spec=discord.TextChannel)
        new_channel.id = 222222222
        new_channel.name = "new-test-channel"
        new_channel.guild = client._guild
        new_channel.category = None
        new_channel.topic = "New channel"
        new_channel.position = 1
        
        client._guild.create_text_channel = AsyncMock(return_value=new_channel)
        
        # Create channel
        created = await client.create_channel(name="new-test-channel", topic="New channel")
        
        assert created is not None
        assert created.name == "new-test-channel"
        client._guild.create_text_channel.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_operations_integration(mock_discord_client):
    """
    Test webhook operations with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        
        channel = mock_discord_client.get_channel(111111111)
        
        # Mock webhook
        mock_webhook = MagicMock(spec=discord.Webhook)
        mock_webhook.id = 333333333
        mock_webhook.name = "test-webhook"
        mock_webhook.url = "https://discord.com/api/webhooks/333333333/token"
        mock_webhook.token = "webhook-token"
        
        # Mock webhooks method
        channel.webhooks = AsyncMock(return_value=[])
        
        # Get webhooks (empty initially)
        webhooks = await client.get_webhooks(channel)
        assert len(webhooks) == 0
        
        # Mock create_webhook
        channel.create_webhook = AsyncMock(return_value=mock_webhook)
        
        # Create webhook
        created = await client.create_webhook(channel, name="test-webhook")
        
        assert created is not None
        assert created.id == 333333333
        assert created.name == "test-webhook"
        channel.create_webhook.assert_called_once()
        
        # Mock delete
        mock_webhook.delete = AsyncMock()
        
        # Delete webhook
        await client.delete_webhook(mock_webhook)
        
        mock_webhook.delete.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_channel_by_name_integration(mock_discord_client):
    """
    Test getting channel by name with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        client._guild = mock_discord_client.guilds[0]
        
        # Get channel by name
        channel = client.get_channel_by_name("test-channel")
        
        assert channel is not None
        assert channel.name == "test-channel"
        
        # Try non-existent channel
        channel_none = client.get_channel_by_name("non-existent")
        assert channel_none is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_message_integration(mock_discord_client, mock_message):
    """
    Test deleting a message with mock Discord API.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        client._client = mock_discord_client
        client._ready = True
        
        # Mock delete method
        mock_message.delete = AsyncMock()
        
        # Delete message
        await client.delete_message(mock_message)
        
        mock_message.delete.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_client_connection_state(mock_discord_client):
    """
    Test Discord client connection state management.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    from discord_mcp.client import DiscordClient, DiscordConfig
    
    config = DiscordConfig(
        bot_token="mock-token",
        guild_id=123456789,
    )
    
    with patch("discord_mcp.client.discord.Client", return_value=mock_discord_client):
        client = DiscordClient(config)
        
        # Initially not connected
        assert not client.is_connected
        
        # Mock connection
        client._client = mock_discord_client
        client._ready = True
        
        # Now connected
        assert client.is_connected
