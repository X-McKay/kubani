"""Skill Auto Temporal Workflow.

Orchestrates the autonomous skill development cycle:
create -> eval -> improve -> repeat until quality goals met.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models import (
        EvalMetrics,
        IterationContext,
        IterationResult,
        SkillAutoInput,
        SkillAutoResult,
        SkillAutoState,
        SkillVersion,
        compute_score,
        is_plateau,
        should_continue_iteration,
    )
    from .activities import (
        detect_skill_overlap_activity,
        generate_test_cases_activity,
        infer_skill_structure_activity,
        load_existing_skills_activity,
        read_file_content_activity,
        run_evaluation_activity,
        run_improvement_activity,
        save_iteration_result_activity,
        send_notification_activity,
        write_file_content_activity,
        write_skill_files_activity,
    )


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["SkillValidationError", "UserCancelled"],
)


@workflow.defn
class SkillAutoWorkflow:
    """
    Autonomous skill development workflow.

    Orchestrates: create -> eval -> improve -> repeat until quality goals met.
    """

    def __init__(self) -> None:
        self._state: SkillAutoState | None = None
        self._paused = False
        self._cancelled = False

    @workflow.run
    async def run(self, input: SkillAutoInput) -> SkillAutoResult:
        """Main workflow execution."""
        # Initialize state
        skill_name = self._infer_skill_name(input.description)
        self._state = SkillAutoState(
            skill_path=input.skill_path or f"kubani/skills/_development/{skill_name}",
            skill_name=skill_name,
        )

        try:
            # Phase 1: Check for overlap (new skills only)
            if input.mode == "create" and not input.allow_overlap:
                await self._check_overlap(input)

            # Phase 2: Create skill (if new)
            if input.mode == "create":
                await self._create_skill(input)

            # Phase 3: Iteration loop
            while self._should_continue(input):
                await self._run_iteration(input)

            # Phase 4: Finalize
            return self._build_result()

        except Exception as e:
            self._state.status = "failed"
            self._state.error = str(e)
            if input.notify:
                await self._notify("failed", input.notify_channel, error=str(e))
            return SkillAutoResult(
                success=False,
                skill_path=self._state.skill_path,
                final_metrics=self._state.best_version.metrics
                if self._state.best_version
                else None,
                iterations_completed=self._state.iteration,
                stop_reason="error",
                error=str(e),
            )

    @workflow.query
    def get_state(self) -> SkillAutoState | None:
        """Query current workflow state."""
        return self._state

    @workflow.signal
    async def pause(self) -> None:
        """Pause workflow after current phase."""
        self._paused = True
        if self._state:
            self._state.status = "paused"

    @workflow.signal
    async def resume(self) -> None:
        """Resume paused workflow."""
        self._paused = False
        if self._state:
            self._state.status = "running"

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel workflow."""
        self._cancelled = True
        if self._state:
            self._state.status = "failed"
            self._state.error = "Cancelled by user"

    def _infer_skill_name(self, description: str) -> str:
        """Infer skill name from description."""
        # Simple heuristic - take first few words, kebab-case
        words = description.lower().split()[:4]
        return "-".join(w for w in words if w.isalnum())[:30]

    def _should_continue(self, input: SkillAutoInput) -> bool:
        """
        Check if iteration loop should continue.

        Uses the pure decision function from the models module for testability.
        """
        ctx = IterationContext(
            current_iteration=self._state.iteration,
            max_iterations=input.max_iterations,
            best_score=self._state.best_score,
            target_accuracy=input.target_accuracy,
            history=self._state.history,
            is_cancelled=self._cancelled,
        )
        should_continue, _reason = should_continue_iteration(ctx)
        return should_continue

    async def _check_overlap(self, input: SkillAutoInput) -> None:
        """Check for skill overlap."""
        existing = await workflow.execute_activity(
            load_existing_skills_activity,
            args=[
                "kubani/skills",
                False,
            ],  # Exclude _development (str, not Path, for serialization)
            start_to_close_timeout=timedelta(minutes=1),
        )

        if existing:
            overlap = await workflow.execute_activity(
                detect_skill_overlap_activity,
                args=[input.description, existing, None],  # llm_client injected by worker
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # overlap is now a dict from activity
            if overlap.get("has_overlap"):
                from ..models import OverlapResult

                self._state.overlap_warning = OverlapResult(
                    has_overlap=overlap["has_overlap"],
                    confidence=overlap["confidence"],
                    overlapping_skills=overlap["overlapping_skills"],
                    reasoning=overlap["reasoning"],
                    recommendation=overlap["recommendation"],
                )
                workflow.logger.warning(
                    f"Overlap detected with {overlap['overlapping_skills']}: {overlap['reasoning']}"
                )

    async def _create_skill(self, input: SkillAutoInput) -> None:
        """Create new skill from description."""
        # Notify start
        if input.notify:
            await self._notify("started", input.notify_channel)

        # Infer structure
        spec = await workflow.execute_activity(
            infer_skill_structure_activity,
            args=[input.description, None],  # llm_client injected by worker
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Load seed tests if provided (via activity to avoid I/O in workflow)
        seed_tests = None
        if input.seed_tests_path:
            seed_tests = await workflow.execute_activity(
                read_file_content_activity,
                args=[input.seed_tests_path],
                start_to_close_timeout=timedelta(seconds=30),
            )

        # Generate test cases
        test_cases = await workflow.execute_activity(
            generate_test_cases_activity,
            args=[spec, None, seed_tests],  # llm_client injected by worker
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Write files and capture content for workflow state
        result = await workflow.execute_activity(
            write_skill_files_activity,
            args=[
                spec,
                test_cases,
                "kubani/skills/_development",
            ],  # str, not Path, for serialization
            start_to_close_timeout=timedelta(minutes=1),
        )

        # Store path and content in state (content avoids future filesystem reads)
        self._state.skill_path = result["path"]
        self._state.current_content = result["content"]
        self._state.current_tests = result["test_cases"]
        self._state.skill_name = spec.get("name", self._state.skill_name)

    async def _run_iteration(self, input: SkillAutoInput) -> None:
        """Run one eval-improve iteration."""
        self._state.iteration += 1

        # Check for pause
        if self._paused:
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)
            if self._cancelled:
                return

        # Run evaluation (returns dict with 'metrics' and 'feedback')
        eval_result = await workflow.execute_activity(
            run_evaluation_activity,
            args=[self._state.skill_path, None],  # llm_client injected by worker
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Extract metrics and feedback from result
        metrics_dict = eval_result["metrics"]
        feedback = eval_result["feedback"]
        metrics = EvalMetrics(
            accuracy=metrics_dict["accuracy"],
            latency_ms=metrics_dict["latency_ms"],
            tests_passed=metrics_dict["tests_passed"],
            tests_total=metrics_dict["tests_total"],
            critic_confidence=metrics_dict["critic_confidence"],
            tokens_prompt=metrics_dict["tokens_prompt"],
            tokens_completion=metrics_dict["tokens_completion"],
        )

        # Compute score
        score = compute_score(metrics)
        improved = score > self._state.best_score

        # Update best version if improved (use content from state, not filesystem)
        if improved:
            self._state.best_version = SkillVersion(
                content=self._state.current_content,
                test_cases=self._state.current_tests,
                metrics=metrics,
                iteration=self._state.iteration,
            )
            self._state.best_score = score

        # Determine action
        action = self._determine_action(input, metrics, score, improved)

        # Record iteration
        iteration_result = IterationResult(
            iteration=self._state.iteration,
            metrics=metrics,
            score=score,
            improved=improved,
            action=action,
        )
        self._state.history.append(iteration_result)

        # Save iteration result to disk for history tracking
        await workflow.execute_activity(
            save_iteration_result_activity,
            args=[
                self._state.skill_path,
                {
                    "iteration": iteration_result.iteration,
                    "score": iteration_result.score,
                    "improved": iteration_result.improved,
                    "action": iteration_result.action,
                    "metrics": {
                        "accuracy": metrics.accuracy,
                        "latency_ms": metrics.latency_ms,
                        "tests_passed": metrics.tests_passed,
                        "tests_total": metrics.tests_total,
                        "critic_confidence": metrics.critic_confidence,
                    },
                },
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Notify progress
        if input.notify:
            await self._notify("iteration_complete", input.notify_channel, metrics=metrics)

        # Check for review pause
        if input.review_each_iteration and action == "continue":
            self._paused = True
            self._state.status = "paused"
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)

        # Run improvement if continuing
        if action == "continue" and not self._cancelled:
            # Revert to best if this iteration regressed (via activity, not direct I/O)
            if not improved and self._state.best_version:
                await workflow.execute_activity(
                    write_file_content_activity,
                    args=[
                        f"{self._state.skill_path}/SKILL.md",
                        self._state.best_version.content,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                # Update current content to match reverted version
                self._state.current_content = self._state.best_version.content

            # Use rich feedback from evaluation (includes failing test details and critic feedback)
            await workflow.execute_activity(
                run_improvement_activity,
                args=[
                    self._state.skill_path,
                    feedback,
                    None,  # llm_client (deprecated, created from config)
                    input.create_backups,
                    input.max_backups,
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

    def _determine_action(
        self,
        input: SkillAutoInput,
        metrics: EvalMetrics,
        score: float,
        improved: bool,
    ) -> str:
        """Determine what action to take after evaluation."""
        if metrics.accuracy >= input.target_accuracy:
            return "stop_success"
        if self._state.iteration >= input.max_iterations:
            return "stop_cap"
        if len(self._state.history) >= 2 and is_plateau(
            self._state.history
            + [
                IterationResult(
                    iteration=self._state.iteration,
                    metrics=metrics,
                    score=score,
                    improved=improved,
                    action="continue",
                )
            ]
        ):
            return "stop_plateau"
        if not improved and len(self._state.history) >= 1:
            prev_score = self._state.history[-1].score
            if prev_score > 0 and (prev_score - score) / prev_score > 0.2:
                return "stop_regression"
        return "continue"

    async def _notify(
        self,
        event: str,
        channel: str,
        metrics: EvalMetrics | None = None,
        error: str | None = None,
    ) -> None:
        """Send Discord notification."""
        await workflow.execute_activity(
            send_notification_activity,
            args=[
                event,
                self._state.skill_name,
                channel,
                None,  # discord_client injected by worker
                self._state.iteration,
                metrics,
                error,
                None,  # result (for complete event)
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

    def _build_result(self) -> SkillAutoResult:
        """Build final result from state."""
        last_action = self._state.history[-1].action if self._state.history else "unknown"

        self._state.status = "completed"
        return SkillAutoResult(
            success=last_action == "stop_success",
            skill_path=self._state.skill_path,
            final_metrics=self._state.best_version.metrics if self._state.best_version else None,
            iterations_completed=self._state.iteration,
            stop_reason=last_action,
        )
