"""
Healer Agent - Agentic remediation with MCP tools.

The Healer is a thin wrapper that:
1. Subscribes to K8S_ISSUE_DETECTED events
2. Creates an agent with kubernetes-mcp-server tools
3. Lets the agent investigate and remediate autonomously
4. Posts updates to Discord at each stage

The agent has full access to MCP tools and decides what to do.
No complex orchestration - just give the agent the problem and let it work.

Discord updates are posted:
- When issue is detected (before investigation)
- During investigation (findings via discord_update tool)
- Before taking action (planned action via discord_update tool)
- After action (result via discord_update tool)
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from strands import tool
from strands.types.tools import AgentTool, ToolGenerator, ToolSpec, ToolUse

from core_agents.events import Event, EventBus, EventType, get_event_bus

if TYPE_CHECKING:
    from strands.tools.mcp import MCPAgentTool
from core_agents.factory import AgentConfig, ModelConfig, get_agent_factory
from core_agents.integrations.discord_mcp import send_discord_message

logger = logging.getLogger(__name__)

# =============================================================================
# Healer-side filters (defense in depth)
# =============================================================================
# These filters provide a second line of defense in case:
# 1. Old events exist in the Redis Stream from before Sentinel filters were deployed
# 2. Events slip through Sentinel filters due to timing or structure issues
# These MUST be kept in sync with the Sentinel's BENIGN_WARNING_PATTERNS

# Benign warning patterns to skip entirely (no investigation or Discord post)
# Keep in sync with Sentinel's BENIGN_WARNING_PATTERNS
HEALER_SKIP_REASONS = {
    "DNSConfigForming",  # DNS warnings with Tailscale are expected
    "Killing",  # Pod termination during rollout
    "Preempting",  # Normal scheduler preemption
    "ProbeWarning",  # Transient probe failures during rollouts
    "ReconciliationSucceeded",  # Flux success events
    "Progressing",  # Normal Flux progress
}

# Resource name patterns to skip (regex patterns)
HEALER_SKIP_RESOURCE_PATTERNS = [
    r"^k8s-monitor-",  # Don't investigate ourselves (prevents loops)
    r"-start-schedule-",  # Scheduled job pods
    r"-start-scheduler-",  # Init container jobs
]


def _should_skip_event(reason: str, resource_name: str) -> tuple[bool, str]:
    """
    Check if an event should be skipped by the Healer.

    Returns:
        Tuple of (should_skip, skip_reason)
    """
    # Check benign warning patterns
    if reason in HEALER_SKIP_REASONS:
        return True, f"benign warning pattern: {reason}"

    # Check resource name patterns
    for pattern in HEALER_SKIP_RESOURCE_PATTERNS:
        if re.search(pattern, resource_name):
            return True, f"ignored resource pattern: {pattern}"

    return False, ""


# Tool result size limits to prevent context overflow
# These can be overridden via environment variables
MAX_LOG_LINES = int(os.getenv("HEALER_MAX_LOG_LINES", "50"))
MAX_EVENTS = int(os.getenv("HEALER_MAX_EVENTS", "20"))
MAX_RESULT_CHARS = int(os.getenv("HEALER_MAX_RESULT_CHARS", "8000"))


def truncate_tool_result(result: str, max_chars: int = MAX_RESULT_CHARS) -> str:
    """Truncate a tool result to prevent context overflow."""
    if len(result) <= max_chars:
        return result

    # Keep first and last portions for context
    keep_start = int(max_chars * 0.7)
    keep_end = int(max_chars * 0.2)
    truncated_msg = f"\n\n... [TRUNCATED {len(result) - max_chars} chars] ...\n\n"

    return result[:keep_start] + truncated_msg + result[-keep_end:]


class LimitedMCPAgentTool(AgentTool):
    """
    Wrapper that limits result size for MCP tools to prevent context overflow.

    This properly implements the AgentTool interface so Strands can register it.

    For pods_log: limits tail to MAX_LOG_LINES
    For events_list: truncates result to MAX_EVENTS items
    All tools: truncates final result to MAX_RESULT_CHARS
    """

    def __init__(self, original_tool: "MCPAgentTool", name: str):
        """
        Initialize the limited tool wrapper.

        Args:
            original_tool: The MCPAgentTool to wrap
            name: The tool name (used for applying specific limits)
        """
        super().__init__()
        self._original = original_tool
        self._name = name

    @property
    def tool_name(self) -> str:
        """Get the name of the tool."""
        return self._name

    @property
    def tool_spec(self) -> ToolSpec:
        """Get the specification of the tool."""
        return self._original.tool_spec

    @property
    def tool_type(self) -> str:
        """Get the type of the tool."""
        return self._original.tool_type

    async def stream(
        self, tool_use: ToolUse, invocation_state: dict[str, Any], **kwargs: Any
    ) -> ToolGenerator:
        """
        Stream the tool execution, applying limits to input and truncating output.

        Args:
            tool_use: The tool use request containing tool ID and parameters
            invocation_state: Context for the tool invocation
            **kwargs: Additional keyword arguments

        Yields:
            Tool events with the last being the tool result
        """
        # Apply input limits for specific tools
        tool_input = tool_use.get("input", {})

        if self._name == "pods_log":
            # Limit log lines unless explicitly set to a smaller value
            current_tail = tool_input.get("tail", 100)
            if current_tail > MAX_LOG_LINES:
                tool_input["tail"] = MAX_LOG_LINES
                logger.debug(f"Limited pods_log tail to {MAX_LOG_LINES}")

        # Delegate to original tool
        async for event in self._original.stream(tool_use, invocation_state, **kwargs):
            # Check if this is a result event with content to truncate
            if hasattr(event, "result") and event.result:
                result = event.result
                content = result.get("content", [])

                # Truncate text content if too large
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text = item["text"]
                        if isinstance(text, str) and len(text) > MAX_RESULT_CHARS:
                            logger.info(
                                f"Truncating {self._name} result from {len(text)} "
                                f"to {MAX_RESULT_CHARS} chars"
                            )
                            item["text"] = truncate_tool_result(text, MAX_RESULT_CHARS)

            yield event


@dataclass
class IssueContext:
    """Context for an issue to investigate."""

    event_id: str
    pod_name: str
    namespace: str
    kind: str
    reason: str
    message: str
    severity: str
    event_type: str  # "Warning" or "Error" - from K8s event type
    # Track which stages have been posted to prevent spam
    posted_stages: set = field(default_factory=set)


# Global context for the current issue being investigated
# This allows the discord_update tool to include resource context
_current_context: IssueContext | None = None


@tool
def discord_update(
    stage: str,
    message: str,
) -> str:
    """Post an update to Discord about the current investigation.

    Use this tool to keep stakeholders informed during investigation and remediation.
    Call this tool ONCE per stage - duplicate posts are automatically skipped.

    Args:
        stage: One of: "findings", "planned_action", "action_result", "retry"
            - findings: Key observations from your investigation
            - planned_action: What you're about to do and why
            - action_result: Outcome of your action (success or failure)
            - retry: If retrying, explain what you'll try differently
        message: Clear, concise message describing the update

    Returns:
        Confirmation that the message was posted (or skipped if duplicate)
    """
    ctx = _current_context
    if ctx is None:
        return "Error: No active investigation context"

    # Prevent duplicate posts for the same stage (except action_result which may vary)
    if stage != "action_result" and stage in ctx.posted_stages:
        logger.debug(f"Skipping duplicate {stage} post for {ctx.reason}")
        return f"Skipped duplicate {stage} update (already posted)"

    # Determine emoji based on stage and message content
    if stage == "action_result":
        # Check for success/failure indicators in the message
        msg_lower = message.lower()
        if "success" in msg_lower or "resolved" in msg_lower or "fixed" in msg_lower:
            emoji = "\u2705"  # green check
        else:
            emoji = "\u26a0\ufe0f"  # warning
    else:
        emoji_map = {
            "findings": "\U0001f50d",  # magnifying glass
            "planned_action": "\U0001f6e0\ufe0f",  # wrench
            "retry": "\U0001f504",  # arrows circle
        }
        emoji = emoji_map.get(stage, "\U0001f4ac")

    stage_labels = {
        "findings": "Investigation Findings",
        "planned_action": "Planned Action",
        "action_result": "Action Result",
        "retry": "Retrying",
    }
    label = stage_labels.get(stage, stage.title())

    content = f"""{emoji} **{label}**: {ctx.reason}

