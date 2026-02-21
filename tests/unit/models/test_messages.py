"""Unit tests for Nexus message models.

This module tests the message models used across the Nexus system:
- UserMessage: Inbound messages from users
- AgentMessage: Outbound messages from the agent
- ConversationMessage: Unified message type for history storage

Tests include:
- Property-based tests for serialization round-trips
- Validation tests for enum values
- Timestamp generation tests
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from kubani.nexus.models.messages import (
    AgentMessage,
    ConversationMessage,
    MessageRole,
    MessageSource,
    UserMessage,
)
from tests.utils.helpers import assert_iso8601_timestamp


# Hypothesis strategies for generating test data
@st.composite
def user_messages(draw):
    """Generate random UserMessage instances for property-based testing."""
    return UserMessage(
        source=draw(st.sampled_from(MessageSource)),
        user_id=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\x00"))),
        conversation_id=draw(st.uuids().map(str)),
        text=draw(st.text(min_size=1, max_size=1000, alphabet=st.characters(blacklist_characters="\x00"))),
        metadata=draw(st.dictionaries(
            st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
            st.one_of(st.text(max_size=100), st.integers(), st.booleans()),
            max_size=5
        ))
    )


@st.composite
def agent_messages(draw):
    """Generate random AgentMessage instances for property-based testing."""
    return AgentMessage(
        conversation_id=draw(st.uuids().map(str)),
        text=draw(st.text(min_size=1, max_size=1000, alphabet=st.characters(blacklist_characters="\x00"))),
        metadata=draw(st.dictionaries(
            st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
            st.one_of(st.text(max_size=100), st.integers(), st.booleans()),
            max_size=5
        ))
    )


@st.composite
def conversation_messages(draw):
    """Generate random ConversationMessage instances for property-based testing."""
    return ConversationMessage(
        role=draw(st.sampled_from(MessageRole)),
        content=draw(st.text(min_size=1, max_size=1000, alphabet=st.characters(blacklist_characters="\x00"))),
        source=draw(st.sampled_from(MessageSource)),
        metadata=draw(st.dictionaries(
            st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_characters="\x00")),
            st.one_of(st.text(max_size=100), st.integers(), st.booleans()),
            max_size=5
        ))
    )


class TestUserMessage:
    """Tests for UserMessage model."""

    @given(message=user_messages())
    def test_property_1_user_message_serialization_round_trip(self, message):
        """
        Feature: nexus-testing, Property 1: Message serialization round-trip
        
        For any valid UserMessage, serializing to dict and deserializing back
        should produce an equivalent object.
        
        Validates: Requirements 1.1
        """
        # Serialize to dict
        message_dict = message.to_dict()
        
        # Verify it's a dict
        assert isinstance(message_dict, dict)
        
        # Deserialize back
        restored_message = UserMessage.from_dict(message_dict)
        
        # Verify equivalence
        assert restored_message.source == message.source
        assert restored_message.user_id == message.user_id
        assert restored_message.conversation_id == message.conversation_id
        assert restored_message.text == message.text
        assert restored_message.timestamp == message.timestamp
        assert restored_message.metadata == message.metadata

    def test_user_message_validation_invalid_source(self):
        """
        Test that UserMessage validation rejects invalid MessageSource values.
        
        Validates: Requirements 1.2
        """
        # Attempt to create UserMessage with invalid source
        with pytest.raises(ValidationError) as exc_info:
            UserMessage(
                source="invalid_source",  # Invalid enum value
                user_id="test-user",
                conversation_id="test-conv",
                text="Hello"
            )
        
        # Verify the error is about the source field
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("source" in str(error) for error in errors)

    def test_user_message_timestamp_auto_generation(self):
        """
        Test that UserMessage auto-generates timestamp when not provided.
        
        Validates: Requirements 1.3
        """
        message = UserMessage(
            source=MessageSource.TEST,
            user_id="test-user",
            conversation_id="test-conv",
            text="Hello"
        )
        
        # Verify timestamp was auto-generated
        assert message.timestamp is not None
        assert isinstance(message.timestamp, str)
        
        # Verify it's in ISO 8601 format
        assert_iso8601_timestamp(message.timestamp)

    def test_user_message_default_metadata(self):
        """Test that UserMessage has empty dict as default metadata."""
        message = UserMessage(
            source=MessageSource.TEST,
            user_id="test-user",
            conversation_id="test-conv",
            text="Hello"
        )
        
        assert message.metadata == {}
        assert isinstance(message.metadata, dict)

    def test_user_message_with_custom_timestamp(self):
        """Test that UserMessage accepts custom timestamp."""
        custom_timestamp = "2024-01-15T10:30:00Z"
        message = UserMessage(
            source=MessageSource.TEST,
            user_id="test-user",
            conversation_id="test-conv",
            text="Hello",
            timestamp=custom_timestamp
        )
        
        assert message.timestamp == custom_timestamp


class TestAgentMessage:
    """Tests for AgentMessage model."""

    @given(message=agent_messages())
    def test_property_1_agent_message_serialization_round_trip(self, message):
        """
        Feature: nexus-testing, Property 1: Message serialization round-trip
        
        For any valid AgentMessage, serializing to dict and deserializing back
        should produce an equivalent object.
        
        Validates: Requirements 1.1
        """
        # Serialize to dict
        message_dict = message.to_dict()
        
        # Verify it's a dict
        assert isinstance(message_dict, dict)
        
        # Deserialize back
        restored_message = AgentMessage.from_dict(message_dict)
        
        # Verify equivalence
        assert restored_message.conversation_id == message.conversation_id
        assert restored_message.text == message.text
        assert restored_message.timestamp == message.timestamp
        assert restored_message.metadata == message.metadata

    @given(message=agent_messages())
    def test_agent_message_timestamp_generation(self, message):
        """
        Test that AgentMessage has valid ISO 8601 timestamp.
        
        Validates: Requirements 1.3
        """
        # Verify timestamp is present
        assert message.timestamp is not None
        assert isinstance(message.timestamp, str)
        
        # Verify it's in ISO 8601 format
        assert_iso8601_timestamp(message.timestamp)

    def test_agent_message_default_metadata(self):
        """Test that AgentMessage has empty dict as default metadata."""
        message = AgentMessage(
            conversation_id="test-conv",
            text="Hello from agent"
        )
        
        assert message.metadata == {}
        assert isinstance(message.metadata, dict)


class TestConversationMessage:
    """Tests for ConversationMessage model."""

    @given(message=conversation_messages())
    def test_property_1_conversation_message_serialization_round_trip(self, message):
        """
        Feature: nexus-testing, Property 1: Message serialization round-trip
        
        For any valid ConversationMessage, serializing to dict and deserializing back
        should produce an equivalent object.
        
        Validates: Requirements 1.1
        """
        # Serialize to dict
        message_dict = message.model_dump(mode="json")
        
        # Verify it's a dict
        assert isinstance(message_dict, dict)
        
        # Deserialize back
        restored_message = ConversationMessage.model_validate(message_dict)
        
        # Verify equivalence
        assert restored_message.role == message.role
        assert restored_message.content == message.content
        assert restored_message.source == message.source
        assert restored_message.timestamp == message.timestamp
        assert restored_message.metadata == message.metadata

    def test_conversation_message_validation_invalid_role(self):
        """
        Test that ConversationMessage validation rejects invalid MessageRole values.
        
        Validates: Requirements 1.2
        """
        # Attempt to create ConversationMessage with invalid role
        with pytest.raises(ValidationError) as exc_info:
            ConversationMessage(
                role="invalid_role",  # Invalid enum value
                content="Hello"
            )
        
        # Verify the error is about the role field
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("role" in str(error) for error in errors)

    @given(message=conversation_messages())
    def test_conversation_message_timestamp_generation(self, message):
        """
        Test that ConversationMessage has valid ISO 8601 timestamp.
        
        Validates: Requirements 1.3
        """
        # Verify timestamp is present
        assert message.timestamp is not None
        assert isinstance(message.timestamp, str)
        
        # Verify it's in ISO 8601 format
        assert_iso8601_timestamp(message.timestamp)

    def test_conversation_message_default_source(self):
        """Test that ConversationMessage defaults to SYSTEM source."""
        message = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content="Hello"
        )
        
        assert message.source == MessageSource.SYSTEM


class TestMessageEnums:
    """Tests for message enum types."""

    def test_message_source_values(self):
        """Test that MessageSource has expected values."""
        assert MessageSource.DISCORD == "discord"
        assert MessageSource.KUBANI_UI == "kubani-ui"
        assert MessageSource.SYSTEM == "system"
        assert MessageSource.TEST == "test"

    def test_message_role_values(self):
        """Test that MessageRole has expected values."""
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"
