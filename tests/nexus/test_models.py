"""Tests for the Nexus data models.

These tests validate serialization, deserialization, and validation
of all message and state models. No external dependencies required.
"""

from __future__ import annotations

import pytest

from kubani.nexus.models.messages import (
    AgentMessage,
    ConversationMessage,
    MessageRole,
    MessageSource,
    UserMessage,
)
from kubani.nexus.models.skills import SkillExecutionResult, SkillMetadata
from kubani.nexus.models.state import (
    ExecutionPlan,
    NexusStatus,
    NexusWorkflowState,
    PlanStep,
)


class TestUserMessage:
    """Test UserMessage model."""

    def test_create_basic(self):
        msg = UserMessage(
            source=MessageSource.KUBANI_UI,
            user_id="user-1",
            conversation_id="conv-1",
            text="Hello!",
        )
        assert msg.source == MessageSource.KUBANI_UI
        assert msg.user_id == "user-1"
        assert msg.text == "Hello!"
        assert msg.timestamp is not None

    def test_serialization_roundtrip(self):
        msg = UserMessage(
            source=MessageSource.DISCORD,
            user_id="discord-123",
            conversation_id="conv-2",
            text="Test message",
            metadata={"channel_id": "456"},
        )
        data = msg.to_dict()
        restored = UserMessage.from_dict(data)
        assert restored.source == msg.source
        assert restored.user_id == msg.user_id
        assert restored.text == msg.text
        assert restored.metadata == msg.metadata

    def test_source_enum_values(self):
        assert MessageSource.DISCORD.value == "discord"
        assert MessageSource.KUBANI_UI.value == "kubani-ui"
        assert MessageSource.SYSTEM.value == "system"
        assert MessageSource.TEST.value == "test"


class TestAgentMessage:
    """Test AgentMessage model."""

    def test_create_basic(self):
        msg = AgentMessage(
            conversation_id="conv-1",
            text="Hello, I'm Nexus!",
        )
        assert msg.conversation_id == "conv-1"
        assert msg.text == "Hello, I'm Nexus!"

    def test_serialization_roundtrip(self):
        msg = AgentMessage(
            conversation_id="conv-1",
            text="Response text",
            metadata={"plan_id": "plan-1"},
        )
        data = msg.to_dict()
        restored = AgentMessage.from_dict(data)
        assert restored.text == msg.text
        assert restored.metadata == msg.metadata


class TestConversationMessage:
    """Test ConversationMessage model."""

    def test_create_user_message(self):
        msg = ConversationMessage(
            role=MessageRole.USER,
            content="What's the weather?",
            source=MessageSource.KUBANI_UI,
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "What's the weather?"

    def test_create_assistant_message(self):
        msg = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content="The weather is sunny.",
            source=MessageSource.SYSTEM,
        )
        assert msg.role == MessageRole.ASSISTANT


class TestNexusWorkflowState:
    """Test NexusWorkflowState model."""

    def test_initial_state(self):
        state = NexusWorkflowState(user_id="user-1")
        assert state.status == NexusStatus.IDLE
        assert state.user_id == "user-1"
        assert len(state.conversation_history) == 0
        assert state.actions_count == 0

    def test_add_message(self):
        state = NexusWorkflowState(user_id="user-1")
        msg = ConversationMessage(
            role=MessageRole.USER,
            content="Hello",
        )
        state.add_message(msg)
        assert len(state.conversation_history) == 1
        assert state.conversation_history[0].content == "Hello"

    def test_history_limit(self):
        state = NexusWorkflowState(user_id="user-1")
        for i in range(60):
            state.add_message(ConversationMessage(
                role=MessageRole.USER,
                content=f"Message {i}",
            ))
        # Should be capped at 50
        assert len(state.conversation_history) == 50

    def test_to_dict(self):
        state = NexusWorkflowState(user_id="user-1")
        state.status = NexusStatus.PLANNING
        state.current_goal = "Research topic X"
        data = state.to_dict()
        assert data["status"] == "planning"
        assert data["current_goal"] == "Research topic X"


class TestExecutionPlan:
    """Test ExecutionPlan model."""

    def test_create_plan(self):
        plan = ExecutionPlan(
            goal="Fetch and summarize news",
            steps=[
                PlanStep(id=1, description="Fetch RSS feed", skill_name="web/fetch-rss"),
                PlanStep(id=2, description="Summarize content", skill_name="text/summarize"),
            ],
        )
        assert plan.goal == "Fetch and summarize news"
        assert len(plan.steps) == 2
        assert plan.steps[0].skill_name == "web/fetch-rss"

    def test_step_status_lifecycle(self):
        step = PlanStep(id=1, description="Test step")
        assert step.status == "pending"

        step.status = "running"
        assert step.status == "running"

        step.status = "completed"
        step.result_summary = "Done"
        assert step.status == "completed"


class TestSkillModels:
    """Test skill-related models."""

    def test_skill_metadata(self):
        meta = SkillMetadata(
            name="web/fetch-url",
            version="0.1.0",
            description="Fetch content from a URL",
            author="nexus-synthesizer",
        )
        assert meta.name == "web/fetch-url"
        assert meta.version == "0.1.0"

    def test_skill_execution_result_success(self):
        result = SkillExecutionResult(
            skill_name="web/fetch-url",
            success=True,
            output="Fetched 1024 bytes",
            exit_code=0,
            duration_ms=150,
        )
        assert result.success is True
        assert result.duration_ms == 150

    def test_skill_execution_result_failure(self):
        result = SkillExecutionResult(
            skill_name="web/fetch-url",
            success=False,
            error="Connection timeout",
            exit_code=1,
            duration_ms=5000,
        )
        assert result.success is False
        assert result.error == "Connection timeout"
