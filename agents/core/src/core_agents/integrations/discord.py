"""
Low-level Discord webhook utilities.

Provides simple helpers for posting messages to Discord channels
via webhooks. For agent-based Discord interaction, use DiscordAgent instead.
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class DiscordEmbed:
    """Discord embed structure for rich messages."""

    title: str
    description: str
    color: int = 0x5865F2  # Discord blurple
    fields: list[dict[str, Any]] | None = None
    footer: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to Discord API format."""
        embed: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "color": self.color,
        }
        if self.fields:
            embed["fields"] = self.fields
        if self.footer:
            embed["footer"] = {"text": self.footer}
        if self.timestamp:
            embed["timestamp"] = self.timestamp
        return embed


class Colors:
    """Color constants for different message types."""

    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245  # Red
    INFO = 0x5865F2  # Blurple
    NEUTRAL = 0x99AAB5  # Gray


async def send_discord_message(
    content: str | None = None,
    embeds: list[DiscordEmbed] | None = None,
    webhook_url: str | None = None,
    username: str = "Kubani Agent",
    avatar_url: str | None = None,
) -> bool:
    """
    Send a message to Discord via webhook (async).

    Args:
        content: Plain text message content.
        embeds: List of DiscordEmbed objects for rich messages.
        webhook_url: Discord webhook URL. Defaults to DISCORD_WEBHOOK_URL env var.
        username: Bot username to display.
        avatar_url: Bot avatar URL.

    Returns:
        True if message was sent successfully.

    Raises:
        ValueError: If no webhook URL is provided.
        httpx.HTTPError: If the request fails.

    Example:
        >>> await send_discord_message(
        ...     embeds=[DiscordEmbed(
        ...         title="Cluster Health",
        ...         description="All systems operational",
        ...         color=Colors.SUCCESS,
        ...     )]
        ... )
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("Discord webhook URL must be provided or set via DISCORD_WEBHOOK_URL")

    payload: dict[str, Any] = {
        "username": username,
    }

    if content:
        payload["content"] = content

    if embeds:
        payload["embeds"] = [e.to_dict() for e in embeds]

    if avatar_url:
        payload["avatar_url"] = avatar_url

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

    return True


def send_discord_message_sync(
    content: str | None = None,
    embeds: list[DiscordEmbed] | None = None,
    webhook_url: str | None = None,
    username: str = "Kubani Agent",
    avatar_url: str | None = None,
) -> bool:
    """
    Send a message to Discord via webhook (synchronous).

    Args:
        content: Plain text message content.
        embeds: List of DiscordEmbed objects for rich messages.
        webhook_url: Discord webhook URL. Defaults to DISCORD_WEBHOOK_URL env var.
        username: Bot username to display.
        avatar_url: Bot avatar URL.

    Returns:
        True if message was sent successfully.
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("Discord webhook URL must be provided or set via DISCORD_WEBHOOK_URL")

    payload: dict[str, Any] = {
        "username": username,
    }

    if content:
        payload["content"] = content

    if embeds:
        payload["embeds"] = [e.to_dict() for e in embeds]

    if avatar_url:
        payload["avatar_url"] = avatar_url

    with httpx.Client() as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    return True


# Convenience alias
post_discord_message = send_discord_message_sync


# =============================================================================
# Rich Formatting Utilities for K8s Monitoring
# =============================================================================
# These utilities provide reusable formatting functions for common monitoring
# scenarios. They are generic enough to be used across different agent workflows.


class StatusEmoji:
    """Emoji constants for status indicators."""

    HEALTHY = "✅"
    WARNING = "⚠️"
    CRITICAL = "🚨"
    ERROR = "❌"
    INFO = "ℹ️"
    INVESTIGATING = "🔍"
    FIXING = "🔧"
    SUCCESS = "✨"
    FAILED = "💥"
    ESCALATION = "🚨"


