"""
Temporal activities for the Kubernetes monitoring agent.

Activities are the units of work that execute the actual business logic.
They are retried automatically on failure and can be long-running.

Uses multi-agent swarm for cluster analysis and remediation.
"""

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from temporalio import activity

from k8s_monitor.models import (
    ClusterHealthReport,
    DiscordPostResult,
    HealthStatus,
    Issue,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Status parsing helpers (also used by tests and remediation)
# =============================================================================

# Keywords for fallback status detection (only used if Status line not found)
CRITICAL_KEYWORDS = frozenset(["critical", "failed", "error", "down", "crashloopbackoff"])
WARNING_KEYWORDS = frozenset(["warning", "pending", "degraded", "notready", "unhealthy"])

# Regex to extract the Status line from LLM output
STATUS_PATTERN = re.compile(r"\*\*Status:\*\*\s*(Healthy|Warning|Critical)", re.IGNORECASE)


def _determine_status(summary: str) -> HealthStatus:
    """
    Determine health status from the summary.

    First tries to extract the explicit **Status:** line from the LLM output.
    Falls back to keyword matching only if the status line is not found.
    """
    # First, try to extract the explicit status line from LLM output
    match = STATUS_PATTERN.search(summary)
    if match:
        status_text = match.group(1).lower()
        if status_text == "critical":
            return HealthStatus.CRITICAL
        elif status_text == "warning":
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    # Fallback: keyword matching (only if LLM didn't include Status line)
    logger.warning("No explicit Status line found in summary, falling back to keyword matching")
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
    Collect cluster metrics and analyze them using the Strands AI agent.

    Uses native Strands SDK patterns with:
    - @tool decorated functions for K8s and memory operations
    - Optional MCP client for kubernetes-mcp-server
    - Hooks for safety, observability, and notifications

    Returns:
        ClusterHealthReport with the analysis results.
    """
    logger.info("Starting swarm cluster analysis")

    try:
        from k8s_monitor.swarm import run_health_check

        result = await run_health_check()

        # Map status string to HealthStatus enum
        status_map = {
            "healthy": HealthStatus.HEALTHY,
            "warning": HealthStatus.WARNING,
            "critical": HealthStatus.CRITICAL,
        }
        status = status_map.get(result.get("status", "healthy"), HealthStatus.HEALTHY)

        # Build summary from result
        summary_parts = [
            f"**Status:** {status.value.title()}",
            "",
            f"**Summary:** {result.get('summary', 'Health check completed')}",
            "",
        ]

        issues = []
        if result.get("issues"):
            summary_parts.append("**Issues:**")
            for i, issue_text in enumerate(result["issues"]):
                summary_parts.append(f"- {issue_text}")
                # Create Issue objects
                issue_id = hashlib.sha256(f"strands-{i}-{issue_text}".encode()).hexdigest()[:12]
                issues.append(
                    Issue(
                        id=issue_id,
                        title=issue_text[:100],
                        description=issue_text,
                        severity=status,
                        resource_type="Unknown",
                        resource_name="unknown",
                        namespace="default",
                        detected_at=datetime.now(UTC).isoformat(),
                    )
                )
            summary_parts.append("")

        if result.get("recommendations"):
            summary_parts.append("**Recommendations:**")
            for rec in result["recommendations"]:
                summary_parts.append(f"- {rec}")

        summary = "\n".join(summary_parts)

        logger.info(
            "Swarm analysis complete",
            extra={
                "status": status.value,
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
async def post_health_confirmation(report: ClusterHealthReport) -> DiscordPostResult:
    """
    Post a brief health confirmation to Discord for healthy status.

    Args:
        report: The ClusterHealthReport (should be HEALTHY status).

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

    logger.info("Posting brief health confirmation to Discord")

    # Brief confirmation message for healthy status
    embed: dict = {
        "title": "✅ Cluster Health Check - All Systems Operational",
        "description": "All nodes, pods, and deployments are healthy.",
        "color": STATUS_COLORS[HealthStatus.HEALTHY],
        "footer": {"text": f"Kubani K8s Monitor • {report.timestamp}"},
        "timestamp": report.timestamp,
    }

    payload = {
        "username": "Kubani K8s Monitor",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        logger.info("Successfully posted health confirmation to Discord")
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
