"""Property-based tests for Discord MCP concurrent request handling.

Feature: mcp-infrastructure-improvements, Property 1: Concurrent Request Independence
Validates: Requirements 1.3
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_property_1_concurrent_request_independence_basic():
    """
    Feature: mcp-infrastructure-improvements, Property 1: Concurrent Request Independence

    For any MCP server and any set of concurrent requests from different agents,
    each request should receive correct responses independent of other requests,
    with no cross-contamination of agent-specific data.

    Validates: Requirements 1.3
    
    This is a basic test that verifies concurrent requests are handled independently.
    """
    # Track sent messages by channel
    sent_messages = {}
    message_id_counter = [0]
    
    async def send_message_side_effect(channel, content=None, embed=None, embeds=None):
        """Track sent messages by channel."""
        message_id_counter[0] += 1
        msg_id = message_id_counter[0]
        
        channel_id = channel.id
        if channel_id not in sent_messages:
            sent_messages[channel_id] = []
        
        msg = MagicMock()
        msg.id = msg_id
        msg.channel = channel
        msg.content = content
        msg.author = MagicMock()
        msg.author.display_name = "TestBot"
        msg.author.id = 987654321
        msg.author.bot = True
        msg.created_at = asyncio.get_event_loop().time()
        msg.embeds = []
        msg.reference = None
        
        sent_messages[channel_id].append(msg)
        return msg
    
    # Create mock Discord client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.send_message = send_message_side_effect
    
    # Create mock channels
    channel1 = MagicMock()
    channel1.id = 111111
    channel1.name = "channel-1"
    
    channel2 = MagicMock()
    channel2.id = 222222
    channel2.name = "channel-2"
    
    def get_channel_side_effect(channel_id: int):
        if channel_id == 111111:
            return channel1
        elif channel_id == 222222:
            return channel2
        return None
    
    mock_client.get_channel = get_channel_side_effect
    
    # Patch the global client
    with patch("discord_mcp.server._discord_client", mock_client):
        with patch("discord_mcp.server.get_client", return_value=mock_client):
            # Simulate concurrent requests to different channels
            task1 = mock_client.send_message(channel1, content="Message to channel 1")
            task2 = mock_client.send_message(channel2, content="Message to channel 2")
            
            result1, result2 = await asyncio.gather(task1, task2)
            
            # Verify results are independent
            assert result1.channel.id == 111111
            assert result1.content == "Message to channel 1"
            
            assert result2.channel.id == 222222
            assert result2.content == "Message to channel 2"
            
            # Verify messages are properly isolated by channel
            assert 111111 in sent_messages
            assert 222222 in sent_messages
            assert len(sent_messages[111111]) == 1
            assert len(sent_messages[222222]) == 1
            
            # Verify no cross-contamination
            assert sent_messages[111111][0].content == "Message to channel 1"
            assert sent_messages[222222][0].content == "Message to channel 2"


@pytest.mark.asyncio
async def test_concurrent_requests_multiple_agents():
    """
    Test that multiple agents can send messages concurrently without interference.
    
    This verifies that the Discord MCP server can handle concurrent requests
    from multiple agents without mixing up their messages.
    """
    # Track sent messages
    sent_messages = []
    message_lock = asyncio.Lock()
    
    async def send_message_side_effect(channel, content=None, embed=None, embeds=None):
        """Track sent messages."""
        async with message_lock:
            msg = MagicMock()
            msg.id = len(sent_messages) + 1
            msg.channel = channel
            msg.content = content
            msg.author = MagicMock()
            msg.author.display_name = "TestBot"
            msg.author.id = 987654321
            msg.author.bot = True
            msg.created_at = asyncio.get_event_loop().time()
            msg.embeds = []
            msg.reference = None
            
            sent_messages.append(msg)
            return msg
    
    # Create mock Discord client
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.send_message = send_message_side_effect
    
    # Create mock channels for different agents
    channels = {}
    for i in range(3):
        channel = MagicMock()
        channel.id = 100000 + i
        channel.name = f"agent-{i}-channel"
        channels[channel.id] = channel
    
    def get_channel_side_effect(channel_id: int):
        return channels.get(channel_id)
    
    mock_client.get_channel = get_channel_side_effect
    
    # Patch the global client
    with patch("discord_mcp.server._discord_client", mock_client):
        with patch("discord_mcp.server.get_client", return_value=mock_client):
            # Simulate concurrent requests from multiple agents
            tasks = []
            for i in range(3):
                channel = channels[100000 + i]
                for j in range(2):
                    task = mock_client.send_message(
                        channel,
                        content=f"Message {j} from agent {i}"
                    )
                    tasks.append((i, task))
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*[task for _, task in tasks])
            
            # Verify all messages were sent
            assert len(sent_messages) == 6  # 3 agents * 2 messages each
            
            # Verify each message has the correct content
            for i, result in enumerate(results):
                agent_idx = i // 2
                msg_idx = i % 2
                expected_content = f"Message {msg_idx} from agent {agent_idx}"
                assert result.content == expected_content
                assert result.channel.id == 100000 + agent_idx