**Resource:** {ctx.kind}/{ctx.pod_name}
**Namespace:** {ctx.namespace}

{message}
"""

    try:
        # Use MCP-based Discord integration
        from core_agents.integrations.discord_mcp import send_discord_message_sync

        result = send_discord_message_sync(
            content=content,
            agent_name="k8s-monitor",
        )
        if result:
            ctx.posted_stages.add(stage)
            logger.info(f"Posted {stage} update to Discord: {ctx.reason}")
            return f"Posted {stage} update to Discord"
        else:
            logger.warning("Failed to post Discord update: No message ID returned")
            return "Warning: Failed to post to Discord"
    except Exception as e:
        logger.warning(f"Failed to post Discord update: {type(e).__name__}: {e}")
        return f"Warning: Failed to post to Discord: {e}"


class HealerAgent:
    """
    Agentic healer that uses MCP tools to investigate and fix issues.

    Supports two modes:
    1. Direct remediation: LLM agent handles investigation and remediation
    2. Orchestrated remediation: Temporal workflow handles 8-stage pipeline

    The orchestration mode is used for correlated issues from the Sentinel,
    providing more structured investigation with memory queries and learning.
    """

    def __init__(
        self,
        source_name: str = "k8s-healer",
        enable_orchestration: bool = True,
    ):
        self.source_name = source_name
        self._event_bus: EventBus | None = None
        self._running = False
        self._enable_orchestration = enable_orchestration
        self._temporal_client = None

    def _create_mcp_client(self):
        """Create MCP client for kubernetes-mcp-server (synchronous context manager)."""
        from mcp.client.streamable_http import streamablehttp_client
        from strands.tools.mcp import MCPClient

        mcp_url = os.getenv(
            "KUBERNETES_MCP_SERVER_URL",
            os.getenv("MCP_SERVER_URL", "https://kubernetes-mcp.almckay.io"),
        )
        if not mcp_url.endswith("/mcp"):
            mcp_url = f"{mcp_url}/mcp"

        logger.debug(f"Connecting to MCP server at {mcp_url}")
        return MCPClient(lambda: streamablehttp_client(mcp_url))

    async def start(self) -> None:
        """Start processing issue events."""
        if self._event_bus is None:
            self._event_bus = await get_event_bus()

        # Initialize Temporal client for orchestration mode
        if self._enable_orchestration:
            await self._init_temporal_client()

        self._running = True
        logger.info(
            f"Healer starting (orchestration={'enabled' if self._enable_orchestration else 'disabled'})"
        )

        # Start both handlers concurrently
        handlers = [self._handle_direct_issues()]
        if self._enable_orchestration:
            handlers.append(self._handle_orchestration_requests())

        try:
            await asyncio.gather(*handlers)
        except asyncio.CancelledError:
            logger.info("Healer cancelled")
        finally:
            self._running = False

    async def _init_temporal_client(self) -> None:
        """Initialize Temporal client for orchestration workflows."""
        try:
            from temporalio.client import Client

            temporal_host = os.getenv("TEMPORAL_HOST", "temporal.almckay.io:7233")
            self._temporal_client = await Client.connect(temporal_host)
            logger.info(f"Connected to Temporal at {temporal_host}")
        except Exception as e:
            logger.warning(f"Failed to connect to Temporal: {e}")
            logger.warning("Orchestration mode disabled - falling back to direct remediation")
            self._enable_orchestration = False

    async def _handle_direct_issues(self) -> None:
        """Handle direct issue events (K8S_ISSUE_DETECTED)."""
        logger.info("Subscribing to K8S_ISSUE_DETECTED events")

        try:
            async for event in self._event_bus.subscribe(
                EventType.K8S_ISSUE_DETECTED,
                consumer_group="k8s-healer",
                consumer_name=self.source_name,
            ):
                if not self._running:
                    break

                try:
                    await self._handle_issue(event)
                except Exception as e:
                    logger.error(f"Error handling issue: {e}")

        except asyncio.CancelledError:
            raise

    async def _handle_orchestration_requests(self) -> None:
        """Handle correlated investigation requests (K8S_INVESTIGATION_REQUESTED)."""
        logger.info("Subscribing to K8S_INVESTIGATION_REQUESTED events")

        try:
            async for event in self._event_bus.subscribe(
                EventType.K8S_INVESTIGATION_REQUESTED,
                consumer_group="k8s-healer-orchestration",
                consumer_name=f"{self.source_name}-orchestration",
            ):
                if not self._running:
                    break

                try:
                    await self._start_orchestration_workflow(event)
                except Exception as e:
                    logger.error(f"Error starting orchestration: {e}")

        except asyncio.CancelledError:
            raise

    async def _start_orchestration_workflow(self, event: Event) -> None:
        """Start the RemediationOrchestrationWorkflow for a correlated issue."""
        if not self._temporal_client:
            logger.warning("Temporal client not available - skipping orchestration")
            return

        payload = event.payload
        correlation_id = payload.get("correlation_id", event.id)
        issue_data = payload.get("issue", {})

        workflow_id = f"remediation-{correlation_id}"

        logger.info(f"Starting orchestration workflow: {workflow_id}")

        try:
            from k8s_monitor.orchestration_workflow import RemediationOrchestrationWorkflow

            handle = await self._temporal_client.start_workflow(
                RemediationOrchestrationWorkflow.run,
                issue_data,
                id=workflow_id,
                task_queue="k8s-monitor",
            )

            logger.info(f"Started workflow {workflow_id}, run_id={handle.result_run_id}")

        except Exception as e:
            logger.error(f"Failed to start orchestration workflow: {e}")

    def stop(self) -> None:
        """Stop processing events."""
        self._running = False

    async def _handle_issue(self, event: Event) -> None:
        """Handle an issue by letting an agent investigate and remediate."""
        global _current_context

        payload = event.payload
        k8s_event = payload.get("event", {})

        context = IssueContext(
            event_id=event.id,
            pod_name=k8s_event.get("name", "unknown"),
            namespace=k8s_event.get("namespace", "default"),
            kind=k8s_event.get("kind", "Pod"),
            reason=k8s_event.get("reason", "Unknown"),
            message=k8s_event.get("message", ""),
            severity=payload.get("classification", {}).get("severity", "medium"),
            event_type=k8s_event.get("type", "Warning"),
        )

        # Defense in depth: Skip benign events that shouldn't trigger investigation
        # This catches old events from before Sentinel filters or any filter bypasses
        should_skip, skip_reason = _should_skip_event(context.reason, context.pod_name)
        if should_skip:
            logger.info(
                f"Skipping event (Healer filter): {context.reason} on "
                f"{context.kind}/{context.pod_name} - {skip_reason}"
            )
            return

        # Set global context for discord_update tool
        _current_context = context

        logger.info(f"Handling: {context.reason} on {context.kind}/{context.pod_name}")

        # Post initial detection notification
        await self._post_detection(context)

        # Let the agent handle everything (it will post updates via discord_update tool)
        start_time = datetime.now(UTC)
        try:
            success, result_summary = await self._run_agent(context)
        finally:
            _current_context = None

        duration = (datetime.now(UTC) - start_time).total_seconds()

        # Post final summary
        await self._post_final_summary(context, success, result_summary, duration)

        # Emit completion event
        event_type = (
            EventType.K8S_REMEDIATION_COMPLETED if success else EventType.K8S_REMEDIATION_FAILED
        )
        await self._event_bus.publish(
            event_type=event_type,
            payload={
                "issue_id": context.event_id,
                "resource": f"{context.kind}/{context.pod_name}",
                "namespace": context.namespace,
                "success": success,
                "summary": result_summary,
                "duration_seconds": duration,
            },
            source=self.source_name,
        )

    async def _post_detection(self, context: IssueContext) -> None:
        """Post initial issue detection notification to Discord."""
        severity_emoji = {
            "critical": "\U0001f534",  # red circle
            "high": "\U0001f7e0",  # orange circle
            "medium": "\U0001f7e1",  # yellow circle
            "low": "\U0001f7e2",  # green circle
        }
        emoji = severity_emoji.get(context.severity.lower(), "\U0001f7e1")

        # Distinguish Warning events from Issues/Errors
        header = "Warning Detected" if context.event_type == "Warning" else "Issue Detected"

        message = f"""{emoji} **{header}**: {context.reason}

