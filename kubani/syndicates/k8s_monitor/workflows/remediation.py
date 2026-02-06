"""K8s Remediation Workflow - Deterministic remediation sequence.

This workflow implements the Workflow pattern for handling K8s issues with
a deterministic sequence of steps:

1. Classify the incoming event
2. Look up applicable remediation skills
3. Execute remediation steps
4. Verify the fix
5. Learn from the outcome

The workflow is triggered by K8s events and executes a known sequence of
activities. It uses ObservableWorkflowMixin for status queries, event logging,
and pause/resume/cancel signals.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


# =============================================================================
# Input/Output Types
# =============================================================================


@dataclass
class RemediationInput:
    """Input for K8s remediation workflow.

    Attributes:
        event_id: Unique identifier for the K8s event
        resource_kind: Kind of resource (Pod, Deployment, etc.)
        resource_name: Name of the resource
        namespace: Kubernetes namespace
        reason: Event reason (OOMKilled, CrashLoopBackOff, etc.)
        message: Event message
        severity: Classified severity (critical, warning, info)
        auto_remediate: Whether to automatically apply fixes
        notify_channel: Discord channel for notifications
        correlation_id: Optional ID for tracking related events
    """

    event_id: str
    resource_kind: str
    resource_name: str
    namespace: str
    reason: str
    message: str
    severity: str = "warning"
    auto_remediate: bool = True
    notify_channel: str = "k8s-alerts"
    correlation_id: str | None = None


@dataclass
class RemediationResult:
    """Result of K8s remediation workflow.

    Attributes:
        event_id: The event that was processed
        classification: How the event was classified
        skills_matched: Skills that matched this issue
        remediation_applied: Whether remediation was applied
        remediation_steps: Steps that were executed
        verified: Whether the fix was verified
        escalated: Whether the issue was escalated
        learning_stored: Whether learning was recorded
        success: Overall success status
        error: Error message if failed
    """

    event_id: str
    classification: dict[str, Any] | None = None
    skills_matched: list[str] | None = None
    remediation_applied: bool = False
    remediation_steps: list[str] | None = None
    verified: bool = False
    escalated: bool = False
    learning_stored: bool = False
    success: bool = True
    error: str | None = None


# =============================================================================
# Activity Retry Policies
# =============================================================================


CLASSIFY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

REMEDIATE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)

VERIFY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=30),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=5,
    backoff_coefficient=1.5,
)


# =============================================================================
# Workflow Definition
# =============================================================================


@workflow.defn
class K8sRemediationWorkflow(ObservableWorkflowMixin):
    """Deterministic K8s remediation workflow.

    Executes a known sequence of steps for handling K8s issues:
    1. Classify event → 2. Match skills → 3. Remediate → 4. Verify → 5. Learn

    The workflow is idempotent and can be safely retried. Each phase
    is tracked via ObservableWorkflowMixin for full observability.

    Signals:
        - pause: Pause execution before next phase
        - resume: Resume paused execution
        - cancel: Cancel the workflow

    Queries:
        - get_status: Current workflow status and phase
        - get_events: List of workflow events
        - get_remediation_stats: Remediation-specific statistics
    """

    def __init__(self) -> None:
        """Initialize the workflow."""
        self._init_observability("K8sRemediationWorkflow")
        self._result = RemediationResult(event_id="")
        self._classification: dict[str, Any] = {}
        self._matched_skills: list[dict[str, Any]] = []
        self._remediation_steps: list[str] = []

    @workflow.run
    async def run(self, input: RemediationInput) -> dict[str, Any]:
        """Execute the remediation workflow.

        Args:
            input: Remediation configuration

        Returns:
            RemediationResult as dict
        """
        self._result.event_id = input.event_id
        self._set_status(
            WorkflowStatus.RUNNING,
            f"Processing {input.resource_kind}/{input.resource_name}",
            phase="init",
            resource=f"{input.namespace}/{input.resource_kind}/{input.resource_name}",
            reason=input.reason,
        )

        try:
            # Phase 1: Classify the event
            await self._classify_event(input)

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 2: Look up applicable skills
            await self._match_skills(input)

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 3: Execute remediation (if auto and skills found)
            if input.auto_remediate and self._matched_skills:
                await self._execute_remediation(input)

                if await self._wait_if_paused():
                    return self._build_result()

                # Phase 4: Verify the fix
                await self._verify_remediation(input)
            elif not self._matched_skills:
                # No skills matched - escalate
                await self._escalate(input, "No matching skills found")
            else:
                # Auto-remediation disabled - notify only
                await self._notify(input, "Manual intervention required")

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 5: Store learning
            await self._store_learning(input)

            self._set_status(WorkflowStatus.COMPLETED, "Remediation complete")
            self._result.success = True

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Remediation failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            # Still try to escalate on failure
            try:
                await self._escalate(input, f"Workflow failed: {e}")
            except Exception:
                pass

        return self._build_result()

    async def _classify_event(self, input: RemediationInput) -> None:
        """Classify the K8s event using EventClassifier agent."""
        from kubani.framework.temporal import classify_event_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Classifying {input.reason}",
            phase="classify",
        )

        result = await workflow.execute_activity(
            classify_event_activity,
            args=[
                {
                    "kind": input.resource_kind,
                    "name": input.resource_name,
                    "namespace": input.namespace,
                    "reason": input.reason,
                    "message": input.message,
                    "type": "Warning" if input.severity != "info" else "Normal",
                }
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=CLASSIFY_RETRY_POLICY,
        )

        if result.get("success"):
            self._classification = result.get("classification", {})
            self._result.classification = self._classification
            self._log_event(
                "classified",
                f"Severity: {self._classification.get('severity')}, "
                f"Category: {self._classification.get('category')}",
            )
        else:
            self._log_event("classification_failed", result.get("error", "Unknown error"))
            # Use input severity as fallback
            self._classification = {"severity": input.severity, "category": "unknown"}
            self._result.classification = self._classification

    async def _match_skills(self, input: RemediationInput) -> None:
        """Look up skills that match this issue."""
        from kubani.framework.temporal import query_knowledge_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Matching remediation skills",
            phase="match_skills",
        )

        # Query for skills that match this issue type
        query = f"k8s remediation skill {input.reason} {input.resource_kind}"
        result = await workflow.execute_activity(
            query_knowledge_activity,
            args=[
                query,
                10,  # limit
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

        if result.get("success"):
            self._matched_skills = result.get("knowledge", [])
            self._result.skills_matched = [s.get("topic", "unknown") for s in self._matched_skills]
            self._log_event("skills_matched", f"Found {len(self._matched_skills)} matching skills")
        else:
            self._matched_skills = []
            self._result.skills_matched = []
            self._log_event("skills_query_failed", result.get("error", "Unknown error"))

    async def _execute_remediation(self, input: RemediationInput) -> None:
        """Execute remediation using the matched skills."""
        from kubani.framework.temporal import remediate_issue_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Executing remediation for {input.reason}",
            phase="remediate",
        )

        # Build context from matched skills
        skill_context = "\n".join(
            f"- {s.get('topic')}: {s.get('content', '')[:200]}..." for s in self._matched_skills[:3]
        )

        result = await workflow.execute_activity(
            remediate_issue_activity,
            args=[
                {
                    "event_id": input.event_id,
                    "resource_kind": input.resource_kind,
                    "resource_name": input.resource_name,
                    "namespace": input.namespace,
                    "reason": input.reason,
                    "message": input.message,
                    "severity": input.severity,
                    "classification": self._classification,
                    "skill_context": skill_context,
                }
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=REMEDIATE_RETRY_POLICY,
        )

        if result.get("success"):
            self._remediation_steps = result.get("steps", [])
            self._result.remediation_applied = True
            self._result.remediation_steps = self._remediation_steps
            self._log_event(
                "remediation_applied",
                f"Applied {len(self._remediation_steps)} steps",
            )
        else:
            self._log_event("remediation_failed", result.get("error", "Unknown error"))
            # Escalate on remediation failure
            await self._escalate(input, f"Remediation failed: {result.get('error')}")

    async def _verify_remediation(self, input: RemediationInput) -> None:
        """Verify that the remediation was successful."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Verifying remediation",
            phase="verify",
        )

        # Wait a bit for changes to take effect
        await workflow.sleep(timedelta(seconds=30))

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "k8s-verifier",
                f"""Verify that the remediation was successful for:
Resource: {input.resource_kind}/{input.resource_name}
Namespace: {input.namespace}
Original issue: {input.reason}

Check:
1. Is the resource healthy now?
2. Are there any new related issues?
3. Is the issue fully resolved?

Return JSON with:
- verified: boolean
- status: current resource status
- issues: any remaining issues
- confidence: 0-1 confidence in verification""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=VERIFY_RETRY_POLICY,
        )

        if result.get("success"):
            verification = self._parse_json_from_result(result.get("result", ""))
            self._result.verified = verification.get("verified", False)

            if self._result.verified:
                self._log_event("verified", "Remediation successful")
                await self._notify(input, "✅ Issue resolved successfully")
            else:
                self._log_event(
                    "verification_failed",
                    f"Issues remain: {verification.get('issues')}",
                )
                await self._escalate(input, f"Verification failed: {verification.get('issues')}")
        else:
            self._log_event("verification_error", result.get("error", "Unknown error"))
            # Don't escalate on verification error - might just be timing

    async def _escalate(self, input: RemediationInput, reason: str) -> None:
        """Escalate the issue to human operators."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Escalating to operators",
            phase="escalate",
        )

        self._result.escalated = True

        await workflow.execute_activity(
            run_agent_activity,
            args=[
                "discord-notifier",
                f"""Send an escalation alert to channel: {input.notify_channel}

Issue Details:
- Resource: {input.namespace}/{input.resource_kind}/{input.resource_name}
- Reason: {input.reason}
- Message: {input.message}
- Severity: {input.severity}
- Escalation reason: {reason}

Format as a Discord embed with:
- Color: Red (0xFF0000)
- Title: 🚨 K8s Issue Escalation
- Fields for each detail
- Timestamp

Return JSON with: message_id, success""",
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

        self._log_event("escalated", reason)

    async def _notify(self, input: RemediationInput, message: str) -> None:
        """Send a notification to Discord."""
        from kubani.framework.temporal import run_agent_activity

        await workflow.execute_activity(
            run_agent_activity,
            args=[
                "discord-notifier",
                f"""Send a notification to channel: {input.notify_channel}

{message}

Resource: {input.namespace}/{input.resource_kind}/{input.resource_name}
Reason: {input.reason}

Format as a simple Discord embed.
Return JSON with: message_id, success""",
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

    async def _store_learning(self, input: RemediationInput) -> None:
        """Store learning from this remediation."""
        from kubani.framework.temporal import store_learning_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Recording learning",
            phase="learn",
        )

        # Determine learning type based on outcome
        if self._result.verified:
            learning_type = "successful_remediation"
            confidence = 0.9
        elif self._result.escalated:
            learning_type = "escalation_pattern"
            confidence = 0.6
        else:
            learning_type = "remediation_attempt"
            confidence = 0.5

        result = await workflow.execute_activity(
            store_learning_activity,
            args=[
                "k8s-monitor",
                learning_type,
                f"""Issue: {input.reason} on {input.resource_kind}/{input.resource_name}
Classification: {self._classification}
Skills matched: {self._result.skills_matched}
Steps applied: {self._remediation_steps}
Outcome: {"verified" if self._result.verified else "escalated" if self._result.escalated else "unknown"}""",
                confidence,
                {
                    "event_id": input.event_id,
                    "resource_kind": input.resource_kind,
                    "reason": input.reason,
                    "verified": self._result.verified,
                    "escalated": self._result.escalated,
                },
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        self._result.learning_stored = result.get("success", False)
        self._log_event("learning_stored", f"Type: {learning_type}")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_json_from_result(self, result: str) -> dict[str, Any]:
        """Parse JSON object from agent result."""
        import json

        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass
        return {}

    def _build_result(self) -> dict[str, Any]:
        """Build result dictionary."""
        return {
            "event_id": self._result.event_id,
            "classification": self._result.classification,
            "skills_matched": self._result.skills_matched,
            "remediation_applied": self._result.remediation_applied,
            "remediation_steps": self._result.remediation_steps,
            "verified": self._result.verified,
            "escalated": self._result.escalated,
            "learning_stored": self._result.learning_stored,
            "success": self._result.success,
            "error": self._result.error,
        }

    # =========================================================================
    # Additional Queries
    # =========================================================================

    @workflow.query
    def get_remediation_stats(self) -> dict[str, Any]:
        """Query remediation statistics."""
        return {
            "event_id": self._result.event_id,
            "classification": self._classification,
            "skills_matched": len(self._matched_skills),
            "steps_executed": len(self._remediation_steps),
            "verified": self._result.verified,
            "escalated": self._result.escalated,
        }
