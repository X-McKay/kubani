"""Tests for DiscordMCPClient."""

import httpx
import pytest

from kubani.framework.mcp.client import DiscordMCPClient


class TestDiscordMCPClientMessaging:
    """Test Discord messaging operations"""

    @pytest.mark.asyncio
    async def test_send_message(self, respx_mock):
        """send_message should post message to Discord channel"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"message_id": "msg-123", "channel_id": "ch-456"}},
            )
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.send_message(channel_id="ch-456", content="Test message")

        assert response.success is True
        assert response.data["message_id"] == "msg-123"
        await client.close()

    @pytest.mark.asyncio
    async def test_send_embed(self, respx_mock):
        """send_embed should post rich embed to Discord channel"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"message_id": "msg-124", "channel_id": "ch-456"}},
            )
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.send_embed(
            channel_id="ch-456",
            title="Test Alert",
            description="Test description",
            color=0xFF0000,
        )

        assert response.success is True
        assert response.data["message_id"] == "msg-124"
        await client.close()


class TestDiscordMCPClientReactions:
    """Test Discord reaction operations"""

    @pytest.mark.asyncio
    async def test_add_reaction(self, respx_mock):
        """add_reaction should add emoji to message"""
        respx_mock.post("http://localhost:8084/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"success": True}})
        )

        client = DiscordMCPClient("discord", "http://localhost:8084")
        response = await client.add_reaction(channel_id="ch-456", message_id="msg-123", emoji="✅")

        assert response.success is True
        await client.close()