**Resource:** {context.kind}/{context.pod_name}
**Namespace:** {context.namespace}
**Severity:** {context.severity.upper()}
**Message:** {context.message}

\U0001f916 *Starting autonomous investigation...*
"""
        try:
            result = await send_discord_message(content=message, agent_name="k8s-monitor")
            if result:
                logger.info(f"Posted {header.lower()} to Discord: {context.reason}")
            else:
                logger.warning("Failed to post detection to Discord: No message ID returned")
        except Exception as e:
            logger.warning(f"Failed to post detection to Discord: {type(e).__name__}: {e}")

    async def _run_agent(self, context: IssueContext) -> tuple[bool, str]:
        """Run the agentic investigator. Returns (success, summary)."""
        try:
            # MCPClient is a synchronous context manager
            with self._create_mcp_client() as mcp_client:
                mcp_tools = mcp_client.list_tools_sync()
                logger.info(f"MCP connected with {len(mcp_tools)} tools")

                # Wrap MCP tools with result size limits to prevent context overflow
                limited_tools = []
                for tool_obj in mcp_tools:
                    tool_name = getattr(tool_obj, "tool_name", getattr(tool_obj, "name", "unknown"))
                    # Only wrap tools that can return large results
                    if tool_name in ("pods_log", "events_list", "pods_list", "resources_list"):
                        limited_tools.append(LimitedMCPAgentTool(tool_obj, tool_name))
                    else:
                        limited_tools.append(tool_obj)

                # Combine MCP tools with our discord_update tool
                all_tools = limited_tools + [discord_update]

                factory = get_agent_factory()
                agent = factory.create_agent(
                    AgentConfig(
                        name="k8s_healer",
                        description="Investigates and fixes Kubernetes issues",
                        system_prompt=HEALER_PROMPT,
                        tools=all_tools,
                        # Limit output tokens to prevent context overflow
                        model_config=ModelConfig(max_tokens=2048),
                    )
                )

                # Brief, focused prompt to reduce context size
                prompt = f"""Issue: {context.reason} on {context.kind}/{context.pod_name} (ns: {context.namespace})
