"""Nexus message models.

Canonical message types used across the Conversational Gateway, Orchestrator,
and all client interfaces (Discord, Kubani UI). These models define the
contract between the user-facing layer and the agent's internal logic.

All timestamps use ISO 8601 format. All IDs are strings to allow for
flexible ID generation strategies (UUID, nanoid, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageSource(str, Enum):
    """The origin of a user message."""

    DISCORD = "discord"
    KUBANI_UI = "kubani-ui"
    SYSTEM = "system"
    TEST = "test"


class MessageRole(str, Enum):
    """The role of a message in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class UserMessage(BaseModel):
    """A message received from a user via the Conversational Gateway.

    This is the canonical inbound message type. The Gateway normalizes
    messages from all sources (Discord, UI, etc.) into this format before
    signaling the Temporal workflow.

    Attributes:
        source: Where the message originated (discord, kubani-ui, etc.).
        user_id: Unique identifier for the user.
        conversation_id: Unique identifier for the conversation session.
        text: The raw text content of the message.
        timestamp: ISO 8601 timestamp of when the message was created.
        metadata: Optional additional data (e.g., Discord channel ID).
    """

    source: MessageSource
    user_id: str
    conversation_id: str
    text: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for Temporal signal payloads."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserMessage:
        """Deserialize from a plain dict (Temporal signal payload)."""
        return cls.model_validate(data)


class AgentMessage(BaseModel):
    """A message sent from the agent back to the user.

    This is the canonical outbound message type. The Orchestrator produces
    these, and the Gateway routes them to the appropriate client.

    Attributes:
        conversation_id: The conversation this message belongs to.
        text: The agent's response text (may contain Markdown).
        timestamp: ISO 8601 timestamp.
        metadata: Optional additional data (e.g., plan summary, action log).
    """

    conversation_id: str
    text: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for Redis pub/sub."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMessage:
        """Deserialize from a plain dict."""
        return cls.model_validate(data)


class ConversationMessage(BaseModel):
    """A unified message type for conversation history storage.

    Used for persisting messages to the database and for building
    the LLM context window.
    """

    role: MessageRole
    content: str
    source: MessageSource = MessageSource.SYSTEM
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
