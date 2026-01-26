# tests/workflows/agent_auto/test_workflow.py
"""Tests for AgentAutoWorkflow using Temporal sandbox.

These tests verify workflow orchestration logic with mocked activities.
Uses properly decorated activity stubs for Temporal Worker compatibility.
"""

from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from kubani.workflows.agent_auto.domain.models import (
    AgentAutoInput,
    AgentEvaluationResult,
    AgentTestCase,
)
from kubani.workflows.agent_auto.workflow import AgentAutoWorkflow

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_agent_input() -> AgentAutoInput:
    """Sample agent input for testing."""
    return AgentAutoInput(
        agent_name="test-agent",
        description="An agent for testing purposes",
        test_cases=[
            AgentTestCase(
                name="test1",
                prompt="Hello",
                expected_skills=["greeting"],
                expected_output="Hello there!",
            ),
        ],
        max_iterations=3,
        target_accuracy=0.8,
        notify=False,
    )


@pytest.fixture
def good_eval_result() -> dict[str, Any]:
    """Evaluation result that exceeds target accuracy."""
    return AgentEvaluationResult(
        objective_accuracy=0.9,
        skill_precision=1.0,
        skill_recall=1.0,
        invoked_skills=["greeting"],
        missing_skills=[],
        extraneous_skills=[],
        failures=[],
    ).model_dump()


@pytest.fixture
def poor_eval_result() -> dict[str, Any]:
    """Evaluation result below target accuracy."""
    return AgentEvaluationResult(
        objective_accuracy=0.5,
        skill_precision=0.5,
        skill_recall=0.5,
        invoked_skills=["greeting"],
        missing_skills=["farewell"],
        extraneous_skills=[],
        failures=["test1"],
    ).model_dump()


@pytest.fixture
def improving_eval_results() -> list[dict[str, Any]]:
    """Sequence of improving evaluation results."""
    return [
        AgentEvaluationResult(
            objective_accuracy=0.5,
            skill_precision=0.5,
            skill_recall=0.5,
            invoked_skills=["greeting"],
            missing_skills=["farewell"],
            extraneous_skills=[],
            failures=["test1"],
        ).model_dump(),
        AgentEvaluationResult(
            objective_accuracy=0.7,
            skill_precision=0.8,
            skill_recall=0.7,
            invoked_skills=["greeting", "farewell"],
            missing_skills=[],
            extraneous_skills=[],
            failures=["test1"],
        ).model_dump(),
        AgentEvaluationResult(
            objective_accuracy=0.9,
            skill_precision=1.0,
            skill_recall=1.0,
            invoked_skills=["greeting", "farewell"],
            missing_skills=[],
            extraneous_skills=[],
            failures=[],
        ).model_dump(),
    ]


@pytest.fixture
def draft_result_no_missing_skills() -> dict[str, Any]:
    """Draft result with no missing skills."""
    return {
        "agent_spec": {
            "name": "test-agent",
            "description": "An agent for testing",
            "required_skills": ["greeting"],
            "config_patterns": {},
        },
        "missing_skills": [],
        "files_to_create": {
            "agents/test-agent/prompt.md": "# Test Agent\n\nTest prompt.",
            "agents/test-agent/config.yaml": "name: test-agent\n",
        },
    }


@pytest.fixture
def draft_result_with_missing_skills() -> dict[str, Any]:
    """Draft result with missing skills."""
    return {
        "agent_spec": {
            "name": "test-agent",
            "description": "An agent for testing",
            "required_skills": ["greeting", "farewell", "new/custom-skill"],
            "config_patterns": {},
        },
        "missing_skills": ["new/custom-skill"],
        "files_to_create": {
            "agents/test-agent/prompt.md": "# Test Agent\n\nTest prompt.",
            "agents/test-agent/config.yaml": "name: test-agent\n",
        },
    }


# =============================================================================
# Mock Activity State
# =============================================================================


class MockActivityState:
    """Shared state for mock activities."""

    def __init__(self):
        self.draft_result: dict[str, Any] = {}
        self.eval_results: list[dict[str, Any]] = []
        self.eval_iter = None
        self.child_workflows_started: list[str] = []
        self.should_fail_draft: bool = False
        self.should_fail_eval: bool = False


# Global state for the test - reset between tests
_mock_state = MockActivityState()


def reset_mock_state(
    draft_result: dict[str, Any] | None = None,
    eval_results: list[dict[str, Any]] | None = None,
):
    """Reset the global mock state for a new test."""
    global _mock_state
    _mock_state = MockActivityState()
    if draft_result:
        _mock_state.draft_result = draft_result
    if eval_results:
        _mock_state.eval_results = eval_results
        _mock_state.eval_iter = iter(eval_results)


# =============================================================================
# Mock Activities
# =============================================================================


@activity.defn(name="draft_agent_activity")
async def mock_draft_agent_activity(description: str) -> dict[str, Any]:
    """Mock draft_agent_activity."""
    if _mock_state.should_fail_draft:
        raise RuntimeError("Draft failed")
    return _mock_state.draft_result