Message: {context.message}
Severity: {context.severity}

Investigate briefly, take action if possible, then conclude with one of:
- REMEDIATION_SUCCESS: <summary>
- REMEDIATION_FAILED: <why>
- CONFIG_CHANGE_NEEDED: <what>"""

                # Run agent with max_turns limit to prevent runaway tool calls
                # Reduced from 12 to 8 to enforce brief investigations
                result = agent(prompt, max_turns=8)

                result_str = str(result)
                logger.debug(f"Agent result: {result_str[:500]}...")

                # Parse result
                if "REMEDIATION_SUCCESS" in result_str.upper():
                    summary = self._extract_field(result_str, "REMEDIATION_SUCCESS")
                    return True, summary
                elif "CONFIG_CHANGE_NEEDED" in result_str.upper():
                    summary = self._extract_field(result_str, "CONFIG_CHANGE_NEEDED")
                    return False, f"Config change needed: {summary}"
                else:
                    summary = self._extract_field(result_str, "REMEDIATION_FAILED")
                    return False, summary

        except Exception as e:
            logger.error(f"Agent failed: {e}")
            return False, str(e)

    def _extract_field(self, text: str, field: str) -> str:
        """Extract field value from agent response."""
        pattern = rf"{field}:\s*(.+?)(?:\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "Unknown"

    async def _post_final_summary(
        self,
        context: IssueContext,
        success: bool,
        summary: str,
        duration: float,
    ) -> None:
        """Post final summary to Discord."""
        status = "Resolved" if success else "Needs Attention"
        emoji = "\U0001f389" if success else "\U0001f6a8"  # party popper or rotating light

        message = f"""{emoji} **Investigation Complete - {status}**

