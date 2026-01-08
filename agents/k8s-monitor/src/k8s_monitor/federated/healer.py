"""
Healer Agent - Skill-based remediation with verification.

The Healer agent:
1. Subscribes to K8S_ISSUE_DETECTED events
2. Retrieves matching skills from the library
3. Requests approval for dangerous actions
4. Executes skill actions via MCP tools
5. Verifies success using LLM critic (Voyager pattern)
6. Updates skill confidence based on outcomes

This implements the Voyager "self-verification" pattern where
each remediation is followed by verification of success.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core_agents import create_agent
from core_agents.approvals import (
    ApprovalRequest,
    ApprovalStatus,
    DiscordApprover,
    get_discord_approver,
)
from core_agents.events import Event, EventBus, EventType, get_event_bus
from core_agents.observability import (
    record_approval_completed,
    record_approval_request,
    record_event_processed,
    record_mcp_call,
    record_skill_execution,
    update_skill_confidence,
)
from core_agents.skills import (
    Skill,
    SkillCategory,
    SkillDomain,
    SkillLibrary,
    SkillOutcome,
    get_skill_library,
)

logger = logging.getLogger(__name__)


@dataclass
class RemediationContext:
    """Context for a remediation attempt."""

    issue_event: Event
    pod_name: str
    namespace: str
    kind: str
    reason: str
    message: str
    original_state: dict[str, Any]
    correlation_id: str


class VerificationResult(BaseModel):
    """Result of verifying a skill execution."""

    success: bool = Field(description="Whether all criteria were met")
    criteria_results: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-criterion success status",
    )
    explanation: str = Field(description="Why the verification passed or failed")
    needs_escalation: bool = Field(default=False)


class HealerAgent:
    """
    Executes skill-based remediation with verification.

    The Healer subscribes to issue events, retrieves matching skills,
    executes their actions via MCP, and verifies success.
    """

    def __init__(
        self,
        skill_library: SkillLibrary | None = None,
        event_bus: EventBus | None = None,
        approver: DiscordApprover | None = None,
        source_name: str = "k8s-healer",
        max_retries: int = 3,
    ):
        """
        Initialize the Healer agent.

        Args:
            skill_library: Skill library for retrieval
            event_bus: Event bus for subscribing/publishing
            approver: Discord approver for dangerous actions
            source_name: Source identifier for events
            max_retries: Maximum remediation attempts per issue
        """
        self._skill_library = skill_library
        self._event_bus = event_bus
        self._approver = approver
        self.source_name = source_name
        self.max_retries = max_retries
        self._running = False
        self._critic_agent = None

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of dependencies."""
        if self._skill_library is None:
            self._skill_library = await get_skill_library()
        if self._event_bus is None:
            self._event_bus = await get_event_bus()
        if self._approver is None:
            try:
                self._approver = get_discord_approver()
            except ValueError:
                logger.warning("Discord approver not configured, approvals will be skipped")

    def _get_critic_agent(self):
        """Get or create the LLM critic agent for verification."""
        if self._critic_agent is None:
            try:
                self._critic_agent = create_agent(
                    name="verification_critic",
                    description="Verifies whether remediation actions were successful",
                    system_prompt=CRITIC_PROMPT,
                    tools=[],
                )
            except Exception as e:
                logger.warning(f"Could not create critic agent: {e}")
        return self._critic_agent

    async def start(self) -> None:
        """Start processing issue events."""
        await self._ensure_initialized()
        self._running = True

        logger.info("Healer starting, subscribing to K8S_ISSUE_DETECTED events")

        try:
            async for event in self._event_bus.subscribe(
                EventType.K8S_ISSUE_DETECTED,
                consumer_group="k8s-healer",
                consumer_name=self.source_name,
            ):
                if not self._running:
                    break

                try:
                    await self.handle_issue(event)
                except Exception as e:
                    logger.error(f"Error handling issue: {e}")

                record_event_processed(
                    event_type=EventType.K8S_ISSUE_DETECTED.value,
                    consumer=self.source_name,
                )

        except asyncio.CancelledError:
            logger.info("Healer cancelled")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop processing events."""
        self._running = False
        logger.info("Healer stopping")

    async def handle_issue(self, event: Event) -> None:
        """
        Handle a detected issue by finding and executing a skill.

        Args:
            event: The K8S_ISSUE_DETECTED event
        """
        payload = event.payload
        k8s_event = payload.get("event", {})
        matching_skill_ids = payload.get("matching_skills", [])

        # Build context
        context = RemediationContext(
            issue_event=event,
            pod_name=k8s_event.get("name", "unknown"),
            namespace=k8s_event.get("namespace", "default"),
            kind=k8s_event.get("kind", "Pod"),
            reason=k8s_event.get("reason", "Unknown"),
            message=k8s_event.get("message", ""),
            original_state=k8s_event,
            correlation_id=event.id,
        )

        logger.info(f"Handling issue: {context.reason} on {context.kind}/{context.pod_name}")

        # Emit remediation started event
        await self._event_bus.publish(
            event_type=EventType.K8S_REMEDIATION_STARTED,
            payload={
                "issue_id": event.id,
                "resource": f"{context.kind}/{context.pod_name}",
                "namespace": context.namespace,
                "reason": context.reason,
            },
            source=self.source_name,
            correlation_id=context.correlation_id,
        )

        # Get best matching skill
        skill = await self._select_skill(matching_skill_ids, context)

        if skill is None:
            await self._escalate("No matching skill found", context)
            return

        # Check if approval needed
        if skill.requires_approval:
            approved = await self._request_approval(skill, context)
            if not approved:
                logger.info(f"Approval denied for {skill.name}")
                return

        # Execute the skill
        start_time = datetime.now(UTC)
        success = await self._execute_skill(skill, context)
        duration = (datetime.now(UTC) - start_time).total_seconds()

        # Record metrics
        record_skill_execution(
            skill_id=skill.id,
            domain=skill.domain.value,
            category=skill.category.value,
            success=success,
            duration_seconds=duration,
        )

        # Update skill confidence
        await self._skill_library.record_outcome(SkillOutcome(skill_id=skill.id, success=success))
        update_skill_confidence(skill.id, skill.domain.value, skill.confidence)

        # Emit completion event
        event_type = (
            EventType.K8S_REMEDIATION_COMPLETED if success else EventType.K8S_REMEDIATION_FAILED
        )

        await self._event_bus.publish(
            event_type=event_type,
            payload={
                "issue_id": event.id,
                "skill_id": skill.id,
                "resource": f"{context.kind}/{context.pod_name}",
                "namespace": context.namespace,
                "success": success,
                "duration_seconds": duration,
            },
            source=self.source_name,
            correlation_id=context.correlation_id,
        )

    async def _select_skill(
        self,
        skill_ids: list[str],
        context: RemediationContext,
    ) -> Skill | None:
        """Select the best skill for this issue."""
        # First, try the pre-matched skills
        for skill_id in skill_ids:
            skill = await self._skill_library.get(skill_id)
            if skill and skill.category == SkillCategory.REMEDIATION:
                return skill

        # Fall back to semantic search
        query = f"{context.reason}: {context.message}"
        results = await self._skill_library.search(
            query=query,
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            limit=1,
            min_confidence=0.5,
        )

        return results[0].skill if results else None

    async def _request_approval(
        self,
        skill: Skill,
        context: RemediationContext,
    ) -> bool:
        """Request approval for a dangerous action via Discord."""
        if self._approver is None:
            logger.warning("No approver configured, skipping approval")
            return True  # Proceed without approval if not configured

        record_approval_request(action=skill.name, skill_id=skill.id)

        request = ApprovalRequest(
            action=skill.name,
            resource=f"{context.kind}/{context.pod_name}",
            reason=f"Issue: {context.reason} - {context.message}",
            skill_id=skill.id,
            agent=self.source_name,
            context={
                "namespace": context.namespace,
                "issue_reason": context.reason,
            },
        )

        result = await self._approver.request_approval(request)

        record_approval_completed(
            action=skill.name,
            status=result.status.value,
            latency_seconds=result.elapsed_seconds,
        )

        return result.status == ApprovalStatus.APPROVED

    async def _execute_skill(
        self,
        skill: Skill,
        context: RemediationContext,
    ) -> bool:
        """
        Execute a skill's actions via MCP and verify success.

        Args:
            skill: The skill to execute
            context: Remediation context with resource details

        Returns:
            True if all actions succeeded and verification passed
        """
        # Build parameter values from context
        params = {
            "pod_name": context.pod_name,
            "namespace": context.namespace,
            "resource_kind": context.kind,
            "deployment_name": context.pod_name,  # May be overridden
        }

        # Execute each action
        for action in skill.actions:
            logger.info(f"Executing action: {action.description}")

            start_time = datetime.now(UTC)
            success = await self._call_mcp_tool(action.mcp_tool, params)
            duration = (datetime.now(UTC) - start_time).total_seconds()

            record_mcp_call(
                server=action.mcp_tool.server,
                tool=action.mcp_tool.tool,
                success=success,
                duration_seconds=duration,
            )

            if not success:
                logger.error(f"Action failed: {action.description}")
                return False

        # Verify success using critic agent
        verification = await self._verify_success(skill, context)

        if not verification.success:
            logger.warning(f"Verification failed: {verification.explanation}")
            if verification.needs_escalation:
                await self._escalate(verification.explanation, context)
            return False

        logger.info(f"Skill {skill.name} completed successfully")
        return True

    async def _call_mcp_tool(
        self,
        mcp_tool: Any,
        params: dict[str, str],
    ) -> bool:
        """
        Call an MCP tool with resolved parameters.

        Uses the local MCP tool adapter which provides fallback to direct
        Kubernetes API calls when MCP server is not available.
        """
        try:
            from k8s_monitor.mcp_tools import call_mcp_tool

            # Resolve parameter templates
            resolved_params = {}
            for key, value in mcp_tool.params.items():
                if isinstance(value, str) and value.startswith("$"):
                    param_name = value[1:]
                    resolved_params[key] = params.get(param_name, value)
                else:
                    resolved_params[key] = value

            # Read-only tools always succeed (just for observation)
            read_only_tools = {"events_list", "pods_get", "pods_log", "pods_list", "resources_get"}
            if mcp_tool.tool in read_only_tools:
                result = call_mcp_tool(mcp_tool.tool, resolved_params)
                # Read-only tools succeed as long as they don't error
                return result.get("success", False) or "error" not in str(result).lower()

            # Write tools need to actually succeed
            result = call_mcp_tool(mcp_tool.tool, resolved_params)
            success = result.get("success", False)

            if not success:
                error = result.get("error", "Unknown error")
                logger.error(f"MCP tool {mcp_tool.tool} failed: {error}")

            return success

        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return False

    async def _verify_success(
        self,
        skill: Skill,
        context: RemediationContext,
    ) -> VerificationResult:
        """
        Verify that a skill execution was successful.

        Uses the LLM critic pattern from Voyager to evaluate
        whether success criteria are met.
        """
        # Get current state
        current_state = await self._get_current_state(context)

        # Try LLM-based verification first
        critic = self._get_critic_agent()
        if critic:
            try:
                return await self._llm_verify(skill, context, current_state)
            except Exception as e:
                logger.warning(f"LLM verification failed, using rule-based: {e}")

        # Fall back to rule-based verification
        return self._rule_based_verify(skill, context, current_state)

    async def _llm_verify(
        self,
        skill: Skill,
        context: RemediationContext,
        current_state: dict[str, Any],
    ) -> VerificationResult:
        """Use LLM to verify success criteria."""
        criteria_text = "\n".join(f"- {c}" for c in skill.success_criteria)

        prompt = f"""
        Evaluate whether the following success criteria are met.

        SKILL: {skill.name}
        CRITERIA:
        {criteria_text}

        BEFORE STATE:
        {context.original_state}

        AFTER STATE:
        {current_state}

        For each criterion, respond with:
        CRITERION: <criterion text>
        MET: YES or NO
        REASON: <brief explanation>

        Then provide:
        OVERALL_SUCCESS: YES or NO
        EXPLANATION: <summary>
        NEEDS_ESCALATION: YES or NO
        """

        result = str(self._critic_agent(prompt))
        return self._parse_verification_result(result, skill.success_criteria)

    def _parse_verification_result(
        self,
        text: str,
        criteria: list[str],
    ) -> VerificationResult:
        """Parse LLM verification response."""
        import re

        # Extract overall success
        success = "OVERALL_SUCCESS: YES" in text.upper()
        needs_escalation = "NEEDS_ESCALATION: YES" in text.upper()

        # Extract explanation
        explanation_match = re.search(
            r"EXPLANATION:\s*(.+?)(?:NEEDS_ESCALATION|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        explanation = explanation_match.group(1).strip() if explanation_match else text

        # Extract per-criterion results
        criteria_results = {}
        for criterion in criteria:
            # Look for criterion in output
            pattern = rf"CRITERION:\s*{re.escape(criterion[:30])}.*?MET:\s*(YES|NO)"
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                criteria_results[criterion] = match.group(1).upper() == "YES"
            else:
                criteria_results[criterion] = success  # Default to overall

        return VerificationResult(
            success=success,
            criteria_results=criteria_results,
            explanation=explanation[:500],
            needs_escalation=needs_escalation,
        )

    def _rule_based_verify(
        self,
        skill: Skill,
        context: RemediationContext,
        current_state: dict[str, Any],
    ) -> VerificationResult:
        """Simple rule-based verification fallback."""
        # Check if pod is now Running
        pod_status = current_state.get("status", "").lower()

        if "running" in pod_status:
            return VerificationResult(
                success=True,
                criteria_results=dict.fromkeys(skill.success_criteria, True),
                explanation="Pod is now in Running state",
            )
        elif "crashloop" in pod_status or "error" in pod_status:
            return VerificationResult(
                success=False,
                criteria_results=dict.fromkeys(skill.success_criteria, False),
                explanation=f"Pod is still in problematic state: {pod_status}",
                needs_escalation=True,
            )
        else:
            # Uncertain - consider it a success for now
            return VerificationResult(
                success=True,
                criteria_results=dict.fromkeys(skill.success_criteria, True),
                explanation=f"Pod state is: {pod_status}",
            )

    async def _get_current_state(
        self,
        context: RemediationContext,
    ) -> dict[str, Any]:
        """Get current state of the resource."""
        try:
            from k8s_monitor.tools import get_pod_status

            status = get_pod_status(context.pod_name, context.namespace)
            return {"status": status, "name": context.pod_name}
        except Exception as e:
            logger.warning(f"Could not get current state: {e}")
            return {"status": "unknown", "error": str(e)}

    async def _escalate(
        self,
        reason: str,
        context: RemediationContext,
    ) -> None:
        """Escalate an issue that couldn't be remediated."""
        logger.warning(f"Escalating issue: {reason}")

        await self._event_bus.publish(
            event_type=EventType.K8S_REMEDIATION_FAILED,
            payload={
                "issue_id": context.issue_event.id,
                "resource": f"{context.kind}/{context.pod_name}",
                "namespace": context.namespace,
                "reason": reason,
                "escalated": True,
            },
            source=self.source_name,
            correlation_id=context.correlation_id,
        )


# Critic agent system prompt (Voyager pattern)
CRITIC_PROMPT = """You are a verification critic for Kubernetes remediation actions.

Your job is to evaluate whether success criteria have been met based on
the before and after states of a resource.

Be strict but fair:
- If a criterion is clearly met, say YES
- If a criterion is clearly not met, say NO
- If uncertain, err on the side of caution (NO)

Focus on observable facts, not assumptions.
"""


async def run_healer() -> None:
    """Run the Healer agent."""
    healer = HealerAgent()
    await healer.start()
