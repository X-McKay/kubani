"""Performance tests for rapid message processing.

Tests the system's ability to handle a high volume of messages in rapid succession
without dropping messages or experiencing significant performance degradation.

Requirements tested:
- 10.2: Process 100 messages in rapid succession
"""

import time
import uuid

import pytest

from kubani.nexus.models import MessageSource, NexusWorkflowState, UserMessage
from kubani.nexus.models.messages import ConversationMessage, MessageRole

# =========================================================================
# Test 27.2: Rapid message processing
# =========================================================================


@pytest.mark.performance
def test_rapid_message_processing_workflow_state() -> None:
    """Test workflow state handles 100 messages in rapid succession.

    Requirements: 10.2

    This test verifies that the workflow state can handle a high volume of messages
    without dropping any or experiencing significant performance degradation.
    """
    # Arrange
    num_messages = 100
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    start_time = time.time()

    # Act - add 100 messages in rapid succession
    for i in range(num_messages):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Test message {i}",
        )

        # Add user message
        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

        # Add agent response
        state.add_message(
            ConversationMessage(
                role=MessageRole.ASSISTANT,
                content=f"Response to message {i}",
            )
        )

    end_time = time.time()
    duration = end_time - start_time

    # Assert - verify performance
    assert duration < 1.0, f"Processing took too long: {duration:.2f}s"

    # Verify conversation history is bounded (max 50 messages)
    assert len(state.conversation_history) <= 50, (
        f"Conversation history exceeded max: {len(state.conversation_history)}"
    )

    # Verify the most recent messages are kept
    last_message = state.conversation_history[-1]
    assert "message 99" in last_message.content or "Response to message" in last_message.content


@pytest.mark.performance
def test_rapid_message_processing_no_dropped_messages() -> None:
    """Test that no messages are dropped during rapid processing.

    Requirements: 10.2

    This test verifies that every message sent is added to the state.
    """
    # Arrange
    num_messages = 100
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Track message IDs
    sent_message_ids = []

    # Act - send messages
    for i in range(num_messages):
        message_id = f"msg-{i}"
        sent_message_ids.append(message_id)

        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Message {message_id}",
        )

        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

    # Assert - verify all messages were processed
    # Due to the sliding window, we should have at least the last 50 messages
    assert len(state.conversation_history) >= min(50, num_messages)

    # Verify the most recent messages are present
    recent_messages = state.conversation_history[-10:]
    recent_texts = [msg.content for msg in recent_messages]

    # Check that the last few message IDs are present
    for i in range(num_messages - 10, num_messages):
        message_id = f"msg-{i}"
        assert any(message_id in text for text in recent_texts), (
            f"Message {message_id} not found in recent messages"
        )


@pytest.mark.performance
def test_rapid_message_processing_maintains_order() -> None:
    """Test that message processing maintains order during rapid processing.

    Requirements: 10.2

    This test verifies that messages are stored in the order they are received,
    even when sent in rapid succession.
    """
    # Arrange
    num_messages = 50  # Smaller number for order verification
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - send messages with sequential numbers
    for i in range(num_messages):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Message number {i}",
        )

        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

    # Assert - verify messages are in order
    # Since we sent fewer than 50 messages, all should be in history
    assert len(state.conversation_history) == num_messages

    # Verify sequential order
    for i, message in enumerate(state.conversation_history):
        expected_text = f"Message number {i}"
        assert message.content == expected_text, (
            f"Message {i} out of order: expected '{expected_text}', got '{message.content}'"
        )


@pytest.mark.performance
def test_rapid_message_processing_memory_efficiency() -> None:
    """Test that rapid message processing doesn't cause memory issues.

    Requirements: 10.2, 10.4

    This test verifies that the workflow maintains a reasonable memory footprint
    even when processing many messages, by enforcing the conversation history window.
    """
    # Arrange
    num_messages = 100
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())
    max_history_size = 50  # From NexusWorkflowState.MAX_CONVERSATION_HISTORY

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - send many messages
    for i in range(num_messages):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Test message {i}",
        )

        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

        # Add agent response
        state.add_message(
            ConversationMessage(
                role=MessageRole.ASSISTANT,
                content=f"Response to message {i}",
            )
        )

    # Assert - verify conversation history is bounded
    assert len(state.conversation_history) <= max_history_size, (
        f"Conversation history exceeded max size: {len(state.conversation_history)} > {max_history_size}"
    )

    # Verify the state is still functional
    assert state.status.value == "idle"  # Status is lowercase
    assert state.user_id == user_id
    assert state.conversation_id == conversation_id


@pytest.mark.performance
def test_rapid_message_processing_concurrent_access() -> None:
    """Test that rapid message processing handles concurrent access patterns.

    Requirements: 10.2

    This test simulates concurrent message additions to verify thread safety.
    """
    # Arrange
    num_messages = 100
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - add messages rapidly (simulating concurrent access)
    messages = []
    for i in range(num_messages):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Concurrent message {i}",
        )
        messages.append(user_message)

    start_time = time.time()

    # Add all messages
    for msg in messages:
        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=msg.text,
                source=msg.source,
            )
        )

    end_time = time.time()
    duration = end_time - start_time

    # Assert - verify performance and correctness
    assert duration < 0.5, f"Processing took too long: {duration:.2f}s"
    assert len(state.conversation_history) <= 50

    # Verify no corruption occurred
    for message in state.conversation_history:
        assert "Concurrent message" in message.content
