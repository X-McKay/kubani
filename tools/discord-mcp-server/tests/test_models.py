"""Tests for Discord MCP models."""

from datetime import UTC, datetime

from discord_mcp.models import (
    ChannelResult,
    EmbedField,
    EmbedModel,
    MessageResult,
    ReactionInfo,
    SuccessResult,
    WebhookResult,
)


class TestEmbedModel:
    """Tests for EmbedModel."""

    def test_minimal_embed(self):
        """Test creating a minimal embed."""
        embed = EmbedModel(title="Test")
        assert embed.title == "Test"
        assert embed.description is None
        assert embed.color is None

    def test_full_embed(self):
        """Test creating a fully populated embed."""
        embed = EmbedModel(
            title="Test Title",
            description="Test description",
            color=0x5865F2,
            url="https://example.com",
            timestamp=datetime.now(UTC),
            footer="Footer text",
            thumbnail_url="https://example.com/thumb.png",
            image_url="https://example.com/image.png",
            author_name="Author",
            author_url="https://example.com/author",
            fields=[
                EmbedField(name="Field 1", value="Value 1", inline=True),
                EmbedField(name="Field 2", value="Value 2"),
            ],
        )
        assert embed.title == "Test Title"
        assert embed.color == 0x5865F2
        assert len(embed.fields) == 2
        assert embed.fields[0].inline is True
        assert embed.fields[1].inline is False


class TestMessageResult:
    """Tests for MessageResult."""

    def test_message_result(self):
        """Test creating a message result."""
        result = MessageResult(
            message_id=123456789,
            channel_id=987654321,
            content="Hello world",
            author="TestUser",
            author_id=111222333,
            created_at=datetime.now(UTC),
            is_bot=False,
            has_embeds=False,
        )
        assert result.message_id == 123456789
        assert result.content == "Hello world"
        assert result.is_bot is False

    def test_message_result_with_reply(self):
        """Test message result with reply reference."""
        result = MessageResult(
            message_id=123456789,
            channel_id=987654321,
            content="This is a reply",
            author="TestUser",
            author_id=111222333,
            created_at=datetime.now(UTC),
            reply_to=123456780,
        )
        assert result.reply_to == 123456780


class TestChannelResult:
    """Tests for ChannelResult."""

    def test_channel_result(self):
        """Test creating a channel result."""
        result = ChannelResult(
            channel_id=123456789,
            name="general",
            topic="General discussion",
            category="Text Channels",
            category_id=111222333,
            position=0,
        )
        assert result.name == "general"
        assert result.category == "Text Channels"


class TestReactionInfo:
    """Tests for ReactionInfo."""

    def test_reaction_info(self):
        """Test creating reaction info."""
        info = ReactionInfo(
            emoji="✅",
            count=3,
            users=["User1", "User2", "User3"],
        )
        assert info.emoji == "✅"
        assert info.count == 3
        assert len(info.users) == 3


class TestWebhookResult:
    """Tests for WebhookResult."""

    def test_webhook_result(self):
        """Test creating a webhook result."""
        result = WebhookResult(
            webhook_id=123456789,
            name="Test Webhook",
            channel_id=987654321,
            url="https://discord.com/api/webhooks/123/abc",
            token="abc123",
        )
        assert result.name == "Test Webhook"
        assert "webhooks" in result.url


class TestSuccessResult:
    """Tests for SuccessResult."""

    def test_success_result(self):
        """Test creating a success result."""
        result = SuccessResult(message="Operation completed")
        assert result.success is True
        assert result.message == "Operation completed"
