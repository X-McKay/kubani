"""
Pydantic models for Discord MCP server tool inputs and outputs.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# =============================================================================
# Embed Models (for rich messages)
# =============================================================================


class EmbedField(BaseModel):
    """A field in a Discord embed."""

    name: str = Field(..., description="Field name/title")
    value: str = Field(..., description="Field content")
    inline: bool = Field(default=False, description="Display inline with other fields")


class EmbedModel(BaseModel):
    """Discord embed for rich message formatting."""

    title: str | None = Field(default=None, description="Embed title")
    description: str | None = Field(default=None, description="Embed description")
    color: int | None = Field(default=None, description="Embed color as integer (e.g., 0x5865F2)")
    url: str | None = Field(default=None, description="URL for the title")
    timestamp: datetime | None = Field(default=None, description="Timestamp to display")
    footer: str | None = Field(default=None, description="Footer text")
    thumbnail_url: str | None = Field(default=None, description="Thumbnail image URL")
    image_url: str | None = Field(default=None, description="Main image URL")
    author_name: str | None = Field(default=None, description="Author name")
    author_url: str | None = Field(default=None, description="Author URL")
    author_icon_url: str | None = Field(default=None, description="Author icon URL")
    fields: list[EmbedField] | None = Field(default=None, description="Embed fields")


# =============================================================================
# Message Models
# =============================================================================


class MessageResult(BaseModel):
    """Result of a message operation."""

    message_id: str = Field(..., description="Discord message ID")
    channel_id: str = Field(..., description="Channel the message is in")
    content: str | None = Field(default=None, description="Message text content")
    author: str = Field(..., description="Message author name")
    author_id: str = Field(..., description="Message author ID")
    created_at: datetime = Field(..., description="When the message was created")
    is_bot: bool = Field(default=False, description="Whether author is a bot")
    has_embeds: bool = Field(default=False, description="Whether message has embeds")
    reply_to: str | None = Field(default=None, description="ID of message this replies to")


class MessagesResult(BaseModel):
    """Result of fetching multiple messages."""

    messages: list[MessageResult] = Field(..., description="List of messages")
    channel_id: str = Field(..., description="Channel the messages are from")
    count: int = Field(..., description="Number of messages returned")


# =============================================================================
# Channel Models
# =============================================================================


class ChannelResult(BaseModel):
    """Result of a channel operation."""

    channel_id: str = Field(..., description="Discord channel ID")
    name: str = Field(..., description="Channel name")
    topic: str | None = Field(default=None, description="Channel topic")
    category: str | None = Field(default=None, description="Parent category name")
    category_id: str | None = Field(default=None, description="Parent category ID")
    position: int = Field(..., description="Channel position in list")


class ChannelsResult(BaseModel):
    """Result of listing channels."""

    channels: list[ChannelResult] = Field(..., description="List of channels")
    guild_id: str = Field(..., description="Guild the channels are in")
    guild_name: str = Field(..., description="Guild name")
    count: int = Field(..., description="Number of channels")


# =============================================================================
# Reaction Models
# =============================================================================


class ReactionInfo(BaseModel):
    """Information about a reaction."""

    emoji: str = Field(..., description="The emoji used")
    count: int = Field(..., description="Total reaction count")
    users: list[str] = Field(..., description="Names of users who reacted (excluding bots)")


class ReactionsResult(BaseModel):
    """Result of getting reactions."""

    message_id: str = Field(..., description="Message ID")
    reactions: list[ReactionInfo] = Field(..., description="List of reactions")


class ReactionWaitResult(BaseModel):
    """Result of waiting for a reaction."""

    emoji: str = Field(..., description="The emoji that was added")
    user: str = Field(..., description="Name of user who reacted")
    message_id: str = Field(..., description="Message ID")


# =============================================================================
# Webhook Models
# =============================================================================


class WebhookResult(BaseModel):
    """Result of a webhook operation."""

    webhook_id: str = Field(..., description="Webhook ID")
    name: str = Field(..., description="Webhook name")
    channel_id: str = Field(..., description="Channel the webhook posts to")
    url: str = Field(..., description="Webhook URL (keep secret!)")
    token: str | None = Field(default=None, description="Webhook token")


class WebhooksResult(BaseModel):
    """Result of listing webhooks."""

    webhooks: list[WebhookResult] = Field(..., description="List of webhooks")
    channel_id: str = Field(..., description="Channel ID")
    count: int = Field(..., description="Number of webhooks")


# =============================================================================
# Common Models
# =============================================================================


class SuccessResult(BaseModel):
    """Generic success result."""

    success: bool = Field(default=True, description="Whether operation succeeded")
    message: str = Field(..., description="Status message")


class ErrorResult(BaseModel):
    """Error result."""

    success: bool = Field(default=False, description="Always false for errors")
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error")
