"""Unit tests for Nexus state models.

This module tests the state models used in the Nexus workflow:
- NexusWorkflowState: The complete queryable state of the workflow
- ExecutionPlan: A versioned execution plan with steps
- PlanStep: Individual steps in an execution plan

Tests include:
- Property-based tests for message window management
- Property-based tests for execution plan state consistency
- Validation tests for state transitions
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kubani.nexus.models.messages import ConversationMessage, MessageRole, MessageSource
from kubani.nexus.models.state import (
    ExecutionPlan,
    NexusStatus,
    NexusWorkflowState,
    PlanStep,
)


# Hypothesis strategies for generating test data
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


@st.composite
def plan_steps(draw):
    """Generate random PlanStep instances for property-based testing."""
    return PlanStep(
        id=draw(st.integers(min_value=0, max_value=1000)),
        description=draw(st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_characters="\x00"))),
        skill_name=draw(st.one_of(
            st.none(),
            st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\x00"))
        )),
        status=draw(st.sampled_from(["pending", "running", "completed", "failed", "skipped"])),
        result_summary=draw(st.one_of(
            st.none(),
            st.text(max_size=200, alphabet=st.characters(blacklist_characters="\x00"))
        )),
        error=draw(st.one_of(
            st.none(),
            st.text(max_size=200, alphabet=st.characters(blacklist_characters="\x00"))
        )),
    )


@st.composite
def execution_plans(draw):
    """Generate random ExecutionPlan instances for property-based testing."""
    num_steps = draw(st.integers(min_value=1, max_value=20))
    steps = [draw(plan_steps()) for _ in range(num_steps)]
    # Ensure unique IDs
    for i, step in enumerate(steps):
        step.id = i
    
    return ExecutionPlan(
        version=draw(st.integers(min_value=1, max_value=100)),
        goal=draw(st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_characters="\x00"))),
        steps=steps,
    )


class TestNexusWorkflowState:
    """Tests for NexusWorkflowState model."""

    @given(messages=st.lists(conversation_messages(), min_size=0, max_size=100))
    def test_property_2_workflow_state_message_window(self, messages):
        """
        Feature: nexus-testing, Property 2: Workflow state message window
        
        For any sequence of messages added to NexusWorkflowState, the
        conversation_history should never exceed 50 messages.
        
        Validates: Requirements 1.4
        """
        # Create a workflow state
        state = NexusWorkflowState(user_id="test-user")
        
        # Add messages one by one
        for message in messages:
            state.add_message(message)
            
            # Verify the window constraint is maintained
            assert len(state.conversation_history) <= 50, (
                f"Conversation history exceeded 50 messages: "
                f"got {len(state.conversation_history)} messages"
            )
        
        # Final verification
        assert len(state.conversation_history) <= 50
        
        # If we added more than 50 messages, verify we kept the last 50
        num_messages = len(messages)
        if num_messages > 50:
            assert len(state.conversation_history) == 50
            # Verify we kept the most recent messages
            expected_messages = messages[num_messages - 50:num_messages]
            for i, expected in enumerate(expected_messages):
                actual = state.conversation_history[i]
                assert actual.content == expected.content
                assert actual.role == expected.role

    def test_workflow_state_initialization(self):
        """Test that NexusWorkflowState initializes with correct defaults."""
        state = NexusWorkflowState(user_id="test-user")
        
        assert state.user_id == "test-user"
        assert state.conversation_id == ""
        assert state.status == NexusStatus.IDLE
        assert state.current_goal is None
        assert state.current_plan is None
        assert state.conversation_history == []
        assert state.last_error is None
        assert state.actions_count == 0
        assert state.started_at is not None

    def test_workflow_state_add_single_message(self):
        """Test adding a single message to workflow state."""
        state = NexusWorkflowState(user_id="test-user")
        message = ConversationMessage(
            role=MessageRole.USER,
            content="Hello"
        )
        
        state.add_message(message)
        
        assert len(state.conversation_history) == 1
        assert state.conversation_history[0].content == "Hello"

    def test_workflow_state_serialization(self):
        """Test that NexusWorkflowState can be serialized and deserialized."""
        state = NexusWorkflowState(
            user_id="test-user",
            conversation_id="test-conv",
            status=NexusStatus.PROCESSING
        )
        
        # Serialize
        state_dict = state.to_dict()
        assert isinstance(state_dict, dict)
        assert state_dict["user_id"] == "test-user"
        assert state_dict["conversation_id"] == "test-conv"
        assert state_dict["status"] == "processing"
        
        # Deserialize
        restored_state = NexusWorkflowState.from_dict(state_dict)
        assert restored_state.user_id == state.user_id
        assert restored_state.conversation_id == state.conversation_id
        assert restored_state.status == state.status


class TestExecutionPlan:
    """Tests for ExecutionPlan model."""

    @given(plan=execution_plans())
    def test_property_4_execution_plan_state_consistency(self, plan):
        """
        Feature: nexus-testing, Property 4: Execution plan state consistency
        
        For any ExecutionPlan, if all steps have status 'completed' or 'skipped',
        then is_complete should be True. The properties current_step, next_pending_step,
        is_complete, and has_failures should be consistent with the step statuses.
        
        Validates: Requirements 1.6
        """
        # Test is_complete property
        all_done = all(s.status in ("completed", "skipped") for s in plan.steps)
        assert plan.is_complete == all_done, (
            f"is_complete property inconsistent: expected {all_done}, got {plan.is_complete}"
        )
        
        # Test has_failures property
        any_failed = any(s.status == "failed" for s in plan.steps)
        assert plan.has_failures == any_failed, (
            f"has_failures property inconsistent: expected {any_failed}, got {plan.has_failures}"
        )
        
        # Test current_step property
        running_steps = [s for s in plan.steps if s.status == "running"]
        if running_steps:
            assert plan.current_step is not None
            assert plan.current_step.status == "running"
            assert plan.current_step in running_steps
        else:
            assert plan.current_step is None
        
        # Test next_pending_step property
        pending_steps = [s for s in plan.steps if s.status == "pending"]
        if pending_steps:
            assert plan.next_pending_step is not None
            assert plan.next_pending_step.status == "pending"
            # Should be the first pending step
            assert plan.next_pending_step == pending_steps[0]
        else:
            assert plan.next_pending_step is None

    def test_execution_plan_initialization(self):
        """Test that ExecutionPlan initializes with correct defaults."""
        plan = ExecutionPlan()
        
        assert plan.version == 1
        assert plan.goal == ""
        assert plan.steps == []
        assert plan.created_at is not None

    def test_execution_plan_all_completed(self):
        """Test execution plan with all steps completed."""
        plan = ExecutionPlan(
            goal="Test goal",
            steps=[
                PlanStep(id=0, description="Step 1", status="completed"),
                PlanStep(id=1, description="Step 2", status="completed"),
                PlanStep(id=2, description="Step 3", status="completed"),
            ]
        )
        
        assert plan.is_complete is True
        assert plan.has_failures is False
        assert plan.current_step is None
        assert plan.next_pending_step is None

    def test_execution_plan_with_failures(self):
        """Test execution plan with failed steps."""
        plan = ExecutionPlan(
            goal="Test goal",
            steps=[
                PlanStep(id=0, description="Step 1", status="completed"),
                PlanStep(id=1, description="Step 2", status="failed", error="Test error"),
                PlanStep(id=2, description="Step 3", status="pending"),
            ]
        )
        
        assert plan.is_complete is False
        assert plan.has_failures is True
        assert plan.current_step is None
        assert plan.next_pending_step is not None
        assert plan.next_pending_step.id == 2

    def test_execution_plan_with_running_step(self):
        """Test execution plan with a running step."""
        plan = ExecutionPlan(
            goal="Test goal",
            steps=[
                PlanStep(id=0, description="Step 1", status="completed"),
                PlanStep(id=1, description="Step 2", status="running"),
                PlanStep(id=2, description="Step 3", status="pending"),
            ]
        )
        
        assert plan.is_complete is False
        assert plan.has_failures is False
        assert plan.current_step is not None
        assert plan.current_step.id == 1
        assert plan.next_pending_step is not None
        assert plan.next_pending_step.id == 2

    def test_execution_plan_with_skipped_steps(self):
        """Test execution plan with skipped steps."""
        plan = ExecutionPlan(
            goal="Test goal",
            steps=[
                PlanStep(id=0, description="Step 1", status="completed"),
                PlanStep(id=1, description="Step 2", status="skipped"),
                PlanStep(id=2, description="Step 3", status="completed"),
            ]
        )
        
        assert plan.is_complete is True
        assert plan.has_failures is False


class TestPlanStep:
    """Tests for PlanStep model."""

    def test_plan_step_initialization(self):
        """Test that PlanStep initializes with correct defaults."""
        step = PlanStep(id=0, description="Test step")
        
        assert step.id == 0
        assert step.description == "Test step"
        assert step.skill_name is None
        assert step.status == "pending"
        assert step.result_summary is None
        assert step.error is None
        assert step.started_at is None
        assert step.completed_at is None

    def test_plan_step_with_all_fields(self):
        """Test PlanStep with all fields populated."""
        step = PlanStep(
            id=1,
            description="Execute skill",
            skill_name="test-skill",
            status="completed",
            result_summary="Success",
            error=None,
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:01:00Z"
        )
        
        assert step.id == 1
        assert step.description == "Execute skill"
        assert step.skill_name == "test-skill"
        assert step.status == "completed"
        assert step.result_summary == "Success"
        assert step.error is None
        assert step.started_at == "2024-01-01T00:00:00Z"
        assert step.completed_at == "2024-01-01T00:01:00Z"

    def test_plan_step_with_error(self):
        """Test PlanStep with error information."""
        step = PlanStep(
            id=2,
            description="Failed step",
            status="failed",
            error="Something went wrong"
        )
        
        assert step.status == "failed"
        assert step.error == "Something went wrong"
