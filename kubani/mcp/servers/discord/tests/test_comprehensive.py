"""
Comprehensive pre-deployment tests for Discord MCP Server.

Tests all 17 Discord tools with valid inputs and error handling.
Verifies correct behavior with real Discord API.
Cleans up all test data after completion.

Requirements: 11.1, 11.2, 11.3, 11.6
"""

import logging
from datetime import datetime

import pytest

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    cleanup_test_data,
    get_test_resource_prefix,
    load_test_config,
    skip_if_backend_unavailable,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)

# Load configuration
config = load_test_config("discord")

# Skip all tests if Discord not configured
pytestmark = pytest.mark.skipif(
    not config.enabled,
    reason="Discord not configured in config/local.yaml",
)


@pytest.fixture
def test_prefix():
    """Get unique prefix for test resources."""
    return get_test_resource_prefix()


@pytest.fixture
def created_resources():
    """Track created resources for cleanup."""
    return {
        "messages": [],
        "message_channels": {},  # message_id -> channel_id mapping
        "channels": [],
        "webhooks": [],
    }


# =========================================================================
# Message Tools Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_send_message_comprehensive(created_resources):
    """Test send_message tool with valid inputs."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]
        test_content = f"Test message from comprehensive test - {datetime.now().isoformat()}"

        # Send message
        result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": test_content},
        )

        assert result["message_id"] is not None
        assert result["channel_id"] == channel_id
        assert result["content"] == test_content

        # Track for cleanup
        message_id = result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        # Verify message was created
        get_result = await session.call_tool(
            "get_message",
            {"channel_id": channel_id, "message_id": message_id},
        )

        assert get_result["message_id"] == message_id
        assert get_result["content"] == test_content

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_send_message_with_embed_comprehensive(created_resources):
    """Test send_message tool with embed."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        embed = {
            "title": "Test Embed",
            "description": "This is a test embed from comprehensive testing",
            "color": 0x00FF00,
        }

        # Send message with embed
        result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message with embed", "embed": embed},
        )

        assert result["message_id"] is not None
        assert result["has_embeds"] is True

        # Track for cleanup
        message_id = result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_send_message_error_handling():
    """Test send_message error handling with invalid channel ID."""
    async with start_mcp_server_stdio("discord", config) as session:
        # Test with invalid channel ID
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "send_message",
                {"channel_id": "999999999999999999", "content": "Test"},
            )

        # Should get an error about channel not found
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_get_messages_comprehensive():
    """Test get_messages tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        # Get messages
        result = await session.call_tool(
            "get_messages",
            {"channel_id": channel_id, "limit": 5},
        )

        assert "messages" in result
        assert "count" in result
        assert result["channel_id"] == channel_id
        assert isinstance(result["messages"], list)
        assert result["count"] <= 5


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_get_messages_error_handling():
    """Test get_messages error handling with invalid channel."""
    async with start_mcp_server_stdio("discord", config) as session:
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_messages",
                {"channel_id": "999999999999999999", "limit": 5},
            )

        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_delete_message_comprehensive(created_resources):
    """Test delete_message tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        # Create a message to delete
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message to delete"},
        )
        message_id = send_result["message_id"]

        # Delete the message
        delete_result = await session.call_tool(
            "delete_message",
            {"channel_id": channel_id, "message_id": message_id},
        )

        assert "message" in delete_result
        assert message_id in delete_result["message"]

        # Verify message is deleted (should raise error)
        with pytest.raises(Exception):
            await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": message_id},
            )


# =========================================================================
# Reaction Tools Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_add_reaction_comprehensive(created_resources):
    """Test add_reaction tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        # Create a message
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message for reaction test"},
        )
        message_id = send_result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        # Add reaction
        reaction_result = await session.call_tool(
            "add_reaction",
            {"channel_id": channel_id, "message_id": message_id, "emoji": "👍"},
        )

        assert "message" in reaction_result
        assert "👍" in reaction_result["message"]

        # Verify reaction was added
        reactions_result = await session.call_tool(
            "get_reactions",
            {"channel_id": channel_id, "message_id": message_id},
        )

        assert len(reactions_result["reactions"]) > 0
        assert any(r["emoji"] == "👍" for r in reactions_result["reactions"])

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_remove_reaction_comprehensive(created_resources):
    """Test remove_reaction tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        # Create a message and add reaction
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message for remove reaction test"},
        )
        message_id = send_result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        await session.call_tool(
            "add_reaction",
            {"channel_id": channel_id, "message_id": message_id, "emoji": "❤️"},
        )

        # Remove reaction
        remove_result = await session.call_tool(
            "remove_reaction",
            {"channel_id": channel_id, "message_id": message_id, "emoji": "❤️"},
        )

        assert "message" in remove_result

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_get_reactions_comprehensive(created_resources):
    """Test get_reactions tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        # Create a message
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message for get reactions test"},
        )
        message_id = send_result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        # Add multiple reactions
        await session.call_tool(
            "add_reaction",
            {"channel_id": channel_id, "message_id": message_id, "emoji": "👍"},
        )
        await session.call_tool(
            "add_reaction",
            {"channel_id": channel_id, "message_id": message_id, "emoji": "🎉"},
        )

        # Get reactions
        result = await session.call_tool(
            "get_reactions",
            {"channel_id": channel_id, "message_id": message_id},
        )

        assert "reactions" in result
        assert len(result["reactions"]) >= 2
        emojis = [r["emoji"] for r in result["reactions"]]
        assert "👍" in emojis
        assert "🎉" in emojis

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


# =========================================================================
# Channel Tools Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_list_channels_comprehensive():
    """Test list_channels tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        result = await session.call_tool("list_channels", {})

        assert "channels" in result
        assert "guild_id" in result
        assert "count" in result
        assert isinstance(result["channels"], list)
        assert result["count"] > 0


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_create_channel_comprehensive(test_prefix, created_resources):
    """Test create_channel tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_name = f"{test_prefix}-test-channel"

        # Create channel
        result = await session.call_tool(
            "create_channel",
            {"name": channel_name, "topic": "Test channel from comprehensive testing"},
        )

        assert result["channel_id"] is not None
        assert result["name"] == channel_name.lower().replace("_", "-")
        assert result["topic"] == "Test channel from comprehensive testing"

        # Track for cleanup
        created_resources["channels"].append(result["channel_id"])

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_delete_channel_comprehensive(test_prefix, created_resources):
    """Test delete_channel tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_name = f"{test_prefix}-delete-test"

        # Create channel
        create_result = await session.call_tool(
            "create_channel",
            {"name": channel_name},
        )
        channel_id = create_result["channel_id"]

        # Delete channel
        delete_result = await session.call_tool(
            "delete_channel",
            {"channel_id": channel_id, "reason": "Comprehensive test cleanup"},
        )

        assert "message" in delete_result
        assert channel_id in delete_result["message"]


