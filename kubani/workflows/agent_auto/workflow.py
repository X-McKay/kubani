# kubani/workflows/agent_auto/workflow.py
"""Agent Auto Temporal Workflow.

Orchestrates the full agent creation lifecycle:
1. Draft agent (identify skills, generate files)
2. Create missing skills (via child SkillAutoWorkflow)
3. Write agent files
4. Eval-Improve loop
5. Publish
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.workflows.agent_auto.activities import (
        analyze_failures_activity,
        apply_improvements_activity,
        draft_agent_activity,
        evaluate_agent_activity,
        publish_agent_activity,
        write_agent_files_activity,
    )
    from kubani.workflows.agent_auto.domain.models import (
        AgentAutoInput,
        AgentAutoResult,
        AgentAutoState,
        AgentEvaluationResult,
    )
    from kubani.workflows.skill_auto.models import SkillAutoInput
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError", "UserCancelled"],
)


@workflow.defn
class AgentAutoWorkflow:
    """
    Autonomous agent development workflow.

    Orchestrates: draft → create skills → write files → eval → improve → publish.
    Calls SkillAutoWorkflow as a child workflow for any missing skills.
    """

    def __init__(self) -> None:
        self._state: AgentAutoState | None = None
        self._paused = False
        self._cancelled = False

    @workflow.run
    async def run(self, input: AgentAutoInput) -> AgentAutoResult:
        """Main workflow execution."""
        # Initialize state
        self._state = AgentAutoState(
            agent_name=input.agent_name,
            description=input.description,
            test_cases=input.test_cases,
        )

        try:
            # === Phase 1: Draft Agent & Identify Missing Skills ===
            await self._draft_agent(input)

            # === Phase 2: Create Missing Skills (via child workflows) ===
            await self._create_missing_skills()

            # === Phase 3: Write Agent Files ===
            await self._write_agent_files()

            # === Phase 4: Eval-Improve Loop ===
            await self._run_improvement_loop(input)

            # === Phase 5: Publish (if successful) ===
            await self._publish_if_successful(input)

            return self._build_result()

        except Exception as e:
            self._state.status = "failed"
            self._state.error = str(e)
            workflow.logger.error(f"AgentAutoWorkflow failed: {e}")
            return AgentAutoResult(
                success=False,
                agent_path=self._state.agent_path,
                final_accuracy=self._get_last_accuracy(),
                iterations_completed=self._state.iteration,
                status="failed",
                error=str(e),
            )

    @workflow.query
    def get_state(self) -> AgentAutoState | None:
        """Query current workflow state."""
        return self._state

    @workflow.signal
    async def pause(self) -> None:
        """Pause workflow after current phase."""
        self._paused = True

    @workflow.signal
    async def resume(self) -> None:
        """Resume paused workflow."""
        self._paused = False

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel workflow."""
        self._cancelled = True
        if self._state:
            self._state.status = "failed"
            self._state.error = "Cancelled by user"

    # =========================================================================
    # Phase 1: Draft Agent
    # =========================================================================

    async def _draft_agent(self, input: AgentAutoInput) -> None:
        """Draft the agent, identifying required skills and generating initial files."""
        self._state.status = "drafting"
        workflow.logger.info(f"Drafting agent: {input.agent_name}")

        # Check for pause/cancel
        await self._check_pause_or_cancel()

        draft_result = await workflow.execute_activity(
            draft_agent_activity,
            args=[input.description],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Store results in workflow state (accessible to subsequent phases)
        self._draft_result = draft_result
        self._state.agent_path = f"agents/{input.agent_name}"

        workflow.logger.info(
            f"Draft complete. Missing skills: {draft_result.get('missing_skills', [])}"
        )

    # =========================================================================
    # Phase 2: Create Missing Skills
    # =========================================================================

    async def _create_missing_skills(self) -> None:
        """Create any missing skills by starting child SkillAutoWorkflow instances."""
        missing_skills = self._draft_result.get("missing_skills", [])

        if not missing_skills:
            workflow.logger.info("No missing skills to create")
            return

        self._state.status = "creating_skills"
        workflow.logger.info(f"Creating {len(missing_skills)} missing skills")

        await self._check_pause_or_cancel()

        # Start child workflows for each missing skill
        child_handles = []
        for skill_name in missing_skills:
            # Create a description for the skill based on its name
            skill_description = f"Skill for {skill_name.replace('/', ' ').replace('_', ' ')}"

            child_handle = await workflow.start_child_workflow(
                SkillAutoWorkflow.run,
                args=[
                    SkillAutoInput(
                        description=skill_description,
                        mode="create",
                        max_iterations=input.child_skill_max_iterations,
                        target_accuracy=input.child_skill_target_accuracy,
                        notify=False,  # Don't send notifications for child skills
                    )
                ],
                id=f"create-skill-{skill_name.replace('/', '-').replace('_', '-')}",
                task_queue=workflow.info().task_queue,
            )
            child_handles.append((skill_name, child_handle))

        # Wait for all child workflows to complete
        # If any child fails, the parent should also fail
        failed_skills = []
        for skill_name, handle in child_handles:
            try:
                result = await handle.result()
                if result.success:
                    workflow.logger.info(f"Successfully created skill: {skill_name}")
                else:
                    workflow.logger.error(f"Failed to create skill {skill_name}: {result.error}")
                    failed_skills.append((skill_name, result.error))
            except Exception as e:
                workflow.logger.error(f"Error creating skill {skill_name}: {e}")
                failed_skills.append((skill_name, str(e)))

        # Fail the parent workflow if any child failed
        if failed_skills:
            error_msg = f"Failed to create {len(failed_skills)} required skill(s): " + ", ".join(
                f"{name} ({error})" for name, error in failed_skills
            )
            raise RuntimeError(error_msg)

    # =========================================================================
    # Phase 3: Write Agent Files
    # =========================================================================

    async def _write_agent_files(self) -> None:
        """Write the agent files to disk."""
        self._state.status = "writing_files"
        workflow.logger.info(f"Writing agent files to {self._state.agent_path}")

        await self._check_pause_or_cancel()

        files_to_create = self._draft_result.get("files_to_create", {})
        if not files_to_create:
            workflow.logger.warning("No files to create")
            return

        write_result = await workflow.execute_activity(
            write_agent_files_activity,
            args=[files_to_create],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if not write_result.get("success"):
            raise RuntimeError(f"Failed to write agent files: {write_result.get('error')}")

        workflow.logger.info(f"Wrote {len(write_result.get('written_files', []))} files")

    # =========================================================================
    # Phase 4: Eval-Improve Loop
    # =========================================================================

    async def _run_improvement_loop(self, input: AgentAutoInput) -> None:
        """Run the evaluation-improvement loop."""
        if not input.test_cases:
            workflow.logger.info("No test cases provided, skipping improvement loop")
            return

        self._state.status = "improving"
        workflow.logger.info(
            f"Starting improvement loop (max {input.max_iterations} iterations, "
            f"target accuracy {input.target_accuracy})"
        )

        for i in range(input.max_iterations):
            self._state.iteration = i + 1

            await self._check_pause_or_cancel()

            # Run evaluation
            eval_result_dict = await workflow.execute_activity(
                evaluate_agent_activity,
                args=[
                    self._state.agent_path,
                    [tc.model_dump() for tc in self._state.test_cases],
                ],
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            eval_result = AgentEvaluationResult(**eval_result_dict)
            self._state.eval_history.append(eval_result)

            workflow.logger.info(
                f"Iteration {i + 1}: accuracy={eval_result.objective_accuracy:.2%}"
            )

            # Check if we've met the target
            if eval_result.objective_accuracy >= input.target_accuracy:
                workflow.logger.info(
                    f"Target accuracy reached: {eval_result.objective_accuracy:.2%}"
                )
                break

            # If not at max iterations, run improvement
            if i < input.max_iterations - 1:
                await self._run_improvement(eval_result_dict)

    async def _run_improvement(self, eval_result_dict: dict[str, Any]) -> None:
        """Analyze failures and apply improvements."""
        # Analyze failures to get suggestions
        suggestions_dict = await workflow.execute_activity(
            analyze_failures_activity,
            args=[eval_result_dict],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Apply improvements
        await workflow.execute_activity(
            apply_improvements_activity,
            args=[self._state.agent_path, suggestions_dict],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

    # =========================================================================
    # Phase 5: Publish
    # =========================================================================

    async def _publish_if_successful(self, input: AgentAutoInput) -> None:
        """Publish the agent if it meets the accuracy target."""
        final_accuracy = self._get_last_accuracy()

        if final_accuracy is None or final_accuracy < input.target_accuracy:
            self._state.status = "finished_failed_to_meet_accuracy"
            workflow.logger.warning(
                f"Agent did not meet target accuracy. "
                f"Final: {final_accuracy}, Target: {input.target_accuracy}"
            )
            return

        self._state.status = "publishing"
        workflow.logger.info("Publishing agent")

        await self._check_pause_or_cancel()

        publish_result = await workflow.execute_activity(
            publish_agent_activity,
            args=[self._state.agent_path, input.publish_options],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if publish_result.get("success"):
            self._state.status = "published"
            workflow.logger.info(f"Agent published to {publish_result.get('published_path')}")
        else:
            raise RuntimeError(f"Failed to publish agent: {publish_result.get('error')}")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _check_pause_or_cancel(self) -> None:
        """Check for pause or cancel signals."""
        if self._cancelled:
            raise RuntimeError("Workflow cancelled by user")

        if self._paused:
            workflow.logger.info("Workflow paused, waiting for resume...")
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)
            if self._cancelled:
                raise RuntimeError("Workflow cancelled by user")

    def _get_last_accuracy(self) -> float | None:
        """Get the accuracy from the last evaluation."""
        if self._state.eval_history:
            return self._state.eval_history[-1].objective_accuracy
        return None

    def _build_result(self) -> AgentAutoResult:
        """Build the final result from workflow state."""
        return AgentAutoResult(
            success=self._state.status == "published",
            agent_path=self._state.agent_path,
            final_accuracy=self._get_last_accuracy(),
            iterations_completed=self._state.iteration,
            status=self._state.status,
        )