**Resource:** {context.kind}/{context.pod_name}
**Namespace:** {context.namespace}
**Duration:** {duration:.1f}s

**Final Status:** {summary}
"""
        try:
            result = await send_discord_message(content=message, agent_name="k8s-monitor")
            if result:
                logger.info(f"Posted final summary to Discord: {status}")
            else:
                logger.warning("Failed to post final summary to Discord: No message ID returned")
        except Exception as e:
            logger.warning(f"Failed to post final summary to Discord: {type(e).__name__}: {e}")


# Compact healer prompt - keep short to save context tokens
HEALER_PROMPT = """You are a Kubernetes healer. Use MCP tools to investigate and fix issues.

## Discord Updates (use discord_update tool)
- findings: Share DETAILED observations after investigating. Include:
  * What you checked (pod status, logs, events)
  * Key error messages or symptoms found
  * Root cause analysis (if determined)
  * Related resources affected (if any)
- planned_action: Announce what you'll do and WHY (ONLY ONCE per issue)
- action_result: Report outcome with details (use "success" or "resolved" for successes, "failed" for failures)

## MCP Tools Available
pods_get, pods_log, pods_delete, pods_exec, pods_list, events_list, resources_get, resources_list, resources_scale

## CRITICAL: Avoid Investigation Loops
- If an action fails twice with the same error, STOP and report CONFIG_CHANGE_NEEDED
- Do NOT create test pods - you don't have permission. Use pods_exec on existing pods instead.
- Do NOT try different namespaces/service accounts - if permission denied, report it.
- Maximum 3 tool calls for investigation, then conclude.

