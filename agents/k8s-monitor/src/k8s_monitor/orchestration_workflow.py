"""
Remediation Orchestration Workflow - 8-stage investigation pipeline.

This workflow implements the sophisticated investigation pipeline from
cluster-monitor as a Temporal workflow, providing:
- Durable state persistence across failures
- Clear stage transitions with audit trail
- Integration with Healer for remediation execution
- Memory queries for pattern matching
- Discord notifications at each stage

Stages:
1. ANALYZING - Initial event classification
2. QUERYING_MEMORY - Check historical patterns
3. INVESTIGATING - Run diagnostic activities
4. PLANNING_REMEDIATION - Determine action plan
5. AWAITING_APPROVAL - Wait for human approval (if needed)
6. EXECUTING_ACTION - Run remediation
7. VERIFYING - Check resolution
8. SUMMARIZING - Generate narrative, store learnings
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from k8s_monitor.models import InvestigationStage, InvestigationState
    from k8s_monitor.orchestration_activities import (
        analyze_issue,
        execute_remediation,
        investigate_issue,
        plan_remediation,
        post_stage_update,
        query_memory,
        store_learning,
        summarize_investigation,
        verify_remediation,
        wait_for_approval,
    )


# Activity retry policy - be conservative to avoid spam
ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)

# Short timeout for quick activities
SHORT_TIMEOUT = timedelta(seconds=30)

# Medium timeout for investigation activities
MEDIUM_TIMEOUT = timedelta(minutes=2)

# Long timeout for remediation activities
LONG_TIMEOUT = timedelta(minutes=5)

# Approval timeout
APPROVAL_TIMEOUT = timedelta(hours=1)


@workflow.defn
class RemediationOrchestrationWorkflow:
    """
    8-stage investigation and remediation workflow.

    This workflow orchestrates the full lifecycle of issue investigation
    and remediation, from detection through verification and learning.

    The workflow is idempotent and can be safely retried - Temporal
    handles state persistence across failures.
    """

    def __init__(self) -> None:
        self._state: InvestigationState | None = None
        self._approval_received = False
        self._approval_result: dict[str, Any] | None = None

    @workflow.signal
    def approval_received(self, approved: bool, reason: str = "") -> None:
        """Signal handler for human approval responses."""
        self._approval_received = True
        self._approval_result = {"approved": approved, "reason": reason}

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        """Query handler to get current investigation state."""
        if self._state:
            return self._state.model_dump(mode="json")
        return {}

    @workflow.run
    async def run(self, issue_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the 8-stage investigation pipeline.

        Args:
            issue_data: Correlated issue from Sentinel (CorrelatedIssue dict)

        Returns:
            Final investigation result with outcome and learnings
        """
        workflow.logger.info(
            f"Starting investigation: {issue_data.get('correlation_id', 'unknown')}"
        )

        # Initialize state
        self._state = InvestigationState(
            investigation_id=f"inv-{workflow.info().workflow_id}",
            trigger_event=issue_data.get("primary_event", {}),
            correlated_events=issue_data.get("related_events", []),
            namespace=issue_data.get("namespace"),
            severity=issue_data.get("severity", "medium"),
        )

        try:
            # Stage 1: ANALYZING
            await self._run_stage(InvestigationStage.ANALYZING, self._analyze)

            # Stage 2: QUERYING_MEMORY
            await self._run_stage(InvestigationStage.QUERYING_MEMORY, self._query_memory)

            # Stage 3: INVESTIGATING
            await self._run_stage(InvestigationStage.INVESTIGATING, self._investigate)

            # Stage 4: PLANNING_REMEDIATION
            await self._run_stage(InvestigationStage.PLANNING_REMEDIATION, self._plan_remediation)

            # Stage 5: AWAITING_APPROVAL (if needed)
            if self._state.approval_required:
                await self._run_stage(InvestigationStage.AWAITING_APPROVAL, self._await_approval)

            # Stage 6: EXECUTING_ACTION
            await self._run_stage(InvestigationStage.EXECUTING_ACTION, self._execute_action)

            # Stage 7: VERIFYING
            await self._run_stage(InvestigationStage.VERIFYING, self._verify)

            # Stage 8: SUMMARIZING
            await self._run_stage(InvestigationStage.SUMMARIZING, self._summarize)

            # Mark completed
            self._state.stage = InvestigationStage.COMPLETED
            workflow.logger.info(f"Investigation completed: {self._state.investigation_id}")

        except Exception as e:
            workflow.logger.error(f"Investigation failed: {e}")
            self._state.stage = InvestigationStage.FAILED
            self._state.error = str(e)

            # Post failure notification
            await workflow.execute_activity(
                post_stage_update,
                args=[self._state.model_dump(mode="json"), "failed", str(e)],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

        return self._state.model_dump(mode="json")

    async def _run_stage(
        self,
        stage: InvestigationStage,
        handler,
    ) -> None:
        """Execute a stage with logging and Discord notification."""
        workflow.logger.info(f"Entering stage: {stage.value}")
        self._state.stage = stage

        # Post stage update to Discord
        await workflow.execute_activity(
            post_stage_update,
            args=[self._state.model_dump(mode="json"), stage.value, None],
            start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        # Execute stage handler
        await handler()

    async def _analyze(self) -> None:
        """Stage 1: Analyze the correlated issue."""
        result = await workflow.execute_activity(
            analyze_issue,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=MEDIUM_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.classification = result.get("classification")
        self._state.confidence = result.get("confidence", 0.0)
        self._state.severity = result.get("severity", self._state.severity)

    async def _query_memory(self) -> None:
        """Stage 2: Query memory for similar incidents."""
        result = await workflow.execute_activity(
            query_memory,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=MEDIUM_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.similar_incidents = result.get("similar_incidents", [])
        self._state.relevant_skills = result.get("relevant_skills", [])

    async def _investigate(self) -> None:
        """Stage 3: Run diagnostic investigation."""
        result = await workflow.execute_activity(
            investigate_issue,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=LONG_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.diagnostic_results = result.get("diagnostics", {})
        self._state.root_cause = result.get("root_cause")
        self._state.pod_name = result.get("pod_name", self._state.pod_name)
        self._state.node_name = result.get("node_name", self._state.node_name)

    async def _plan_remediation(self) -> None:
        """Stage 4: Plan remediation actions."""
        result = await workflow.execute_activity(
            plan_remediation,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=MEDIUM_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.remediation_plan = result.get("plan")
        self._state.approval_required = result.get("requires_approval", False)

    async def _await_approval(self) -> None:
        """Stage 5: Wait for human approval."""
        # Request approval
        await workflow.execute_activity(
            wait_for_approval,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        # Wait for signal with timeout
        try:
            await workflow.wait_condition(
                lambda: self._approval_received,
                timeout=APPROVAL_TIMEOUT,
            )

            if self._approval_result:
                self._state.approval_status = (
                    "approved" if self._approval_result["approved"] else "rejected"
                )
                if not self._approval_result["approved"]:
                    raise Exception(
                        f"Approval rejected: {self._approval_result.get('reason', 'No reason given')}"
                    )
        except TimeoutError:
            self._state.approval_status = "timeout"
            raise Exception("Approval timeout - no response within 1 hour")

    async def _execute_action(self) -> None:
        """Stage 6: Execute the remediation plan."""
        if not self._state.remediation_plan:
            workflow.logger.info("No remediation plan - skipping execution")
            return

        result = await workflow.execute_activity(
            execute_remediation,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=LONG_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.remediation_result = result

    async def _verify(self) -> None:
        """Stage 7: Verify remediation success."""
        result = await workflow.execute_activity(
            verify_remediation,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=MEDIUM_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.verification_result = result
        self._state.resolution_confirmed = result.get("resolved", False)

    async def _summarize(self) -> None:
        """Stage 8: Summarize and store learnings."""
        # Generate narrative
        result = await workflow.execute_activity(
            summarize_investigation,
            args=[self._state.model_dump(mode="json")],
            start_to_close_timeout=MEDIUM_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        self._state.narrative = result.get("narrative", "")

        # Store learnings if successful
        if self._state.resolution_confirmed:
            await workflow.execute_activity(
                store_learning,
                args=[self._state.model_dump(mode="json")],
                start_to_close_timeout=SHORT_TIMEOUT,
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
