"""
Temporal activities for the Kubernetes monitoring agent.

Activities are the units of work that execute the actual business logic.
They are retried automatically on failure and can be long-running.
"""

import logging
import os
from datetime import UTC, datetime
from enum import Enum

import httpx
from pydantic import BaseModel, Field
from temporalio import activity

from k8s_monitor.agent import analyze_cluster

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Cluster health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"


class ClusterHealthReport(BaseModel):
    """Result of cluster health analysis."""

    summary: str = Field(description="Human-readable health summary")
    status: HealthStatus = Field(description="Overall cluster health status")
    timestamp: str = Field(description="ISO format timestamp of the analysis")
    error: str | None = Field(default=None, description="Error message if analysis failed")

    model_config = {"frozen": True}


class DiscordPostResult(BaseModel):
    """Result of posting to Discord."""

    success: bool = Field(description="Whether the post was successful")
    message_id: str | None = Field(default=None, description="Discord message ID if successful")
    error: str | None = Field(default=None, description="Error message if failed")


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


@activity.defn
async def collect_and_analyze_cluster() -> ClusterHealthReport:
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

        logger.info(
            "Analysis complete", extra={"status": status.value, "summary_length": len(summary)}
        )

        return ClusterHealthReport(
            summary=summary,
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
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
