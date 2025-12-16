"""
Temporal activities for the Kubernetes monitoring agent.

Activities are the units of work that execute the actual business logic.
They are retried automatically on failure and can be long-running.
"""

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from temporalio import activity

from k8s_monitor.agent import analyze_cluster
from k8s_monitor.models import (
    ClusterHealthReport,
    DiscordPostResult,
    HealthStatus,
    Issue,
)

logger = logging.getLogger(__name__)


# Keywords that indicate different health statuses
CRITICAL_KEYWORDS = frozenset(["critical", "failed", "error", "down", "crashloopbackoff"])
WARNING_KEYWORDS = frozenset(["warning", "pending", "degraded", "notready", "unhealthy"])


def _determine_status(summary: str) -> HealthStatus:
    """Determine health status from summary content."""
    summary_lower = summary.lower()

    if any(word in summary_lower for word in CRITICAL_KEYWORDS):
        return HealthStatus.CRITICAL
    if any(word in summary_lower for word in WARNING_KEYWORDS):
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def _extract_issues_from_summary(summary: str, status: HealthStatus) -> list[Issue]:
    """
    Extract individual issues from the summary text.

    Looks for patterns like:
    - Pod names in backticks followed by status
    - Resources mentioned in **Issues** section
    """
    issues: list[Issue] = []

    if status == HealthStatus.HEALTHY:
        return issues

    # Pattern to match resource issues: `resource-name` (namespace) followed by status
    # Handles various formats:
    # - `resource-name` (namespace) - *status*
    # - `resource-name` (namespace) is **status**
    # - `resource-name` (namespace) has **status**
    # - `resource-name` (namespace) **status** (direct)
    pattern = r"`([a-zA-Z0-9\-_.]+)`\s*\(([a-zA-Z0-9\-_]+)\)\s*(?:[-–—]|is|has)?\s*[`*]*\*?\*?([A-Za-z]+)\*?\*?[`*]*"
    matches = re.findall(pattern, summary)

    for match in matches:
        resource_name, namespace, issue_status = match
        issue_status_lower = issue_status.lower()

        # Skip if not actually an issue
        if issue_status_lower in ("running", "ready", "available", "bound"):
            continue

        # Determine severity
        severity = HealthStatus.WARNING
        if issue_status_lower in ("failed", "crashloopbackoff", "error", "backoff"):
            severity = HealthStatus.CRITICAL

        # Determine resource type from name patterns
        resource_type = "Pod"
        if "deploy" in resource_name.lower():
            resource_type = "Deployment"
        elif "svc" in resource_name.lower() or "service" in resource_name.lower():
            resource_type = "Service"
        elif "pvc" in resource_name.lower():
            resource_type = "PersistentVolumeClaim"

        # Generate unique issue ID
        issue_id = hashlib.sha256(
            f"{resource_type}/{resource_name}/{namespace}/{issue_status}".encode()
        ).hexdigest()[:12]

        issues.append(
            Issue(
                id=issue_id,
                title=f"{resource_type} {resource_name} is {issue_status}",
                description=f"The {resource_type.lower()} '{resource_name}' in namespace '{namespace}' is in '{issue_status}' state.",
                severity=severity,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                detected_at=datetime.now(UTC).isoformat(),
            )
        )

    # If no issues extracted but status is not healthy, create a generic issue
    if not issues and status != HealthStatus.HEALTHY:
        issue_id = hashlib.sha256(
            f"generic/{status.value}/{datetime.now(UTC).isoformat()[:13]}".encode()
        ).hexdigest()[:12]

        issues.append(
            Issue(
                id=issue_id,
                title="Cluster health issue detected",
                description=summary[:500],
                severity=status,
                resource_type="Cluster",
                resource_name="cluster",
                namespace="default",
                detected_at=datetime.now(UTC).isoformat(),
            )
        )

    return issues


@activity.defn
async def collect_and_analyze_cluster() -> dict[str, Any]:
    """
    Collect cluster metrics and analyze them using the AI agent.

    This activity:
    1. Uses the Strands agent to gather Kubernetes data
    2. Analyzes the data and generates a summary
    3. Determines the overall health status

    Returns:
        ClusterHealthReport with the analysis results.
    """
    logger.info("Starting cluster analysis")

    try:
        # Run the analysis (this uses Strands agent with k8s tools)
        summary = analyze_cluster()
        status = _determine_status(summary)
        issues = _extract_issues_from_summary(summary, status)

        logger.info(
            "Analysis complete",
            extra={
                "status": status.value,
                "summary_length": len(summary),
                "issues_count": len(issues),
            },
        )

        return ClusterHealthReport(
            summary=summary,
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            issues=issues,
        )

    except Exception as e:
        logger.exception("Error during cluster analysis")
        return ClusterHealthReport(
            summary="",
            status=HealthStatus.ERROR,
            timestamp=datetime.now(UTC).isoformat(),
            error=str(e),
        )


# Discord embed colors for each status
STATUS_COLORS: dict[HealthStatus, int] = {
    HealthStatus.HEALTHY: 0x57F287,  # Green
    HealthStatus.WARNING: 0xFEE75C,  # Yellow
    HealthStatus.CRITICAL: 0xED4245,  # Red
    HealthStatus.ERROR: 0x99AAB5,  # Gray
}

# Status emoji for each status
STATUS_EMOJI: dict[HealthStatus, str] = {
    HealthStatus.HEALTHY: "✅",
    HealthStatus.WARNING: "⚠️",
    HealthStatus.CRITICAL: "🚨",
    HealthStatus.ERROR: "❌",
}


@activity.defn
async def post_to_discord(report: ClusterHealthReport) -> DiscordPostResult:
    """
    Post the cluster health report to Discord.

    Args:
        report: The ClusterHealthReport to post.

    Returns:
        DiscordPostResult indicating success or failure.
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL not configured")
        return DiscordPostResult(
            success=False,
            error="DISCORD_WEBHOOK_URL environment variable not set",
        )

    logger.info("Posting report to Discord", extra={"status": report.status.value})

    # Build the embed
    emoji = STATUS_EMOJI.get(report.status, "📊")
    color = STATUS_COLORS.get(report.status, 0x5865F2)

    embed: dict = {
        "title": f"{emoji} Kubernetes Cluster Health Report",
        "description": report.summary[:4000] if report.summary else "No data collected",
        "color": color,
        "footer": {"text": f"Kubani K8s Monitor • {report.timestamp}"},
        "timestamp": report.timestamp,
    }

    if report.error:
        embed["fields"] = [
            {
                "name": "Error",
                "value": f"```{report.error[:1000]}```",
                "inline": False,
            }
        ]

    payload = {
        "username": "Kubani K8s Monitor",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        logger.info("Successfully posted to Discord")
        return DiscordPostResult(success=True)

    except httpx.HTTPStatusError as e:
        error_msg = f"Discord API error: {e.response.status_code}"
        logger.error(error_msg, extra={"status_code": e.response.status_code})
        return DiscordPostResult(success=False, error=error_msg)

    except httpx.RequestError as e:
        error_msg = f"Network error posting to Discord: {e}"
        logger.error(error_msg)
        return DiscordPostResult(success=False, error=error_msg)

    except Exception as e:
        error_msg = f"Unexpected error posting to Discord: {e}"
        logger.exception("Unexpected error posting to Discord")
        return DiscordPostResult(success=False, error=error_msg)
