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

from strands import tool

from core_agents.events import Event, EventBus, EventType, get_event_bus
from core_agents.factory import AgentConfig, ModelConfig, get_agent_factory
from core_agents.integrations.discord import send_discord_message

logger = logging.getLogger(__name__)


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

    emoji_map = {
        "findings": "\U0001f50d",  # magnifying glass
        "planned_action": "\U0001f6e0\ufe0f",  # wrench
        "action_result": "\u2705" if "success" in message.lower() else "\u26a0\ufe0f",
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
        # Use synchronous version since we're called from a sync tool context
        from core_agents.integrations.discord import send_discord_message_sync

        send_discord_message_sync(content=content, username="Kubani Healer")
        ctx.posted_stages.add(stage)
        logger.info(f"Posted {stage} update to Discord: {ctx.reason}")
        return f"Posted {stage} update to Discord"
    except Exception as e:
        logger.warning(f"Failed to post Discord update: {type(e).__name__}: {e}")
        return f"Warning: Failed to post to Discord: {e}"


class HealerAgent:
    """
    Agentic healer that uses MCP tools to investigate and fix issues.

    This is intentionally minimal - the LLM agent does the thinking,
    not Python code orchestrating every step.
    """

    def __init__(self, source_name: str = "k8s-healer"):
        self.source_name = source_name
        self._event_bus: EventBus | None = None
        self._running = False

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
                    await self._handle_issue(event)
                except Exception as e:
                    logger.error(f"Error handling issue: {e}")

        except asyncio.CancelledError:
            logger.info("Healer cancelled")
        finally:
            self._running = False

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
            await send_discord_message(content=message, username="Kubani Healer")
            logger.info(f"Posted {header.lower()} to Discord: {context.reason}")
        except Exception as e:
            logger.warning(f"Failed to post detection to Discord: {type(e).__name__}: {e}")

    async def _run_agent(self, context: IssueContext) -> tuple[bool, str]:
        """Run the agentic investigator. Returns (success, summary)."""
        try:
            # MCPClient is a synchronous context manager
            with self._create_mcp_client() as mcp_client:
                mcp_tools = mcp_client.list_tools_sync()
                logger.info(f"MCP connected with {len(mcp_tools)} tools")

                # Combine MCP tools with our discord_update tool
                all_tools = list(mcp_tools) + [discord_update]

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
                result = agent(prompt, max_turns=12)

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
            await send_discord_message(content=message, username="Kubani Healer")
            logger.info(f"Posted final summary to Discord: {status}")
        except Exception as e:
            logger.warning(f"Failed to post final summary to Discord: {type(e).__name__}: {e}")


# Compact healer prompt - keep short to save context tokens
HEALER_PROMPT = """You are a Kubernetes healer. Use MCP tools to investigate and fix issues.

## Discord Updates (use discord_update tool)
- findings: Share observations after investigating
- planned_action: Announce what you'll do (ONLY ONCE per issue)
- action_result: Report outcome

## MCP Tools: pods_get, pods_log, pods_delete, events_list, resources_get, resources_scale

## Quick Strategy
1. Investigate briefly (pods_get, pods_log)
2. Post findings ONCE
3. Post planned_action ONCE
4. Take action or report config change needed
5. Post result

## Benign Warnings (just acknowledge)
- DNSConfigForming/Nameserver limits: Normal with Tailscale. No action.
- FailedBinding for missing PVC: Stale event. No action.
- BackOff on init containers that completed: Transient. No action.

## Actions
- CrashLoopBackOff, probe failures: Delete pod to restart
- Config issues: Report what needs changing (don't try to fix)

## Output (required - exactly ONE)
- REMEDIATION_SUCCESS: <summary>
- REMEDIATION_FAILED: <why>
- CONFIG_CHANGE_NEEDED: <what>"""


async def run_healer() -> None:
    """Run the Healer agent."""
    healer = HealerAgent()
    await healer.start()