@activity.defn(name="write_agent_files_activity")
async def mock_write_agent_files_activity(files_to_create: dict[str, str]) -> dict[str, Any]:
    """Mock write_agent_files_activity."""
    return {
        "success": True,
        "written_files": list(files_to_create.keys()),
    }


@activity.defn(name="evaluate_agent_activity")
async def mock_evaluate_agent_activity(
    agent_path: str,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Mock evaluate_agent_activity."""
    if _mock_state.should_fail_eval:
        raise RuntimeError("Evaluation failed")
    if _mock_state.eval_iter:
        try:
            return next(_mock_state.eval_iter)
        except StopIteration:
            pass
    if _mock_state.eval_results:
        return _mock_state.eval_results[-1]
    # Default result
    return AgentEvaluationResult(
        objective_accuracy=0.5,
        skill_precision=0.5,
        skill_recall=0.5,
        invoked_skills=[],
        missing_skills=[],
        extraneous_skills=[],
        failures=["test1"],
    ).model_dump()


@activity.defn(name="analyze_failures_activity")
async def mock_analyze_failures_activity(eval_result: dict[str, Any]) -> dict[str, Any]:
    """Mock analyze_failures_activity."""
    return {
        "prompt_clarifications": ["Consider adding more context"],
        "skill_additions": eval_result.get("missing_skills", []),
        "skill_removals": [],
        "config_changes": {},
    }


@activity.defn(name="apply_improvements_activity")
async def mock_apply_improvements_activity(
    agent_path: str,
    suggestions: dict[str, Any],
) -> dict[str, Any]:
    """Mock apply_improvements_activity."""
    return {
        "success": True,
        "prompt_updated": True,
        "config_updated": False,
    }


@activity.defn(name="publish_agent_activity")
async def mock_publish_agent_activity(
    agent_path: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    """Mock publish_agent_activity."""
    return {
        "success": True,
        "published_path": agent_path,
        "synced_to_registry": False,
    }


# Mock SkillAutoWorkflow for child workflow testing
from kubani.workflows.skill_auto.models import EvalMetrics, SkillAutoInput, SkillAutoResult


@workflow.defn(name="SkillAutoWorkflow")
class MockSkillAutoWorkflow:
    """Mock SkillAutoWorkflow for testing child workflow invocation."""

    @workflow.run
    async def run(self, input: SkillAutoInput) -> SkillAutoResult:
        """Return success for any skill creation request."""
        _mock_state.child_workflows_started.append(input.description)
        return SkillAutoResult(
            success=True,
            skill_path=f"kubani/skills/_development/{input.description.replace(' ', '-')}",
            final_metrics=EvalMetrics(
                accuracy=0.85,
                latency_ms=1000.0,
                tests_passed=5,
                tests_total=5,
                critic_confidence=0.9,
            ),
            iterations_completed=1,
            stop_reason="stop_success",
        )


# List of all mock activities for the worker
MOCK_ACTIVITIES = [
    mock_draft_agent_activity,
    mock_write_agent_files_activity,
    mock_evaluate_agent_activity,
    mock_analyze_failures_activity,
    mock_apply_improvements_activity,
    mock_publish_agent_activity,
]


# =============================================================================
# Helper for running workflows
# =============================================================================


async def run_workflow(workflow_input: AgentAutoInput):
    """Run the workflow with mock activities.

    Uses UnsandboxedWorkflowRunner to avoid sandbox restrictions.
    """
    from temporalio.worker._workflow_instance import UnsandboxedWorkflowRunner

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="test-queue",
            workflows=[AgentAutoWorkflow, MockSkillAutoWorkflow],
            activities=MOCK_ACTIVITIES,
            workflow_runner=UnsandboxedWorkflowRunner(),
        ),
    ):
        result = await env.client.execute_workflow(
            AgentAutoWorkflow.run,
            workflow_input,
            id="test-agent-workflow",
            task_queue="test-queue",
        )
        return result


# =============================================================================
# Tests - Basic Workflow Execution
# =============================================================================


class TestAgentAutoWorkflowBasicExecution:
    """Tests for basic workflow execution paths."""

    @pytest.mark.asyncio
    async def test_workflow_succeeds_on_first_iteration(
        self, sample_agent_input, draft_result_no_missing_skills, good_eval_result
    ):
        """Workflow completes successfully when first evaluation exceeds target."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[good_eval_result],
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        assert result.status == "published"
        assert result.iterations_completed == 1
        assert result.final_accuracy >= 0.8

    @pytest.mark.asyncio
    async def test_workflow_improves_until_target(
        self, sample_agent_input, draft_result_no_missing_skills, improving_eval_results
    ):
        """Workflow iterates until reaching target accuracy."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=improving_eval_results,
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        assert result.status == "published"
        # Should succeed on iteration 3 (accuracy 0.9 >= 0.8)
        assert result.iterations_completed == 3
        assert result.final_accuracy >= 0.8

    @pytest.mark.asyncio
    async def test_workflow_stops_at_max_iterations(
        self, sample_agent_input, draft_result_no_missing_skills, poor_eval_result
    ):
        """Workflow stops when reaching max iterations without meeting target."""
        # Create sequence that never meets target
        poor_results = [poor_eval_result] * 5

        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=poor_results,
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is False
        assert result.status == "finished_failed_to_meet_accuracy"
        assert result.iterations_completed == sample_agent_input.max_iterations

    @pytest.mark.asyncio
    async def test_workflow_skips_improvement_loop_without_test_cases(
        self, draft_result_no_missing_skills
    ):
        """Workflow skips improvement loop when no test cases provided."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[],  # Won't be used
        )

        input_without_tests = AgentAutoInput(
            agent_name="test-agent",
            description="An agent without test cases",
            test_cases=[],  # No test cases
            notify=False,
        )

        result = await run_workflow(input_without_tests)

        # Without test cases, can't evaluate, so can't publish
        assert result.status == "finished_failed_to_meet_accuracy"
        assert result.iterations_completed == 0