# =========================================================================
# Webhook Tools Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_list_webhooks_comprehensive():
    """Test list_webhooks tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        result = await session.call_tool(
            "list_webhooks",
            {"channel_id": channel_id},
        )

        assert "webhooks" in result
        assert "channel_id" in result
        assert "count" in result
        assert isinstance(result["webhooks"], list)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_create_webhook_comprehensive(test_prefix, created_resources):
    """Test create_webhook tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]
        webhook_name = f"{test_prefix}-webhook"

        # Create webhook
        result = await session.call_tool(
            "create_webhook",
            {"channel_id": channel_id, "name": webhook_name},
        )

        assert result["webhook_id"] is not None
        assert result["name"] == webhook_name
        assert result["url"] is not None
        assert result["token"] is not None

        # Track for cleanup
        created_resources["webhooks"].append(
            {"webhook_id": result["webhook_id"], "channel_id": channel_id}
        )

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_delete_webhook_comprehensive(test_prefix, created_resources):
    """Test delete_webhook tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]
        webhook_name = f"{test_prefix}-delete-webhook"

        # Create webhook
        create_result = await session.call_tool(
            "create_webhook",
            {"channel_id": channel_id, "name": webhook_name},
        )
        webhook_id = create_result["webhook_id"]

        # Delete webhook
        delete_result = await session.call_tool(
            "delete_webhook",
            {"channel_id": channel_id, "webhook_id": webhook_id},
        )

        assert "message" in delete_result
        assert webhook_id in delete_result["message"]


# =========================================================================
# Channel Name Tools Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_send_message_to_channel_name_comprehensive(created_resources):
    """Test send_message_to_channel_name tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        # First, get a channel name from list_channels
        channels_result = await session.call_tool("list_channels", {})
        if not channels_result["channels"]:
            pytest.skip("No channels available for testing")

        channel_name = channels_result["channels"][0]["name"]
        channel_id = channels_result["channels"][0]["channel_id"]

        # Send message by channel name
        result = await session.call_tool(
            "send_message_to_channel_name",
            {"channel_name": channel_name, "content": "Test message by channel name"},
        )

        assert result["message_id"] is not None
        assert result["channel_id"] == channel_id

        # Track for cleanup
        message_id = result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_get_messages_by_channel_name_comprehensive():
    """Test get_messages_by_channel_name tool."""
    async with start_mcp_server_stdio("discord", config) as session:
        # Get a channel name
        channels_result = await session.call_tool("list_channels", {})
        if not channels_result["channels"]:
            pytest.skip("No channels available for testing")

        channel_name = channels_result["channels"][0]["name"]

        # Get messages by channel name
        result = await session.call_tool(
            "get_messages_by_channel_name",
            {"channel_name": channel_name, "limit": 5},
        )

        assert "messages" in result
        assert "count" in result
        assert isinstance(result["messages"], list)


# =========================================================================
# Error Handling Tests
# =========================================================================


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_channel_not_found_error():
    """Test error handling for non-existent channel."""
    async with start_mcp_server_stdio("discord", config) as session:
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "send_message",
                {"channel_id": "999999999999999999", "content": "Test"},
            )

        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_message_not_found_error():
    """Test error handling for non-existent message."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": "999999999999999999"},
            )

        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_invalid_channel_name_error():
    """Test error handling for invalid channel name."""
    async with start_mcp_server_stdio("discord", config) as session:
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "send_message_to_channel_name",
                {"channel_name": "nonexistent-channel-xyz", "content": "Test"},
            )

        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg
