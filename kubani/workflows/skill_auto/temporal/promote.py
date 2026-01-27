"""PromoteWorkflow - Child workflow for skill promotion.

Handles the promotion flow:
1. Check for overlap with production skills
2. Send promotion request to Discord
3. Await approval reaction
4. Promote skill to production
5. Sync to registry
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models import (
        PromoteWorkflowInput,
        PromoteWorkflowResult,
    )
    from .activities import (
        await_approval_activity,
        check_promotion_overlap_activity,
        load_existing_skills_activity,
        promote_skill_activity,
        send_promotion_request_activity,
        sync_registry_activity,
    )


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["SkillOverlapError", "UserCancelled"],
)


@workflow.defn
class PromoteWorkflow:
    """
    Child workflow for promoting a skill from development to production.

    Flow:
    1. Load production skills and check for overlap
    2. Send promotion request to Discord
    3. Wait for approval reaction (checkmark or X)
    4. If approved, move skill and update metadata
    5. Sync to registry
    """

    def __init__(self) -> None:
        self._cancelled = False

    @workflow.run
    async def run(self, input: PromoteWorkflowInput) -> PromoteWorkflowResult:
        """Execute the promotion workflow."""
        try:
            # Step 1: Load production skills and check for overlap
            production_skills = await workflow.execute_activity(
                load_existing_skills_activity,
                args=[input.skills_root, False],  # Exclude _development
                start_to_close_timeout=timedelta(minutes=1),
            )

            # Check for overlap (may raise SkillOverlapError)
            overlap_result = await workflow.execute_activity(
                check_promotion_overlap_activity,
                args=[
                    input.skill_name,
                    input.skill_description,
                    production_skills,
                    None,  # llm_client injected by worker
                    input.allow_overlap,
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            # Log warning if overlap but allowed (overlap_result is a dict)
            if overlap_result.get("has_overlap"):
                workflow.logger.warning(
                    f"Overlap detected with {overlap_result.get('overlapping_skills')}, "
                    "but allow_overlap=True"
                )

            # Step 2: Send promotion request to Discord
            request_result = await workflow.execute_activity(
                send_promotion_request_activity,
                args=[
                    input.skill_name,
                    input.skill_path,
                    input.metrics,
                    input.iterations,
                    input.notify_channel,
                    None,  # discord_client injected by worker
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if not request_result.get("sent"):
                return PromoteWorkflowResult(
                    promoted=False,
                    error=f"Failed to send promotion request: {request_result.get('error')}",
                )

            message_id = request_result.get("message_id")
            channel_id = request_result.get("channel_id", input.notify_channel)

            # Step 3: Wait for approval
            approval_result = await workflow.execute_activity(
                await_approval_activity,
                args=[
                    channel_id,
                    message_id,
                    None,  # discord_client injected by worker
                    300,  # 5 minute timeout
                ],
                start_to_close_timeout=timedelta(minutes=10),
            )

            if approval_result.get("timeout"):
                return PromoteWorkflowResult(
                    promoted=False,
                    error="Approval timed out",
                )

            if approval_result.get("rejected"):
                return PromoteWorkflowResult(
                    promoted=False,
                    rejected_by=approval_result.get("user_name"),
                    rejection_reason="Rejected via Discord reaction",
                )

            if not approval_result.get("approved"):
                return PromoteWorkflowResult(
                    promoted=False,
                    error=approval_result.get("error", "Unknown approval error"),
                )

            # Step 4: Promote skill
            promote_result = await workflow.execute_activity(
                promote_skill_activity,
                args=[
                    input.skill_path,
                    input.target_category,
                    input.skills_root,
                ],
                start_to_close_timeout=timedelta(minutes=1),
            )

            if not promote_result.get("success"):
                return PromoteWorkflowResult(
                    promoted=False,
                    approved_by=approval_result.get("user_name"),
                    error=promote_result.get("error"),
                )

            # Step 5: Sync to registry
            sync_result = await workflow.execute_activity(
                sync_registry_activity,
                args=[
                    promote_result.get("promoted_path"),
                    None,  # registry_client injected by worker
                ],
                start_to_close_timeout=timedelta(minutes=1),
            )

            return PromoteWorkflowResult(
                promoted=True,
                promoted_path=promote_result.get("promoted_path"),
                approved_by=approval_result.get("user_name"),
                synced_to_registry=sync_result.get("synced", False),
            )

        except Exception as e:
            error_name = type(e).__name__
            if error_name == "SkillOverlapError":
                return PromoteWorkflowResult(
                    promoted=False,
                    error=str(e),
                )
            raise

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel the promotion workflow."""
        self._cancelled = True
