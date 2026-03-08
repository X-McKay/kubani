"""
K8s Coordinator Tools.

Custom tools for the coordinator agent to dispatch work to specialist agents
and publish results. These are provided via get_additional_tools().
"""

import logging
import os

logger = logging.getLogger(__name__)


async def dispatch_diagnostics(issue_summary: str) -> str:
    """Dispatch an issue to the diagnostics agent for investigation.

    Use this when you find an issue that needs deep investigation but should NOT
    be auto-remediated. The diagnostics agent will gather logs, events, and
    resource status to identify the root cause.

    Args:
        issue_summary: Description of the issue including resource kind/name,
            namespace, reason, and any relevant context from events or logs.

    Returns:
        Investigation findings with root cause analysis and recommendations.
    """
    from kubani.agents.k8s_diagnostics import K8sDiagnosticsAgent

    try:
        agent = K8sDiagnosticsAgent()
        result = await agent.run(issue_summary)
        logger.info(f"Diagnostics completed: {result[:200]}")
        return result
    except Exception as e:
        logger.error(f"Diagnostics agent failed: {e}")
        return f"Diagnostics failed: {e}"


async def dispatch_remediation(issue_summary: str) -> str:
    """Dispatch a safe issue to the remediator agent for auto-remediation.

    Only use this for issues classified as safe to auto-remediate:
    CrashLoopBackOff, ImagePullBackOff, Unhealthy, BackOff.

    The remediator will investigate briefly, take corrective action if possible,
    and report the outcome.

    Args:
        issue_summary: Description of the issue including resource kind/name,
            namespace, reason, and message.

    Returns:
        Remediation result: REMEDIATION_SUCCESS, REMEDIATION_FAILED, or CONFIG_CHANGE_NEEDED
        followed by a summary.
    """
    from kubani.agents.remediator.agent import RemediatorAgent

    try:
        agent = RemediatorAgent()
        # RemediatorAgent.run() handles the full investigation + remediation cycle
        result = await agent.run(issue_summary)
        logger.info(f"Remediation completed: {result[:200]}")
        return result
    except Exception as e:
        logger.error(f"Remediator agent failed: {e}")
        return f"Remediation failed: {e}"


async def publish_results(
    summary: str,
    severity: str = "info",
) -> str:
    """Publish monitoring results to the UI activity feed and Discord.

    Call this after completing all dispatches to share the final report.

    Args:
        summary: Formatted markdown summary of findings and actions taken.
            Include: what was checked, what was found, what was auto-remediated,
            and what recommendations remain.
        severity: One of "info" (routine/healthy), "warning" (non-critical issues),
            "error" (critical issues found).

    Returns:
        Confirmation of publication.
    """
    published_to = []

    # 1. Publish to UI activity feed
    try:
        from kubani.framework.ui_events import publish_activity

        redis_url = os.environ.get("REDIS_URL")
        await publish_activity(
            source="k8s-monitor",
            event_type="agent_activity" if severity == "info" else "alert",
            title="K8s Health Check",
            content=summary,
            severity=severity,
            metadata={"trigger": "scheduled"},
            redis_url=redis_url,
        )
        published_to.append("UI feed")
    except Exception as e:
        logger.warning(f"Failed to publish to UI feed: {e}")

    # 2. Publish to Discord webhook
    try:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if webhook_url:
            import httpx

            # Discord has a 2000-char limit per message
            chunks = _split_message(summary, max_length=1900)
            async with httpx.AsyncClient(timeout=30) as client:
                for chunk in chunks:
                    resp = await client.post(
                        webhook_url,
                        json={"content": chunk},
                        params={"wait": "true"},
                    )
                    resp.raise_for_status()
            published_to.append("Discord")
        else:
            logger.debug("No DISCORD_WEBHOOK_URL set, skipping Discord")
    except Exception as e:
        logger.warning(f"Failed to publish to Discord: {e}")

    if published_to:
        return f"Published to: {', '.join(published_to)}"
    return "Warning: Failed to publish to any channel"


def _split_message(text: str, max_length: int = 1900) -> list[str]:
    """Split a message into chunks that fit Discord's limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks
