"""
Approved Execution - executes risky actions with human approval and learning.

This module provides the core workflow for approval-gated execution:
1. Query past similar approvals from memory
2. Request approval via Discord with historical context
3. Execute action using elevated kubernetes-mcp-executor
4. Verify the outcome
5. Store learning for future reference
6. Post outcome to Discord

Usage:
    from core_agents.approvals import ApprovedExecutor

    executor = ApprovedExecutor(agent_name="cluster-swarm")

    result = await executor.execute_with_approval(
        action="delete_pod",
        resource="pods/promtail-9w26g",
        namespace="monitoring",
        issue_pattern="timeout",
        risk_level=RiskLevel.MEDIUM,
        execute_fn=lambda client: client.call_tool("pods_delete", {...}),
        verify_fn=lambda client: check_pod_restarted(...),
    )
"""

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from core_agents.approvals.discord import get_discord_approver
from core_agents.approvals.learning import (
    ActionOutcome,
    ApprovalLearning,
    PastApprovalMatch,
    PastApprovalSummary,
    RiskLevel,
    calculate_confidence,
)
from core_agents.approvals.schema import ApprovalRequest, ApprovalResult, ApprovalStatus
from core_agents.integrations.discord_mcp import send_discord_message

logger = logging.getLogger(__name__)


# Type aliases
ExecuteFunction = Callable[[Any], Awaitable[dict[str, Any]]]
VerifyFunction = Callable[[Any], Awaitable[bool]]


