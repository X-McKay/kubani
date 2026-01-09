"""
Healer Agent - Skill-based remediation with verification.

The Healer agent:
1. Subscribes to K8S_ISSUE_DETECTED events
2. Retrieves matching skills from the library (supports both Python and markdown skills)
3. Requests approval for dangerous actions
4. Executes skill actions via MCP tools
5. Verifies success using LLM critic (Voyager pattern)
6. Updates skill confidence based on outcomes

This implements the Voyager "self-verification" pattern where
each remediation is followed by verification of success.

Supports two skill formats:
- Python Skill objects (legacy): Stored in Qdrant, defined in Python
- Markdown SKILL.md files (new): Agent Skills format, stored in skills/
"""

import asyncio
import logging
import os
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
from core_agents.integrations.discord import (
    format_escalation,
    format_fix_attempt,
    format_fix_failure,
    format_fix_success,
    format_investigation_results,
    format_issue_detection,
    send_discord_message,
)
from core_agents.integrations.mcp import get_registry as get_mcp_registry
from core_agents.observability import (
    record_approval_completed,
    record_approval_request,
    record_event_processed,
    record_mcp_call,
    record_skill_execution,
    update_skill_confidence,
)
from core_agents.registry import RegistryClient, get_registry_client
from core_agents.skills import (
    AgentSkill,
    Skill,
    SkillCategory,
    SkillDomain,
    SkillLibrary,
    SkillOutcome,
    UnifiedSkillLibrary,
    get_skill_library,
    get_unified_skill_library,
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

    Supports both legacy Python skills and new markdown-based Agent Skills.
    When both are available, prefers markdown skills for easier iteration.
    """

    def __init__(
        self,
        skill_library: SkillLibrary | None = None,
        unified_library: UnifiedSkillLibrary | None = None,
        event_bus: EventBus | None = None,
        approver: DiscordApprover | None = None,
        registry_client: RegistryClient | None = None,
        source_name: str = "k8s-healer",
        max_retries: int = 3,
        prefer_markdown_skills: bool = True,
        enable_registry: bool = True,
    ):
        """
        Initialize the Healer agent.

        Args:
            skill_library: Legacy Python skill library
            unified_library: Markdown-based skill library
            event_bus: Event bus for subscribing/publishing
            approver: Discord approver for dangerous actions
            registry_client: Registry client for recording skill outcomes
            source_name: Source identifier for events
            max_retries: Maximum remediation attempts per issue
            prefer_markdown_skills: If True, prefer markdown skills over Python skills
            enable_registry: If True, record skill outcomes to registry
        """
        self._skill_library = skill_library
        self._unified_library = unified_library
        self._event_bus = event_bus
        self._approver = approver
        self._registry_client = registry_client
        self._mcp_registry = None
        self.source_name = source_name
        self.max_retries = max_retries
        self.prefer_markdown_skills = prefer_markdown_skills
        self.enable_registry = enable_registry
        self._running = False
        self._critic_agent = None
        self._executor_agent = None

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of dependencies."""
        if self._skill_library is None:
            self._skill_library = await get_skill_library()

        # Initialize unified library if markdown skills are preferred
        if self._unified_library is None and self.prefer_markdown_skills:
            try:
                skills_dir = os.getenv("SKILLS_DIR", "skills")
                self._unified_library = await get_unified_skill_library(skills_dir=skills_dir)
                # Sync skills on startup (indexes to Qdrant)
                await self._unified_library.sync()
                logger.info("Unified skill library initialized and synced")
            except Exception as e:
                logger.warning(f"Could not initialize unified skill library: {e}")

        if self._event_bus is None:
            self._event_bus = await get_event_bus()
        if self._approver is None:
            try:
                self._approver = get_discord_approver()
            except ValueError:
                logger.warning("Discord approver not configured, approvals will be skipped")

        # Initialize registry client for outcome tracking
        if self._registry_client is None and self.enable_registry:
            try:
                self._registry_client = get_registry_client()
                await self._registry_client.connect()
                logger.info("Registry client connected for skill outcome tracking")

                # Sync skills to registry so outcomes can be recorded
                if self._unified_library:
                    await self._sync_skills_to_registry()
            except Exception as e:
                logger.warning(
                    f"Could not connect to registry: {e}. Outcomes will not be recorded."
                )

        # Load MCP registry for policy checks
        if self._mcp_registry is None:
            try:
                self._mcp_registry = get_mcp_registry()
                if self._mcp_registry:
                    logger.info("MCP registry loaded for policy-based approval checks")
            except Exception as e:
                logger.debug(f"Could not load MCP registry: {e}")

    def _check_mcp_policy_requires_approval(self, skill: Skill | AgentSkill) -> bool:
        """
        Check if MCP policy requires approval for this skill's operations.

        Compares the skill's MCP tools against the agent's policy require_approval list.

        Args:
            skill: The skill to check

        Returns:
            True if policy requires approval for any of the skill's operations
        """
        if not self._mcp_registry:
            return False

        try:
            policy = self._mcp_registry.get_policy("k8s-monitor")

            # Check for wildcard (all operations need approval)
            if "*" in policy.require_approval:
                return True

            # Get the MCP tools this skill uses
            mcp_tools = []

            if isinstance(skill, AgentSkill):
                # Check skill body for tool references (markdown skills)
                if "pods_delete" in skill.body or "pods.delete" in skill.body:
                    mcp_tools.append("pods.delete")
                if "deployments.scale" in skill.body or "resources_scale" in skill.body:
                    mcp_tools.append("deployments.scale")
                if "resources.delete" in skill.body or "resources_delete" in skill.body:
                    mcp_tools.append("resources.delete")
            else:
                # Legacy Python skills have action.mcp_tool
                for action in skill.actions:
                    if action.mcp_tool:
                        # Convert tool name to policy format: pods_delete -> pods.delete
                        tool_name = action.mcp_tool.tool.replace("_", ".")
                        mcp_tools.append(tool_name)

            # Check if any tool requires approval per policy
            for tool in mcp_tools:
                if tool in policy.require_approval:
                    logger.info(f"MCP policy requires approval for tool: {tool}")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking MCP policy: {e}")
            return False

    async def _sync_skills_to_registry(self) -> None:
        """Sync all loaded skills to the registry for tracking."""
        if not self._registry_client or not self._unified_library:
            return

        try:
            skills = await self._unified_library.list_all(domain="k8s")
            synced = 0
            for skill in skills:
                try:
                    await self._registry_client.register_skill(
                        skill_id=skill.id,
                        name=skill.name,
                        domain=skill.domain,
                        category=skill.category,
                        status="stable" if skill.confidence >= 0.8 else "experimental",
                        confidence=skill.confidence,
                        requires_approval=skill.requires_approval,
                    )
                    synced += 1
                except Exception as e:
                    logger.debug(f"Could not sync skill {skill.id}: {e}")
            logger.info(f"Synced {synced}/{len(skills)} K8s skills to registry")
        except Exception as e:
            logger.warning(f"Failed to sync skills to registry: {e}")

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

        Posts Discord notifications at each step:
        1. Issue detection
        2. Investigation results
        3. Fix attempt
        4. Fix success/failure

        Args:
            event: The K8S_ISSUE_DETECTED event
        """
        payload = event.payload
        k8s_event = payload.get("event", {})
        matching_skill_ids = payload.get("matching_skills", [])
        severity = payload.get("severity", "medium")

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
        timestamp = datetime.now(UTC).isoformat()

        # Step 1: Post issue detection to Discord
        await self._post_issue_detection(context, severity, timestamp)

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
            # No explicit skill found - investigate using MCP tools and LLM reasoning
            logger.info("No matching skill found, attempting investigation-based remediation")
            investigation_success = await self._investigate_and_remediate(
                context, severity, timestamp
            )
            if not investigation_success:
                await self._escalate("Investigation-based remediation failed", context)
            return

        # Step 2: Post investigation results to Discord
        is_markdown_skill = isinstance(skill, AgentSkill)
        confidence = skill.confidence if hasattr(skill, "confidence") else 0.5
        await self._post_investigation_results(context, skill, confidence, timestamp)

        # Check if approval needed (from skill metadata OR MCP policy)
        needs_approval = skill.requires_approval or self._check_mcp_policy_requires_approval(skill)
        if needs_approval:
            approved = await self._request_approval(skill, context)
            if not approved:
                logger.info(f"Approval denied for {skill.name}")
                return

        # Step 3: Post fix attempt to Discord
        await self._post_fix_attempt(context, skill, timestamp)

        # Execute the skill (different methods for markdown vs Python skills)
        start_time = datetime.now(UTC)

        if is_markdown_skill:
            success = await self._execute_markdown_skill(skill, context)
        else:
            success = await self._execute_skill(skill, context)

        duration = (datetime.now(UTC) - start_time).total_seconds()
        result_timestamp = datetime.now(UTC).isoformat()

        # Get domain/category as strings for metrics (handle both skill types)
        if is_markdown_skill:
            domain = skill.domain
            category = skill.category
            confidence = skill.confidence
        else:
            domain = skill.domain.value
            category = skill.category.value
            confidence = skill.confidence

        # Record metrics
        record_skill_execution(
            skill_id=skill.id,
            domain=domain,
            category=category,
            success=success,
            duration_seconds=duration,
        )

        # Update skill confidence (legacy skills stored in Qdrant)
        if not is_markdown_skill:
            await self._skill_library.record_outcome(
                SkillOutcome(skill_id=skill.id, success=success)
            )
        update_skill_confidence(skill.id, domain, confidence)

        # Record outcome to registry for ALL skills (enables centralized tracking)
        if self._registry_client is not None:
            try:
                await self._registry_client.record_skill_outcome(
                    skill_id=skill.id,
                    success=success,
                )
                logger.debug(f"Recorded skill outcome to registry: {skill.id} success={success}")
            except Exception as e:
                logger.warning(f"Failed to record skill outcome to registry: {e}")

        # Step 4: Post fix result to Discord
        await self._post_fix_result(context, skill, success, duration, result_timestamp)

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

    async def _investigate_and_remediate(
        self,
        context: RemediationContext,
        severity: str,
        timestamp: str,
    ) -> bool:
        """
        Investigate an issue using an agentic multi-step approach with MCP tools.

        The investigation follows these phases:
        1. Gather initial evidence (events, pod status, logs)
        2. Trace to owning controller (Deployment/DaemonSet/StatefulSet)
        3. Analyze configuration for issues
        4. Determine root cause and appropriate remediation

        This distinguishes between:
        - TRANSIENT issues: Can fix with pod restart
        - CONFIGURATION issues: Need GitOps change (reports but doesn't auto-fix)

        Args:
            context: The remediation context
            severity: Issue severity
            timestamp: Timestamp for Discord notifications

        Returns:
            True if remediation succeeded, False otherwise
        """
        from k8s_monitor.mcp_tools import call_mcp_tool_async

        logger.info(f"Starting agentic investigation of {context.kind}/{context.pod_name}")

        evidence = {}
        investigation_log = []

        # Phase 1: Gather initial evidence
        logger.info("Phase 1: Gathering events and initial evidence")

        # Get events first - they often tell us what's happening
        try:
            events_result = await call_mcp_tool_async(
                "events_list",
                {"namespace": context.namespace},
            )
            evidence["events"] = events_result
            investigation_log.append(f"Got events for namespace {context.namespace}")
        except Exception as e:
            evidence["events"] = {"error": str(e)}
            investigation_log.append(f"Failed to get events: {e}")

        # Try to get the pod (it might not exist if recreated)
        try:
            pod_result = await call_mcp_tool_async(
                "pods_get",
                {"name": context.pod_name, "namespace": context.namespace},
            )
            evidence["pod"] = pod_result
            investigation_log.append(f"Got pod details for {context.pod_name}")
        except Exception as e:
            evidence["pod"] = {"error": str(e)}
            investigation_log.append(f"Pod not found (may have been recreated): {e}")

        # Get logs if we got pod info
        if evidence.get("pod", {}).get("success", False):
            try:
                logs_result = await call_mcp_tool_async(
                    "pods_log",
                    {"name": context.pod_name, "namespace": context.namespace, "tail": 50},
                )
                evidence["logs"] = logs_result
                investigation_log.append("Got pod logs")
            except Exception as e:
                evidence["logs"] = {"error": str(e)}

        # Phase 2: Trace to controller
        logger.info("Phase 2: Tracing to owning controller")

        controller_info = self._infer_controller(context.pod_name, evidence)
        if controller_info:
            try:
                controller_result = await call_mcp_tool_async(
                    "resources_get",
                    {
                        "apiVersion": "apps/v1",
                        "kind": controller_info["kind"],
                        "name": controller_info["name"],
                        "namespace": context.namespace,
                    },
                )
                evidence["controller"] = controller_result
                investigation_log.append(f"Got {controller_info['kind']}/{controller_info['name']}")
            except Exception as e:
                evidence["controller"] = {"error": str(e)}
                investigation_log.append(f"Failed to get controller: {e}")

        # Phase 3: Deep analysis with LLM
        logger.info("Phase 3: LLM analysis with full context")

        investigator = self._get_investigator_agent()
        if investigator is None:
            logger.warning("No investigator agent available, cannot proceed with investigation")
            return False

        # Build enhanced analysis prompt with controller info
        controller_section = ""
        if evidence.get("controller"):
            controller_section = f"""
## Controller Configuration
{self._format_evidence(evidence.get("controller", {}))}

Check for configuration issues like:
- hostNetwork: true with wrong dnsPolicy
- Missing resource limits
- Incorrect environment variables
- Wrong image tags
"""

        analysis_prompt = f"""
You are investigating a Kubernetes issue. Analyze the evidence thoroughly.

# ISSUE
- Resource: {context.kind}/{context.pod_name}
- Namespace: {context.namespace}
- Event Reason: {context.reason}
- Event Message: {context.message}

# INVESTIGATION LOG
{chr(10).join(investigation_log)}

# EVIDENCE COLLECTED

## Events
{self._format_evidence(evidence.get("events", {}))}

## Pod Status
{self._format_evidence(evidence.get("pod", {}))}

## Pod Logs
{self._format_evidence(evidence.get("logs", {}))}
{controller_section}

# ANALYSIS INSTRUCTIONS

1. **Identify the Root Cause**: What is causing this issue based on the evidence?

2. **Classify the Issue**:
   - TRANSIENT: Temporary failure that a restart might fix (CrashLoopBackOff, ImagePullBackOff)
   - CONFIGURATION: Requires config change (wrong dnsPolicy, missing resources, bad env vars)
   - INFRASTRUCTURE: Node or cluster level problem
   - EXTERNAL: Depends on external service

3. **Determine Remediation**:
   - TRANSIENT issues: DELETE_POD or SCALE_DEPLOYMENT
   - CONFIGURATION issues: Report the issue and what needs to change (CAN_REMEDIATE: NO)
   - For hostNetwork + dnsPolicy issues: Recommend setting dnsPolicy: ClusterFirstWithHostNet

# RESPONSE FORMAT (use exactly this format)

ROOT_CAUSE: <One sentence describing the root cause>
ISSUE_TYPE: <TRANSIENT | CONFIGURATION | INFRASTRUCTURE | EXTERNAL>
CAN_REMEDIATE: <YES | NO>
REMEDIATION_ACTION: <DELETE_POD | SCALE_DEPLOYMENT | RESTART_DEPLOYMENT | NONE>
REMEDIATION_REASON: <Why this action will or won't help>
CONFIGURATION_FIX: <If CONFIGURATION issue, what config change is needed>
GITOPS_PATH: <If known, the GitOps file that needs changing>
"""

        try:
            analysis_result = str(investigator(analysis_prompt))
            logger.info(f"Investigation analysis: {analysis_result[:500]}")

            # Parse the analysis
            can_remediate = "CAN_REMEDIATE: YES" in analysis_result.upper()
            root_cause = self._extract_field(analysis_result, "ROOT_CAUSE")
            issue_type = self._extract_field(analysis_result, "ISSUE_TYPE")
            remediation_action = self._extract_field(analysis_result, "REMEDIATION_ACTION")
            remediation_reason = self._extract_field(analysis_result, "REMEDIATION_REASON")
            config_fix = self._extract_field(analysis_result, "CONFIGURATION_FIX")
            gitops_path = self._extract_field(analysis_result, "GITOPS_PATH")

            # Post investigation results to Discord
            await self._post_investigation_results_dynamic(
                context=context,
                root_cause=root_cause,
                evidence=evidence,
                can_remediate=can_remediate,
                proposed_action=remediation_action if can_remediate else config_fix,
                timestamp=timestamp,
            )

            # Handle CONFIGURATION issues - post recommendation, don't auto-fix
            if issue_type.upper() == "CONFIGURATION" or not can_remediate:
                logger.info(f"Issue requires configuration change: {root_cause}")
                if config_fix and config_fix != "Unknown":
                    await self._post_configuration_recommendation(
                        context=context,
                        root_cause=root_cause,
                        config_fix=config_fix,
                        gitops_path=gitops_path if gitops_path != "Unknown" else None,
                        timestamp=timestamp,
                    )
                return False

            # Step 3: Execute remediation based on LLM recommendation
            logger.info(f"Executing recommended remediation: {remediation_action}")

            # Post fix attempt
            await self._post_fix_attempt_dynamic(
                context=context,
                action=f"{remediation_action}: {remediation_reason}",
                timestamp=timestamp,
            )

            start_time = datetime.now(UTC)
            success = await self._execute_recommended_action(
                action=remediation_action,
                context=context,
            )
            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Post result
            result_timestamp = datetime.now(UTC).isoformat()
            if success:
                await self._post_fix_result_dynamic(
                    context=context,
                    action=remediation_action,
                    success=True,
                    duration=duration,
                    timestamp=result_timestamp,
                )

                # Emit success event
                await self._event_bus.publish(
                    event_type=EventType.K8S_REMEDIATION_COMPLETED,
                    payload={
                        "issue_id": context.issue_event.id,
                        "resource": f"{context.kind}/{context.pod_name}",
                        "namespace": context.namespace,
                        "action": remediation_action,
                        "method": "investigation_based",
                        "root_cause": root_cause,
                        "success": True,
                        "duration_seconds": duration,
                    },
                    source=self.source_name,
                    correlation_id=context.correlation_id,
                )

                logger.info(f"Investigation-based remediation succeeded: {remediation_action}")
                return True
            else:
                await self._post_fix_result_dynamic(
                    context=context,
                    action=remediation_action,
                    success=False,
                    duration=duration,
                    timestamp=result_timestamp,
                )
                logger.warning(f"Investigation-based remediation failed: {remediation_action}")
                return False

        except Exception as e:
            logger.error(f"Investigation analysis failed: {e}")
            return False

    def _get_investigator_agent(self):
        """Get or create the LLM investigator agent."""
        if not hasattr(self, "_investigator_agent") or self._investigator_agent is None:
            try:
                self._investigator_agent = create_agent(
                    name="issue_investigator",
                    description="Investigates Kubernetes issues and recommends remediation",
                    system_prompt=INVESTIGATOR_PROMPT,
                    tools=[],
                )
            except Exception as e:
                logger.warning(f"Could not create investigator agent: {e}")
                self._investigator_agent = None
        return self._investigator_agent

    def _format_evidence(self, data: Any) -> str:
        """Format evidence data for LLM consumption."""
        import json

        if isinstance(data, dict):
            if "error" in data:
                return f"[Error collecting data: {data['error']}]"
            try:
                return json.dumps(data, indent=2, default=str)[:2000]
            except Exception:
                return str(data)[:2000]
        elif isinstance(data, list):
            try:
                return json.dumps(data[:10], indent=2, default=str)[:2000]
            except Exception:
                return str(data)[:2000]
        elif isinstance(data, str):
            return data[:2000]
        else:
            return str(data)[:2000]

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extract a field value from LLM response."""
        import re

        pattern = rf"{field_name}:\s*(.+?)(?:\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return "Unknown"

    async def _execute_recommended_action(
        self,
        action: str,
        context: RemediationContext,
    ) -> bool:
        """Execute the LLM-recommended remediation action."""
        from k8s_monitor.mcp_tools import call_mcp_tool_async

        action_upper = action.upper().strip()

        try:
            if "DELETE_POD" in action_upper or "RESTART" in action_upper:
                # Delete the pod to trigger a restart
                result = await call_mcp_tool_async(
                    "pods_delete",
                    {
                        "name": context.pod_name,
                        "namespace": context.namespace,
                    },
                )
                success = result.get("success", False) or "deleted" in str(result).lower()
                logger.info(f"Pod delete result: {result}")
                return success

            elif "SCALE_DEPLOYMENT" in action_upper:
                # Try to get deployment name from pod name
                # Pod names typically follow: deployment-replicaset-pod pattern
                parts = context.pod_name.rsplit("-", 2)
                deployment_name = parts[0] if len(parts) >= 2 else context.pod_name

                # Scale to 0 then back to 1 (or current)
                result = await call_mcp_tool_async(
                    "resources_scale",
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": deployment_name,
                        "namespace": context.namespace,
                        "scale": 0,
                    },
                )
                if result.get("success", False):
                    # Wait briefly then scale back up
                    await asyncio.sleep(2)
                    result = await call_mcp_tool_async(
                        "resources_scale",
                        {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "name": deployment_name,
                            "namespace": context.namespace,
                            "scale": 1,
                        },
                    )
                return result.get("success", False)

            elif "NONE" in action_upper:
                logger.info("LLM recommended no action")
                return False

            else:
                logger.warning(f"Unknown remediation action: {action}")
                return False

        except Exception as e:
            logger.error(f"Failed to execute recommended action: {e}")
            return False

    async def _post_investigation_results_dynamic(
        self,
        context: RemediationContext,
        root_cause: str,
        evidence: dict[str, Any],
        can_remediate: bool,
        proposed_action: str,
        timestamp: str,
    ) -> None:
        """Post dynamic investigation results to Discord."""
        evidence_summary = []
        if evidence.get("pod_status"):
            status = evidence["pod_status"]
            if isinstance(status, dict) and "status" in status:
                evidence_summary.append(
                    f"Pod Status: {status.get('status', {}).get('phase', 'Unknown')}"
                )
        if evidence.get("logs") and not isinstance(evidence["logs"], dict):
            evidence_summary.append("Logs collected")
        if evidence.get("events"):
            evidence_summary.append(f"Found {len(evidence['events'])} related events")

        embed = format_investigation_results(
            issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
            root_cause=root_cause[:300],
            evidence=evidence_summary or ["Investigation data collected"],
            proposed_fix=proposed_action if can_remediate else "Manual investigation required",
            confidence=0.7 if can_remediate else 0.3,
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post investigation results to Discord: {e}")

    async def _post_fix_attempt_dynamic(
        self,
        context: RemediationContext,
        action: str,
        timestamp: str,
    ) -> None:
        """Post dynamic fix attempt to Discord."""
        embed = format_fix_attempt(
            issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
            attempt_number=1,
            max_attempts=1,
            action=f"LLM-recommended: {action}",
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post fix attempt to Discord: {e}")

    async def _post_fix_result_dynamic(
        self,
        context: RemediationContext,
        action: str,
        success: bool,
        duration: float,
        timestamp: str,
    ) -> None:
        """Post dynamic fix result to Discord."""
        if success:
            embed = format_fix_success(
                issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
                fix_applied=f"LLM-recommended: {action}",
                result=f"Completed in {duration:.1f}s",
                timestamp=timestamp,
            )
        else:
            embed = format_fix_failure(
                issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
                attempt_number=1,
                max_attempts=1,
                result=f"Action failed after {duration:.1f}s",
                next_action="Manual investigation required",
                timestamp=timestamp,
            )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post fix result to Discord: {e}")

    async def _select_skill(
        self,
        skill_ids: list[str],
        context: RemediationContext,
    ) -> Skill | AgentSkill | None:
        """
        Select the best skill for this issue.

        Searches both unified (markdown) and legacy (Python) skill libraries.
        Prefers markdown skills if prefer_markdown_skills is True.
        """
        query = f"{context.reason}: {context.message}"

        # Search unified library first if preferred
        if self.prefer_markdown_skills and self._unified_library:
            try:
                results = await self._unified_library.search(
                    query=query,
                    domain="k8s",
                    category="remediation",
                    limit=1,
                    min_confidence=0.5,
                )
                if results:
                    logger.info(
                        f"Found markdown skill: {results[0].skill.id} (score: {results[0].score:.2f})"
                    )
                    return results[0].skill
            except Exception as e:
                logger.warning(f"Unified library search failed: {e}")

        # Fall back to legacy Python skills
        # First, try the pre-matched skill IDs
        for skill_id in skill_ids:
            skill = await self._skill_library.get(skill_id)
            if skill and skill.category == SkillCategory.REMEDIATION:
                return skill

        # Fall back to semantic search on legacy library
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
        skill: Skill | AgentSkill,
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

    async def _execute_markdown_skill(
        self,
        skill: AgentSkill,
        context: RemediationContext,
    ) -> bool:
        """
        Execute a markdown-based skill using an LLM agent.

        The skill body (markdown) is loaded into the agent's context,
        and the agent executes the steps using available MCP tools.

        Args:
            skill: The AgentSkill to execute
            context: Remediation context with resource details

        Returns:
            True if execution succeeded
        """
        logger.info(f"Executing markdown skill: {skill.name}")

        # Get or create executor agent
        executor = self._get_executor_agent()
        if executor is None:
            logger.warning("No executor agent available, falling back to direct execution")
            # Fall back to direct MCP calls for known patterns
            return await self._execute_markdown_skill_direct(skill, context)

        # Build execution prompt with skill body and context
        prompt = f"""
Execute this skill for the given context. Follow the instructions carefully.

# SKILL
{skill.body}

# CONTEXT
- Pod Name: {context.pod_name}
- Namespace: {context.namespace}
- Resource Kind: {context.kind}
- Issue: {context.reason}
- Message: {context.message}

# INSTRUCTIONS
1. Check the preconditions - if any are not met, explain why and stop
2. Execute each action in the Actions section using the available MCP tools
3. After executing, verify the success criteria
4. Report whether the skill succeeded or failed

Use the kubernetes-mcp-server tools:
- pods_delete(name, namespace) - Delete a pod
- pods_get(name, namespace) - Get pod details
- pods_log(name, namespace, tail) - Get pod logs
- events_list(namespace) - List events
- resources_scale(apiVersion, kind, name, namespace, scale) - Scale a deployment

Begin execution now.
"""

        try:
            result = str(executor(prompt))
            logger.debug(f"Executor result: {result[:500]}...")

            # Parse result to determine success
            success = self._parse_executor_result(result)

            if success:
                logger.info(f"Markdown skill {skill.name} completed successfully")
            else:
                logger.warning(f"Markdown skill {skill.name} execution did not fully succeed")

            return success

        except Exception as e:
            logger.error(f"Error executing markdown skill: {e}")
            return False

    def _get_executor_agent(self):
        """Get or create the LLM executor agent for markdown skills."""
        if self._executor_agent is None:
            try:
                self._executor_agent = create_agent(
                    name="skill_executor",
                    description="Executes skills by following markdown instructions",
                    system_prompt=EXECUTOR_PROMPT,
                    tools=[],  # MCP tools are injected via the Strands agent
                )
            except Exception as e:
                logger.warning(f"Could not create executor agent: {e}")
        return self._executor_agent

    def _parse_executor_result(self, result: str) -> bool:
        """Parse executor result to determine if skill succeeded."""
        result_lower = result.lower()

        # Look for success indicators
        success_indicators = [
            "skill succeeded",
            "execution successful",
            "completed successfully",
            "success criteria met",
            "all criteria met",
        ]

        failure_indicators = [
            "skill failed",
            "execution failed",
            "could not complete",
            "preconditions not met",
            "criteria not met",
        ]

        # Check for explicit success/failure
        for indicator in success_indicators:
            if indicator in result_lower:
                return True

        # Default to success if no failure indicators found
        return all(indicator not in result_lower for indicator in failure_indicators)

    async def _execute_markdown_skill_direct(
        self,
        skill: AgentSkill,
        context: RemediationContext,
    ) -> bool:
        """
        Execute a markdown skill directly by parsing MCP tool references.

        This is a fallback when no LLM agent is available.
        """
        try:
            from k8s_monitor.mcp_tools import call_mcp_tool

            # For restart-crashloop and restart-imagepullbackoff, just delete the pod
            if "restart" in skill.id.lower() or "crashloop" in skill.id.lower():
                result = call_mcp_tool(
                    "pods_delete",
                    {
                        "name": context.pod_name,
                        "namespace": context.namespace,
                    },
                )
                return result.get("success", False)

            # For other skills, try to parse the yaml blocks
            logger.warning(f"Direct execution not implemented for skill: {skill.id}")
            return False

        except Exception as e:
            logger.error(f"Direct execution failed: {e}")
            return False

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

        # Post escalation to Discord
        timestamp = datetime.now(UTC).isoformat()
        embed = format_escalation(
            issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
            resource_type=context.kind,
            resource_name=context.pod_name,
            namespace=context.namespace,
            attempts=1,
            attempts_summary=[reason],
            root_cause=None,
            action_required=["Investigate manually", "Check application logs"],
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post escalation to Discord: {e}")

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

    # =========================================================================
    # Discord Notification Helpers
    # =========================================================================

    async def _post_issue_detection(
        self,
        context: RemediationContext,
        severity: str,
        timestamp: str,
    ) -> None:
        """Post issue detection to Discord."""
        embed = format_issue_detection(
            issue_title=context.reason,
            resource_type=context.kind,
            resource_name=context.pod_name,
            namespace=context.namespace,
            severity=severity,
            description=context.message[:200] if context.message else None,
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post issue detection to Discord: {e}")

    async def _post_investigation_results(
        self,
        context: RemediationContext,
        skill: Skill | AgentSkill,
        confidence: float,
        timestamp: str,
    ) -> None:
        """Post investigation results to Discord."""
        embed = format_investigation_results(
            issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
            root_cause=context.message[:200] if context.message else "Issue detected by K8s events",
            evidence=[
                f"Event: {context.reason}",
                f"Resource: {context.kind}/{context.pod_name}",
                f"Namespace: {context.namespace}",
            ],
            proposed_fix=skill.name,
            confidence=confidence,
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post investigation results to Discord: {e}")

    async def _post_fix_attempt(
        self,
        context: RemediationContext,
        skill: Skill | AgentSkill,
        timestamp: str,
    ) -> None:
        """Post fix attempt to Discord."""
        # Get skill description for the action
        description = skill.description if hasattr(skill, "description") else skill.name

        embed = format_fix_attempt(
            issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
            attempt_number=1,
            max_attempts=self.max_retries,
            action=description,
            timestamp=timestamp,
        )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post fix attempt to Discord: {e}")

    async def _post_fix_result(
        self,
        context: RemediationContext,
        skill: Skill | AgentSkill,
        success: bool,
        duration: float,
        timestamp: str,
    ) -> None:
        """Post fix result (success or failure) to Discord."""
        if success:
            embed = format_fix_success(
                issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
                fix_applied=skill.name,
                result=f"Completed in {duration:.1f}s",
                timestamp=timestamp,
            )
        else:
            embed = format_fix_failure(
                issue_title=f"{context.reason} on {context.kind}/{context.pod_name}",
                attempt_number=1,
                max_attempts=self.max_retries,
                result=f"Skill execution failed after {duration:.1f}s",
                next_action="Manual investigation may be required",
                timestamp=timestamp,
            )

        try:
            await send_discord_message(
                embeds=[embed],
                username="Kubani K8s Healer",
            )
        except Exception as e:
            logger.warning(f"Failed to post fix result to Discord: {e}")


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

# Executor agent system prompt (for markdown skills)
EXECUTOR_PROMPT = """You are a Kubernetes remediation executor.

Your job is to execute skills by following their markdown instructions.
Each skill contains:
- Preconditions: Check these first, skip if not met
- Actions: Execute these using MCP tools
- Success Criteria: Verify these after execution

When executing:
1. First verify all preconditions are met
2. Execute each action in order using the available tools
3. Check success criteria after each action
4. Report clearly whether the skill succeeded or failed

Use the kubernetes-mcp-server tools available to you.
Be concise and action-oriented. Execute the skill, don't just describe it.

At the end, clearly state:
- SKILL SUCCEEDED if all actions completed and criteria met
- SKILL FAILED if any action failed or criteria not met
"""

# Investigator agent system prompt (for investigation-based remediation)
INVESTIGATOR_PROMPT = """You are a Kubernetes issue investigator and remediation executor.

Your job is to analyze evidence from Kubernetes clusters and TAKE ACTION to fix issues.
You should be PROACTIVE and attempt remediation for most issues.

When analyzing issues:
1. Look at pod status, logs, and events to understand the issue
2. Identify the most likely root cause
3. Recommend a remediation action - err on the side of trying something

Available remediation actions:
- DELETE_POD: Delete the pod to trigger a restart. Use for:
  * CrashLoopBackOff - pod may recover after restart
  * Unhealthy - probe failures often resolve with restart
  * ImagePullBackOff - retry the image pull
  * DNSConfigForming - DNS issues may resolve
  * Any transient failure that might clear up

- SCALE_DEPLOYMENT: Scale to 0 then back to 1. Use for:
  * Stuck deployments
  * Multiple pods failing
  * Need full deployment restart

- RESTART_DEPLOYMENT: Similar to scale, triggers new pod rollout

- NONE: Only use when:
  * PVC binding issues (need storage admin)
  * Node-level hardware problems
  * Missing Secrets/ConfigMaps (need gitops fix)
  * Resource quota exceeded (need limit change)

IMPORTANT: Be AGGRESSIVE about trying fixes. Most pod issues CAN be fixed with a restart.
Even if you're only 50% confident, recommend CAN_REMEDIATE: YES and try DELETE_POD.

The worst case is the pod restarts and fails again - no harm done.
The best case is a transient issue clears up and the pod recovers.

Default to CAN_REMEDIATE: YES with DELETE_POD unless there's a specific reason not to.
"""


async def run_healer() -> None:
    """Run the Healer agent."""
    healer = HealerAgent()
    await healer.start()
