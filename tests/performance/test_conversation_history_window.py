"""Performance tests for conversation history window.

Tests that the conversation history window is properly maintained and bounded.

Requirements tested:
- 10.4: Conversation history window maintenance
"""

import time
import uuid

import pytest

from kubani.nexus.models import MessageSource, NexusWorkflowState, UserMessage
from kubani.nexus.models.messages import ConversationMessage, MessageRole

# =========================================================================
# Test 27.4: Conversation history window
# =========================================================================


@pytest.mark.performance
def test_conversation_history_window_bounded() -> None:
    """Test that conversation history is bounded to 50 messages.

    Requirements: 10.4

    This test verifies that when adding 100 messages to workflow state,
    only the last 50 are kept in memory.
    """
    # Arrange
    num_messages = 100
    max_history_size = 50  # From NexusWorkflowState.MAX_CONVERSATION_HISTORY
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - add 100 messages
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

    # Assert - verify history is bounded
    assert len(state.conversation_history) <= max_history_size, (
        f"Conversation history exceeded max size: {len(state.conversation_history)} > {max_history_size}"
    )

    # Verify the most recent messages are kept
    last_message = state.conversation_history[-1]
    assert "message 99" in last_message.content


@pytest.mark.performance
def test_conversation_history_window_with_mixed_messages() -> None:
    """Test conversation history window with user and agent messages.

    Requirements: 10.4

    This test verifies that the window works correctly with both
    user messages and agent responses.
    """
    # Arrange
    num_conversations = 50  # 50 user messages + 50 agent responses = 100 total
    max_history_size = 50
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - add user messages and agent responses
    for i in range(num_conversations):
        # Add user message
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"User message {i}",
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
                content=f"Agent response {i}",
            )
        )

    # Assert - verify history is bounded
    assert len(state.conversation_history) <= max_history_size, (
        f"Conversation history exceeded max size: {len(state.conversation_history)} > {max_history_size}"
    )

    # Verify we have a mix of user and agent messages
    user_messages = [m for m in state.conversation_history if m.role == MessageRole.USER]
    agent_messages = [m for m in state.conversation_history if m.role == MessageRole.ASSISTANT]

    assert len(user_messages) > 0, "Should have user messages"
    assert len(agent_messages) > 0, "Should have agent messages"


@pytest.mark.performance
def test_conversation_history_window_sliding() -> None:
    """Test that conversation history window slides correctly.

    Requirements: 10.4

    This test verifies that as new messages are added, old messages
    are removed to maintain the window size.
    """
    # Arrange
    max_history_size = 50
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - add messages in batches
    # First batch: messages 0-49
    for i in range(50):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Message {i}",
        )
        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

    # Verify first batch
    assert len(state.conversation_history) == 50
    assert "Message 0" in state.conversation_history[0].content

    # Second batch: messages 50-99
    for i in range(50, 100):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Message {i}",
        )
        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

    # Assert - verify window slid
    assert len(state.conversation_history) == max_history_size

    # First message should now be message 50 (message 0-49 were removed)
    assert "Message 50" in state.conversation_history[0].content

    # Last message should be message 99
    assert "Message 99" in state.conversation_history[-1].content


@pytest.mark.performance
def test_conversation_history_window_performance() -> None:
    """Test that maintaining the window doesn't degrade performance.

    Requirements: 10.4

    This test verifies that adding messages and maintaining the window
    is performant even with many messages.
    """
    # Arrange
    num_messages = 1000  # Large number to test performance
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    start_time = time.time()

    # Act - add many messages
    for i in range(num_messages):
        user_message = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id=user_id,
            conversation_id=conversation_id,
            text=f"Message {i}",
        )
        state.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=user_message.text,
                source=user_message.source,
            )
        )

    end_time = time.time()
    duration = end_time - start_time

    # Assert - verify performance
    # Adding 1000 messages should be fast (< 1 second)
    assert duration < 1.0, f"Adding messages took too long: {duration:.2f}s"

    # Verify history is still bounded
    assert len(state.conversation_history) <= 50


@pytest.mark.performance
def test_conversation_history_window_memory_efficiency() -> None:
    """Test that the window prevents unbounded memory growth.

    Requirements: 10.4

    This test verifies that the conversation history doesn't grow
    unbounded, preventing memory issues.
    """
    # Arrange
    user_id = "test-user"
    conversation_id = str(uuid.uuid4())

    state = NexusWorkflowState(user_id=user_id, conversation_id=conversation_id)

    # Act - add messages in multiple rounds
    for round_num in range(10):
        for i in range(100):
            user_message = UserMessage(
                source=MessageSource.KUBANI_UI,
                user_id=user_id,
                conversation_id=conversation_id,
                text=f"Round {round_num}, Message {i}",
            )
            state.add_message(
                ConversationMessage(
                    role=MessageRole.USER,
                    content=user_message.text,
                    source=user_message.source,
                )
            )

        # Assert - verify history is bounded after each round
        assert len(state.conversation_history) <= 50, (
            f"History grew unbounded in round {round_num}: {len(state.conversation_history)}"
        )

    # Final verification
    assert len(state.conversation_history) <= 50

    # Verify we have messages from the last round only
    last_message = state.conversation_history[-1]
    assert "Round 9" in last_message.content