# =============================================================================
# Tests - Child Workflow for Missing Skills
# =============================================================================


class TestAgentAutoWorkflowChildWorkflows:
    """Tests for child workflow invocation for missing skills."""

    @pytest.mark.asyncio
    async def test_workflow_creates_child_workflows_for_missing_skills(
        self, sample_agent_input, draft_result_with_missing_skills, good_eval_result
    ):
        """Workflow starts child SkillAutoWorkflow for each missing skill."""
        reset_mock_state(
            draft_result=draft_result_with_missing_skills,
            eval_results=[good_eval_result],
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        # Verify child workflows were started
        assert len(_mock_state.child_workflows_started) == 1
        # The child workflow should have been started for the missing skill
        assert any("custom-skill" in desc for desc in _mock_state.child_workflows_started)

    @pytest.mark.asyncio
    async def test_workflow_proceeds_without_missing_skills(
        self, sample_agent_input, draft_result_no_missing_skills, good_eval_result
    ):
        """Workflow proceeds directly to writing files when no skills are missing."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[good_eval_result],
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        # No child workflows should have been started
        assert len(_mock_state.child_workflows_started) == 0


# =============================================================================
# Tests - Error Handling
# =============================================================================


class TestAgentAutoWorkflowErrorHandling:
    """Tests for workflow error handling."""

    @pytest.mark.asyncio
    async def test_workflow_handles_draft_error(self, sample_agent_input):
        """Workflow handles draft activity errors gracefully."""
        reset_mock_state(
            draft_result={},
            eval_results=[],
        )
        _mock_state.should_fail_draft = True

        try:
            result = await run_workflow(sample_agent_input)

            assert result.success is False
            assert result.status == "failed"
            assert result.error is not None
        finally:
            _mock_state.should_fail_draft = False

    @pytest.mark.asyncio
    async def test_workflow_handles_evaluation_error(
        self, sample_agent_input, draft_result_no_missing_skills
    ):
        """Workflow handles evaluation activity errors gracefully."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[],
        )
        _mock_state.should_fail_eval = True

        try:
            result = await run_workflow(sample_agent_input)

            assert result.success is False
            assert result.status == "failed"
            assert result.error is not None
        finally:
            _mock_state.should_fail_eval = False


# =============================================================================
# Tests - Workflow State
# =============================================================================


class TestAgentAutoWorkflowState:
    """Tests for workflow state management."""

    @pytest.mark.asyncio
    async def test_workflow_tracks_evaluation_history(
        self, sample_agent_input, draft_result_no_missing_skills, improving_eval_results
    ):
        """Workflow tracks evaluation history across iterations."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=improving_eval_results,
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        # Final accuracy should be from the last successful evaluation
        assert result.final_accuracy >= 0.8

    @pytest.mark.asyncio
    async def test_workflow_returns_agent_path(
        self, sample_agent_input, draft_result_no_missing_skills, good_eval_result
    ):
        """Workflow returns the agent path in result."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[good_eval_result],
        )

        result = await run_workflow(sample_agent_input)

        assert result.agent_path is not None
        assert "test-agent" in result.agent_path


# =============================================================================
# Tests - Publishing
# =============================================================================


class TestAgentAutoWorkflowPublishing:
    """Tests for agent publishing."""

    @pytest.mark.asyncio
    async def test_workflow_publishes_on_success(
        self, sample_agent_input, draft_result_no_missing_skills, good_eval_result
    ):
        """Workflow publishes agent when target accuracy is met."""
        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=[good_eval_result],
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is True
        assert result.status == "published"

    @pytest.mark.asyncio
    async def test_workflow_does_not_publish_on_failure(
        self, sample_agent_input, draft_result_no_missing_skills, poor_eval_result
    ):
        """Workflow does not publish when target accuracy is not met."""
        poor_results = [poor_eval_result] * 5

        reset_mock_state(
            draft_result=draft_result_no_missing_skills,
            eval_results=poor_results,
        )

        result = await run_workflow(sample_agent_input)

        assert result.success is False
        assert result.status == "finished_failed_to_meet_accuracy"