class ApprovedExecutor:
    """
    Executes risky Kubernetes actions with human approval and learning.

    Provides the full lifecycle:
    - Query past similar incidents
    - Request approval with historical context
    - Execute using elevated permissions
    - Verify outcome
    - Store learning
    """

    def __init__(
        self,
        agent_name: str,
        approval_channel: str | None = None,
        notification_channel: str | None = None,
        approval_timeout: int = 300,
    ):
        """
        Initialize the executor.

        Args:
            agent_name: Name of the agent using this executor
            approval_channel: Discord channel for approvals (default: kubani-approvals)
            notification_channel: Discord channel for status updates (default: agent's channel)
            approval_timeout: Timeout for approval requests in seconds
        """
        self.agent_name = agent_name
        self.approval_channel = approval_channel or os.getenv(
            "DISCORD_APPROVAL_CHANNEL", "kubani-approvals"
        )
        self.notification_channel = notification_channel or os.getenv("DISCORD_CHANNEL", agent_name)
        self.approval_timeout = approval_timeout
        self._approver = get_discord_approver()
        self._approver.channel_name = self.approval_channel

    async def execute_with_approval(
        self,
        action: str,
        resource: str,
        namespace: str,
        issue_pattern: str,
        risk_level: RiskLevel,
        reason: str,
        execute_fn: ExecuteFunction,
        verify_fn: VerifyFunction | None = None,
        correlation_id: str | None = None,
        context: dict[str, Any] | None = None,
        mcp_client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Execute an action with approval workflow.

        Args:
            action: Action name (e.g., "delete_pod", "scale_deployment")
            resource: Resource being acted on (e.g., "pods/my-pod")
            namespace: Kubernetes namespace
            issue_pattern: Issue pattern type (e.g., "timeout", "oom")
            risk_level: Risk level of the action
            reason: Reason for the action
            execute_fn: Async function to execute the action (receives mcp_client)
            verify_fn: Optional async function to verify success (receives mcp_client)
            correlation_id: Optional correlation ID for the incident
            context: Additional context for the approval request
            mcp_client: MCP client for execution (will create if not provided)

        Returns:
            Dict with execution result and learning details
        """
        learning_id = str(uuid.uuid4())[:8]
        resource_parts = resource.split("/")
        resource_type = resource_parts[0] if len(resource_parts) > 1 else "unknown"
        resource_name = resource_parts[-1]

        # Start building the learning record
        learning = ApprovalLearning(
            learning_id=learning_id,
            correlation_id=correlation_id,
            issue_pattern=issue_pattern,
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            action=action,
            risk_level=risk_level,
            approval_status="pending",
            approval_requested_at=datetime.utcnow(),
            resolution_summary="In progress",
            agent=self.agent_name,
            tags=[issue_pattern, namespace, action],
        )

        try:
            # Step 1: Query past similar approvals
            past_summary = await self._query_past_approvals(
                issue_pattern=issue_pattern,
                action=action,
                namespace=namespace,
            )

            # Step 2: Check if auto-approval is appropriate
            if risk_level == RiskLevel.LOW:
                logger.info(f"Auto-approving low-risk action: {action} on {resource}")
                learning.approval_status = "auto_approved"
                learning.approval_responded_at = datetime.utcnow()
                approval_result = ApprovalResult(
                    request_id=learning_id,
                    status=ApprovalStatus.APPROVED,
                    approved=True,
                    responder="auto",
                    requested_at=learning.approval_requested_at,
                )
            else:
                # Step 3: Request approval via Discord
                approval_result = await self._request_approval(
                    action=action,
                    resource=resource,
                    namespace=namespace,
                    reason=reason,
                    past_summary=past_summary,
                    context=context or {},
                    learning_id=learning_id,
                )

                learning.approval_status = approval_result.status.value
                learning.approved_by = approval_result.responder
                learning.approval_responded_at = approval_result.responded_at
                learning.approval_duration_seconds = approval_result.elapsed_seconds

            # Step 4: Execute if approved
            if not approval_result.approved:
                learning.action_executed = False
                learning.resolution_summary = f"Action not approved: {approval_result.status.value}"
                await self._post_outcome(learning, approved=False)
                await self._store_learning(learning)
                return {
                    "success": False,
                    "approved": False,
                    "status": approval_result.status.value,
                    "learning_id": learning_id,
                }

            # Execute the action
            learning.action_executed = True
            execution_result = await self._execute_action(
                execute_fn=execute_fn,
                mcp_client=mcp_client,
            )

            if execution_result.get("error"):
                learning.action_outcome = ActionOutcome.FAILURE
                learning.execution_error = execution_result.get("error")
                learning.resolution_summary = f"Execution failed: {learning.execution_error}"
            else:
                learning.action_outcome = ActionOutcome.SUCCESS

                # Step 5: Verify if function provided
                if verify_fn:
                    try:
                        learning.verification_passed = await verify_fn(mcp_client)
                        learning.verification_details = (
                            "Verification passed"
                            if learning.verification_passed
                            else "Verification failed"
                        )
                        if not learning.verification_passed:
                            learning.action_outcome = ActionOutcome.PARTIAL
                    except Exception as e:
                        learning.verification_passed = False
                        learning.verification_details = f"Verification error: {e}"
                        learning.action_outcome = ActionOutcome.PARTIAL

                learning.resolution_summary = self._build_resolution_summary(learning)

            # Step 6: Calculate confidence and store learning
            learning.confidence = calculate_confidence(
                learning.action_outcome,
                learning.verification_passed,
                learning.approval_status,
            )

            await self._post_outcome(learning, approved=True)
            await self._store_learning(learning)

            return {
                "success": learning.action_outcome == ActionOutcome.SUCCESS,
                "approved": True,
                "approved_by": learning.approved_by,
                "action_outcome": learning.action_outcome.value
                if learning.action_outcome
                else None,
                "verification_passed": learning.verification_passed,
                "learning_id": learning_id,
                "resolution_summary": learning.resolution_summary,
            }

        except Exception as e:
            logger.error(f"Error in execute_with_approval: {e}", exc_info=True)
            learning.action_outcome = ActionOutcome.FAILURE
            learning.execution_error = str(e)
            learning.resolution_summary = f"Error: {e}"
            await self._store_learning(learning)
            return {
                "success": False,
                "error": str(e),
                "learning_id": learning_id,
            }

    async def _query_past_approvals(
        self,
        issue_pattern: str,
        action: str,
        namespace: str,
    ) -> PastApprovalSummary:
        """Query memory for similar past approvals."""
        try:
            from memory_mcp.tools import query_learnings

            # Query for similar approval learnings
            query = f"approval {issue_pattern} {action} {namespace}"
            result = await query_learnings(
                query=query,
                agent_id=self.agent_name,
                learning_type="approval",
                limit=10,
            )

            if not result or not result.get("learnings"):
                return PastApprovalSummary(
                    total_similar=0,
                    approved_count=0,
                    rejected_count=0,
                    success_count=0,
                    success_rate=0.0,
                )

            learnings = result["learnings"]
            matches = []
            approved_count = 0
            success_count = 0

            for learning in learnings:
                ctx = learning.get("context", {})
                if ctx.get("approval_status") == "approved":
                    approved_count += 1
                    if ctx.get("action_outcome") == "success":
                        success_count += 1

                matches.append(
                    PastApprovalMatch(
                        learning_id=learning.get("learning_id", ""),
                        issue_pattern=ctx.get("issue_pattern", issue_pattern),
                        action=ctx.get("action", action),
                        approval_status=ctx.get("approval_status", "unknown"),
                        action_outcome=ActionOutcome(ctx["action_outcome"])
                        if ctx.get("action_outcome")
                        else None,
                        approved_by=ctx.get("approved_by"),
                        resolution_summary=learning.get("content", "")[:200],
                        confidence=learning.get("confidence", 0.5),
                        timestamp=datetime.fromisoformat(
                            learning.get("timestamp", datetime.utcnow().isoformat())
                        ),
                        relevance_score=learning.get("relevance_score", 0.0),
                    )
                )

            rejected_count = len(learnings) - approved_count
            success_rate = success_count / approved_count if approved_count > 0 else 0.0

            return PastApprovalSummary(
                total_similar=len(learnings),
                approved_count=approved_count,
                rejected_count=rejected_count,
                success_count=success_count,
                success_rate=success_rate,
                last_similar=matches[0] if matches else None,
                matches=matches[:5],
            )

        except ImportError:
            logger.warning("Memory MCP not available, skipping past approval query")
            return PastApprovalSummary(
                total_similar=0,
                approved_count=0,
                rejected_count=0,
                success_count=0,
                success_rate=0.0,
            )
        except Exception as e:
            logger.error(f"Error querying past approvals: {e}")
            return PastApprovalSummary(
                total_similar=0,
                approved_count=0,
                rejected_count=0,
                success_count=0,
                success_rate=0.0,
            )

    async def _request_approval(
        self,
        action: str,
        resource: str,
        namespace: str,
        reason: str,
        past_summary: PastApprovalSummary,
        context: dict[str, Any],
        learning_id: str,
    ) -> ApprovalResult:
        """Request approval via Discord."""
        # Build context with past experience
        full_context = {
            "namespace": namespace,
            **context,
        }

        # Add past experience if available
        if past_summary.total_similar > 0:
            full_context["past_experience"] = past_summary.format_for_discord()

        request = ApprovalRequest(
            id=learning_id,
            action=action,
            resource=resource,
            reason=reason,
            agent=self.agent_name,
            context=full_context,
            timeout_seconds=self.approval_timeout,
        )

        logger.info(f"Requesting approval for {action} on {resource}")
        return await self._approver.request_approval(request)

    async def _execute_action(
        self,
        execute_fn: ExecuteFunction,
        mcp_client: Any | None,
    ) -> dict[str, Any]:
        """Execute the action using the executor MCP client."""
        try:
            # If no client provided, create one for the executor
            if mcp_client is None:
                mcp_client = await self._create_executor_client()

            result = await execute_fn(mcp_client)
            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _create_executor_client(self) -> Any:
        """Create MCP client for kubernetes-mcp-executor."""
        from mcp.client.streamable_http import streamablehttp_client
        from strands.tools.mcp import MCPClient

        mcp_url = os.getenv(
            "KUBERNETES_EXECUTOR_MCP_URL",
            "https://kubernetes-executor.almckay.io",
        )
        if not mcp_url.endswith("/mcp"):
            mcp_url = f"{mcp_url}/mcp"

        logger.debug(f"Connecting to Kubernetes executor at {mcp_url}")
        return MCPClient(lambda: streamablehttp_client(mcp_url))

    async def _post_outcome(self, learning: ApprovalLearning, approved: bool) -> None:
        """Post outcome to Discord."""
        try:
            if approved and learning.action_executed:
                emoji = "✅" if learning.action_outcome == ActionOutcome.SUCCESS else "⚠️"
                status = (
                    "SUCCESS" if learning.action_outcome == ActionOutcome.SUCCESS else "PARTIAL"
                )

                message = f"""{emoji} **Action Completed**

**Action:** `{learning.action}` on `{learning.resource_type}/{learning.resource_name}`
**Namespace:** `{learning.namespace}`
**Approved by:** @{learning.approved_by or "auto"}
**Result:** {status}"""

                if learning.verification_passed is not None:
                    message += f"\n**Verification:** {'passed' if learning.verification_passed else 'failed'}"

                message += (
                    f"\n\n_Learning stored for future reference (ID: {learning.learning_id})_"
                )

            elif not approved:
                message = f"""❌ **Action Not Executed**

**Action:** `{learning.action}` on `{learning.resource_type}/{learning.resource_name}`
**Status:** {learning.approval_status}
**Reason:** Approval not granted

_This outcome has been recorded for learning_"""

            else:
                message = f"""🚨 **Action Failed**

**Action:** `{learning.action}` on `{learning.resource_type}/{learning.resource_name}`
**Error:** {learning.execution_error or "Unknown error"}

_This failure has been recorded for learning_"""

            await send_discord_message(
                content=message,
                channel_name=self.approval_channel,
            )

        except Exception as e:
            logger.error(f"Failed to post outcome to Discord: {e}")

    async def _store_learning(self, learning: ApprovalLearning) -> None:
        """Store the learning in memory."""
        try:
            from memory_mcp.tools import store_learning

            await store_learning(
                agent_id=self.agent_name,
                learning_type="approval",
                content=learning.to_learning_content(),
                confidence=learning.confidence,
                context=learning.to_context_dict(),
                tags=learning.tags,
            )
            logger.info(f"Stored approval learning: {learning.learning_id}")

        except ImportError:
            logger.warning("Memory MCP not available, skipping learning storage")
        except Exception as e:
            logger.error(f"Failed to store learning: {e}")

    def _build_resolution_summary(self, learning: ApprovalLearning) -> str:
        """Build a human-readable resolution summary."""
        parts = [f"Action {learning.action} on {learning.resource_name}"]

        if learning.approval_status == "auto_approved":
            parts.append("(auto-approved)")
        elif learning.approved_by:
            parts.append(f"approved by {learning.approved_by}")

        if learning.action_outcome:
            parts.append(f"- {learning.action_outcome.value}")

        if learning.verification_passed is not None:
            parts.append(f"- verification {'passed' if learning.verification_passed else 'failed'}")

        return " ".join(parts)


# Convenience function for simple use cases
async def execute_with_approval(
    agent_name: str,
    action: str,
    resource: str,
    namespace: str,
    issue_pattern: str,
    risk_level: RiskLevel,
    reason: str,
    execute_fn: ExecuteFunction,
    verify_fn: VerifyFunction | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    Execute an action with approval workflow.

    Convenience function that creates an executor and runs the workflow.
    See ApprovedExecutor.execute_with_approval for full documentation.
    """
    executor = ApprovedExecutor(agent_name=agent_name)
    return await executor.execute_with_approval(
        action=action,
        resource=resource,
        namespace=namespace,
        issue_pattern=issue_pattern,
        risk_level=risk_level,
        reason=reason,
        execute_fn=execute_fn,
        verify_fn=verify_fn,
        **kwargs,
    )