def format_health_confirmation(
    summary: str,
    timestamp: str,
    additional_info: dict[str, Any] | None = None,
) -> DiscordEmbed:
    """
    Format a brief health confirmation message for healthy status.

    Args:
        summary: Brief summary of health status
        timestamp: ISO timestamp of the check
        additional_info: Optional additional information to include

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_health_confirmation(
        ...     summary="All nodes, pods, and deployments are healthy.",
        ...     timestamp="2024-01-15T10:00:00Z",
        ...     additional_info={"nodes": 3, "pods": 42}
        ... )
    """
    description_parts = [summary]

    if additional_info:
        description_parts.append("")
        for key, value in additional_info.items():
            description_parts.append(f"**{key.title()}:** {value}")

    return DiscordEmbed(
        title=f"{StatusEmoji.HEALTHY} Cluster Health Check - All Systems Operational",
        description="\n".join(description_parts),
        color=Colors.SUCCESS,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_issue_detection(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    severity: str,
    description: str | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format an issue detection notification.

    Args:
        issue_title: Short title of the issue
        resource_type: Type of K8s resource (Pod, Deployment, etc.)
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        severity: Severity level (healthy, warning, critical, error)
        description: Optional detailed description
        timestamp: ISO timestamp of detection

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_issue_detection(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     resource_type="Pod",
        ...     resource_name="app-backend",
        ...     namespace="production",
        ...     severity="critical",
        ...     description="Container is crashing repeatedly"
        ... )
    """
    # Map severity to emoji and color
    severity_lower = severity.lower()
    if severity_lower == "critical":
        emoji = StatusEmoji.CRITICAL
        color = Colors.ERROR
    elif severity_lower == "warning":
        emoji = StatusEmoji.WARNING
        color = Colors.WARNING
    else:
        emoji = StatusEmoji.ERROR
        color = Colors.NEUTRAL

    description_parts = [
        f"**Resource:** {resource_type}/{resource_name}",
        f"**Namespace:** {namespace}",
        f"**Severity:** {severity.title()}",
    ]

    if description:
        description_parts.extend(["", description])

    description_parts.extend(["", "_Starting automated investigation..._"])

    return DiscordEmbed(
        title=f"{emoji} Issue Detected: {issue_title}",
        description="\n".join(description_parts),
        color=color,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_investigation_results(
    issue_title: str,
    root_cause: str,
    evidence: list[str] | None = None,
    similar_issues_count: int = 0,
    last_occurrence: str | None = None,
    proposed_fix: str | None = None,
    confidence: float | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format investigation results notification.

    Args:
        issue_title: Title of the issue investigated
        root_cause: Identified root cause
        evidence: List of key evidence items
        similar_issues_count: Number of similar past issues
        last_occurrence: When the issue last occurred
        proposed_fix: Proposed remediation action
        confidence: Confidence level (0.0-1.0)
        timestamp: ISO timestamp

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_investigation_results(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     root_cause="OOMKilled - container exceeded memory limit",
        ...     evidence=["Last exit code: 137 (OOM)", "Memory limit: 512Mi"],
        ...     similar_issues_count=2,
        ...     proposed_fix="Increase memory limit to 1Gi",
        ...     confidence=0.9
        ... )
    """
    description_parts = [
        f"**Root Cause:** {root_cause}",
    ]

    if evidence:
        description_parts.extend(["", "**Evidence:**"])
        for item in evidence[:3]:  # Limit to top 3 items
            description_parts.append(f"- {item}")

    if similar_issues_count > 0:
        description_parts.append("")
        occurrence_text = f"Found {similar_issues_count} past occurrence(s)"
        if last_occurrence:
            occurrence_text += f" (last: {last_occurrence})"
        description_parts.append(f"**Similar Issues:** {occurrence_text}")

    if proposed_fix:
        description_parts.extend(["", f"**Planned Remediation:** {proposed_fix}"])

    if confidence is not None:
        confidence_pct = int(confidence * 100)
        description_parts.append(f"**Confidence:** {confidence_pct}%")

    return DiscordEmbed(
        title=f"{StatusEmoji.INVESTIGATING} Investigation Complete: {issue_title}",
        description="\n".join(description_parts),
        color=Colors.INFO,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_fix_attempt(
    issue_title: str,
    attempt_number: int,
    max_attempts: int,
    action: str,
    command: str | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format a fix attempt notification.

    Args:
        issue_title: Title of the issue being fixed
        attempt_number: Current attempt number (1-based)
        max_attempts: Maximum number of attempts
        action: Description of the action being taken
        command: Optional command being executed
        timestamp: ISO timestamp

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_fix_attempt(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     attempt_number=1,
        ...     max_attempts=3,
        ...     action="Updating deployment memory limit",
        ...     command="kubectl patch deployment app-backend ..."
        ... )
    """
    description_parts = [
        f"**Action:** {action}",
    ]

    if command:
        # Truncate long commands
        display_command = command if len(command) <= 200 else command[:197] + "..."
        description_parts.extend(["", "**Command:**", f"```bash\n{display_command}\n```"])

    description_parts.extend(["", "_Executing..._"])

    return DiscordEmbed(
        title=f"{StatusEmoji.FIXING} Applying Fix (Attempt {attempt_number}/{max_attempts})",
        description="\n".join(description_parts),
        color=Colors.INFO,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_fix_success(
    issue_title: str,
    fix_applied: str,
    result: str,
    recurrence_count: int = 0,
    recommendations: list[str] | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format a successful fix notification.

    Args:
        issue_title: Title of the issue that was fixed
        fix_applied: Description of the fix that was applied
        result: Result of the fix
        recurrence_count: Number of times this issue has occurred
        recommendations: Optional recommendations for permanent fixes
        timestamp: ISO timestamp

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_fix_success(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     fix_applied="Increased memory limit to 1Gi",
        ...     result="Pod now running successfully",
        ...     recurrence_count=3,
        ...     recommendations=["Investigate memory leak in application"]
        ... )
    """
    description_parts = [
        f"**Fix Applied:** {fix_applied}",
        f"**Result:** {result}",
    ]

    if recurrence_count >= 3:
        description_parts.extend(
            [
                "",
                f"⚠️ **Note:** This issue has occurred {recurrence_count} times. Consider:",
            ]
        )
        if recommendations:
            for rec in recommendations:
                description_parts.append(f"- {rec}")
        else:
            description_parts.append("- Investigating root cause for permanent fix")

    description_parts.extend(["", "_Learning stored for future reference._"])

    return DiscordEmbed(
        title=f"{StatusEmoji.SUCCESS} Issue Resolved: {issue_title}",
        description="\n".join(description_parts),
        color=Colors.SUCCESS,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_fix_failure(
    issue_title: str,
    attempt_number: int,
    max_attempts: int,
    result: str,
    next_action: str | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format a failed fix attempt notification.

    Args:
        issue_title: Title of the issue
        attempt_number: Current attempt number that failed
        max_attempts: Maximum number of attempts
        result: Result/reason for failure
        next_action: What will be tried next
        timestamp: ISO timestamp

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_fix_failure(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     attempt_number=1,
        ...     max_attempts=3,
        ...     result="Deployment updated but pod still crashing",
        ...     next_action="Re-investigating with new context..."
        ... )
    """
    description_parts = [
        f"**Result:** {result}",
    ]

    if next_action:
        description_parts.extend(["", next_action])

    if attempt_number < max_attempts:
        description_parts.append(f"_Attempt {attempt_number + 1}/{max_attempts} starting..._")

    return DiscordEmbed(
        title=f"{StatusEmoji.FAILED} Fix Attempt {attempt_number} Failed",
        description="\n".join(description_parts),
        color=Colors.WARNING,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )


def format_escalation(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    attempts: int,
    attempts_summary: list[str],
    root_cause: str | None = None,
    action_required: list[str] | None = None,
    timestamp: str | None = None,
) -> DiscordEmbed:
    """
    Format an escalation notification for manual intervention.

    Args:
        issue_title: Title of the issue
        resource_type: Type of K8s resource
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        attempts: Number of failed attempts
        attempts_summary: Summary of what was tried
        root_cause: Identified root cause (if known)
        action_required: List of actions needed from human
        timestamp: ISO timestamp

    Returns:
        DiscordEmbed ready to send

    Example:
        >>> embed = format_escalation(
        ...     issue_title="Pod CrashLoopBackOff",
        ...     resource_type="Pod",
        ...     resource_name="app-backend",
        ...     namespace="production",
        ...     attempts=3,
        ...     attempts_summary=["Increased memory limit → Pod still crashing"],
        ...     root_cause="Likely configuration issue in new deployment",
        ...     action_required=["Check application logs", "Verify configuration"]
        ... )
    """
    description_parts = [
        f"**Issue:** {issue_title} ({resource_type}/{resource_name})",
        f"**Namespace:** {namespace}",
        f"**Attempts:** {attempts}/{attempts} failed",
    ]

    if attempts_summary:
        description_parts.extend(["", "**What was tried:**"])
        for i, attempt in enumerate(attempts_summary, 1):
            description_parts.append(f"{i}. {attempt}")

    if root_cause:
        description_parts.extend(["", f"**Root Cause:** {root_cause}"])

    if action_required:
        description_parts.extend(["", "**Action Required:** Manual investigation needed"])
        for action in action_required:
            description_parts.append(f"- {action}")

    return DiscordEmbed(
        title=f"{StatusEmoji.ESCALATION} URGENT: Automated Remediation Failed",
        description="\n".join(description_parts),
        color=Colors.ERROR,
        footer="Kubani K8s Monitor",
        timestamp=timestamp,
    )