## Cluster Context
- Nodes: rig0 (primary), asio, workstation (use these exact names for node operations)
- DNS: CoreDNS runs in kube-system namespace with label k8s-app=kube-dns
- Registry: registry.registry.svc.cluster.local:5000

## DNS Diagnostics (if needed)
Use pods_exec on an existing pod (like coredns in kube-system) instead of creating test pods:
- pods_exec with command ["nslookup", "example.com"] on any running pod

## Quick Strategy
1. First, check if the resource still exists (pods_get). If not found, it was likely replaced during rollout.
2. If exists, check logs briefly (pods_log with tail=30)
3. Post findings ONCE
4. Take action OR report config change needed
5. Post result and conclude

## Benign Warnings (just acknowledge - no deep investigation needed)
- DNSConfigForming/Nameserver limits: Normal with Tailscale. REMEDIATION_SUCCESS: Expected behavior.
- FailedBinding for missing PVC: Check if PVC exists, report if not.
- BackOff on init containers that completed: Transient. REMEDIATION_SUCCESS: Init completed.
- BackOff on job pods (*-start-schedule-*, *-start-scheduler-*): Expected. REMEDIATION_SUCCESS: Job behavior.
- Resource not found during investigation: Was replaced/deleted. REMEDIATION_SUCCESS: Resource no longer exists.

## Actions
- CrashLoopBackOff, probe failures: Delete pod to trigger restart (pods_delete)
- ImagePullBackOff: Check image name, report CONFIG_CHANGE_NEEDED if image is wrong
- DNS issues: Check CoreDNS pod health in kube-system, report findings

## Output (required - exactly ONE at the end)
- REMEDIATION_SUCCESS: <summary>
- REMEDIATION_FAILED: <why>
- CONFIG_CHANGE_NEEDED: <what needs to change>"""


async def run_healer(enable_orchestration: bool = True) -> None:
    """Run the Healer agent.

    Args:
        enable_orchestration: If True, also handle K8S_INVESTIGATION_REQUESTED
            events and start orchestration workflows for correlated issues.
    """
    healer = HealerAgent(enable_orchestration=enable_orchestration)
    await healer.start()
