"""
Temporal activities for issue remediation.

These activities handle investigation, fix attempts, and Discord notifications
for the remediation workflow.
"""

import logging
import os
from typing import Any

import httpx
from temporalio import activity

from k8s_monitor.models import (
    DiscordMessageType,
    FixAttempt,
    Investigation,
    Issue,
    RemediationRecord,
)
from k8s_monitor.remediation_agent import attempt_fix, investigate_issue

logger = logging.getLogger(__name__)


# Discord embed colors for different message types
MESSAGE_COLORS: dict[DiscordMessageType, int] = {
    DiscordMessageType.ISSUE_DETECTED: 0xED4245,  # Red
    DiscordMessageType.INVESTIGATION_COMPLETE: 0x5865F2,  # Blurple
    DiscordMessageType.FIX_ATTEMPTED: 0xFEE75C,  # Yellow
    DiscordMessageType.FIX_SUCCESS: 0x57F287,  # Green
    DiscordMessageType.FIX_FAILED: 0xED4245,  # Red
    DiscordMessageType.ESCALATION: 0xFF0000,  # Bright red
    DiscordMessageType.HEALTH_REPORT: 0x5865F2,  # Blurple
}

# Emojis for message types
MESSAGE_EMOJI: dict[DiscordMessageType, str] = {
    DiscordMessageType.ISSUE_DETECTED: "🚨",
    DiscordMessageType.INVESTIGATION_COMPLETE: "🔍",
    DiscordMessageType.FIX_ATTEMPTED: "🔧",
    DiscordMessageType.FIX_SUCCESS: "✅",
    DiscordMessageType.FIX_FAILED: "❌",
    DiscordMessageType.ESCALATION: "🆘",
    DiscordMessageType.HEALTH_REPORT: "📊",
}


@activity.defn
async def investigate_issue_activity(issue_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Investigate an issue to determine root cause and propose a fix.

    Args:
        issue_dict: Dictionary representation of the Issue

    Returns:
        Dictionary representation of the Investigation
    """
    logger.info(f"Starting investigation for issue: {issue_dict.get('id')}")

    issue = Issue(**issue_dict)
    investigation = investigate_issue(issue)

    logger.info(f"Investigation complete. Root cause: {investigation.root_cause}")
    return investigation.model_dump()


@activity.defn
async def attempt_fix_activity(
    issue_dict: dict[str, Any],
    investigation_dict: dict[str, Any],
    attempt_number: int,
) -> dict[str, Any]:
    """
    Attempt to fix an issue based on investigation results.

    Args:
        issue_dict: Dictionary representation of the Issue
        investigation_dict: Dictionary representation of the Investigation
        attempt_number: Which attempt this is (1-3)

    Returns:
        Dictionary representation of the FixAttempt
    """
    logger.info(f"Attempting fix #{attempt_number} for issue: {issue_dict.get('id')}")

    issue = Issue(**issue_dict)
    investigation = Investigation(**investigation_dict)
    fix_attempt = attempt_fix(issue, investigation, attempt_number)

    logger.info(f"Fix attempt {attempt_number} {'succeeded' if fix_attempt.success else 'failed'}")
    return fix_attempt.model_dump()


@activity.defn
async def verify_issue_resolved(issue_dict: dict[str, Any]) -> bool:
    """
    Verify if an issue has been resolved.

    Args:
        issue_dict: Dictionary representation of the Issue

    Returns:
        True if the issue appears to be resolved
    """
    logger.info(f"Verifying resolution for issue: {issue_dict.get('id')}")

    # Use the verify_fix tool from remediation_agent
    from k8s_monitor.remediation_agent import verify_fix

    issue = Issue(**issue_dict)
    result = verify_fix(issue.resource_type, issue.resource_name, issue.namespace)

    # Check if the resource looks healthy
    result_lower = result.lower()
    is_healthy = (
        "running" in result_lower
        or "ready" in result_lower
        or "available" in result_lower
    ) and not (
        "pending" in result_lower
        or "error" in result_lower
        or "failed" in result_lower
        or "crashloop" in result_lower
    )

    logger.info(f"Issue resolved: {is_healthy}")
    return is_healthy


@activity.defn
async def post_remediation_discord(
    message_type: str,
    issue_dict: dict[str, Any],
    investigation_dict: dict[str, Any] | None,
    fix_attempt_dict: dict[str, Any] | None,
    record_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Post a remediation-related message to Discord.

    Args:
        message_type: Type of message (from DiscordMessageType)
        issue_dict: The issue being remediated
        investigation_dict: Investigation results (if available)
        fix_attempt_dict: Fix attempt results (if available)
        record_dict: Full remediation record (if available)

    Returns:
        Result of the Discord post
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL not configured")
        return {"success": False, "error": "DISCORD_WEBHOOK_URL not set"}

    msg_type = DiscordMessageType(message_type)
    issue = Issue(**issue_dict)

    # Build embed based on message type
    embed = _build_embed(msg_type, issue, investigation_dict, fix_attempt_dict, record_dict)

    payload = {
        "username": "Kubani K8s Remediation",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        logger.info(f"Posted {message_type} message to Discord")
        return {"success": True}

    except httpx.HTTPStatusError as e:
        error_msg = f"Discord API error: {e.response.status_code}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Error posting to Discord: {e}"
        logger.exception(error_msg)
        return {"success": False, "error": error_msg}


def _build_embed(
    msg_type: DiscordMessageType,
    issue: Issue,
    investigation_dict: dict[str, Any] | None,
    fix_attempt_dict: dict[str, Any] | None,
    record_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build Discord embed based on message type."""
    emoji = MESSAGE_EMOJI.get(msg_type, "📋")
    color = MESSAGE_COLORS.get(msg_type, 0x5865F2)

    if msg_type == DiscordMessageType.ISSUE_DETECTED:
        return _build_issue_detected_embed(emoji, color, issue)

    elif msg_type == DiscordMessageType.INVESTIGATION_COMPLETE:
        return _build_investigation_embed(emoji, color, issue, investigation_dict)

    elif msg_type == DiscordMessageType.FIX_SUCCESS:
        return _build_fix_success_embed(emoji, color, issue, fix_attempt_dict)

    elif msg_type == DiscordMessageType.FIX_FAILED:
        return _build_fix_failed_embed(emoji, color, issue, fix_attempt_dict, record_dict)

    elif msg_type == DiscordMessageType.ESCALATION:
        return _build_escalation_embed(emoji, color, issue, record_dict)

    else:
        return _build_generic_embed(emoji, color, issue)


def _build_issue_detected_embed(emoji: str, color: int, issue: Issue) -> dict[str, Any]:
    """Build embed for issue detection."""
    return {
        "title": f"{emoji} Issue Detected",
        "description": f"**{issue.title}**\n\n{issue.description}",
        "color": color,
        "fields": [
            {
                "name": "Resource",
                "value": f"`{issue.resource_type}/{issue.resource_name}`",
                "inline": True,
            },
            {
                "name": "Namespace",
                "value": f"`{issue.namespace}`",
                "inline": True,
            },
            {
                "name": "Severity",
                "value": issue.severity.value.upper(),
                "inline": True,
            },
            {
                "name": "Status",
                "value": "🔄 Auto-remediation starting...",
                "inline": False,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id}"},
    }


def _build_investigation_embed(
    emoji: str, color: int, issue: Issue, investigation_dict: dict[str, Any] | None
) -> dict[str, Any]:
    """Build embed for investigation results."""
    if not investigation_dict:
        investigation_dict = {}

    findings = investigation_dict.get("findings", "No findings")
    root_cause = investigation_dict.get("root_cause", "Unknown")
    proposed_fix = investigation_dict.get("proposed_fix", "No fix proposed")
    confidence = investigation_dict.get("confidence", 0)

    # Truncate long fields
    if len(findings) > 500:
        findings = findings[:497] + "..."
    if len(root_cause) > 200:
        root_cause = root_cause[:197] + "..."

    return {
        "title": f"{emoji} Investigation Complete",
        "description": f"**Issue:** {issue.title}",
        "color": color,
        "fields": [
            {
                "name": "Root Cause",
                "value": root_cause,
                "inline": False,
            },
            {
                "name": "Findings",
                "value": f"```\n{findings[:800]}\n```" if findings else "None",
                "inline": False,
            },
            {
                "name": "Proposed Fix",
                "value": proposed_fix,
                "inline": False,
            },
            {
                "name": "Confidence",
                "value": f"{confidence:.0%}",
                "inline": True,
            },
            {
                "name": "Status",
                "value": "🔧 Attempting fix...",
                "inline": True,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id}"},
    }


def _build_fix_success_embed(
    emoji: str, color: int, issue: Issue, fix_attempt_dict: dict[str, Any] | None
) -> dict[str, Any]:
    """Build embed for successful fix."""
    if not fix_attempt_dict:
        fix_attempt_dict = {}

    action = fix_attempt_dict.get("action_taken", "Unknown action")
    result = fix_attempt_dict.get("result", "No result")
    attempt_num = fix_attempt_dict.get("attempt_number", 1)

    return {
        "title": f"{emoji} Issue Resolved",
        "description": f"**{issue.title}** has been automatically remediated.",
        "color": color,
        "fields": [
            {
                "name": "Resource",
                "value": f"`{issue.resource_type}/{issue.resource_name}`",
                "inline": True,
            },
            {
                "name": "Attempt",
                "value": f"#{attempt_num}",
                "inline": True,
            },
            {
                "name": "Action Taken",
                "value": action[:500] if action else "Unknown",
                "inline": False,
            },
            {
                "name": "Result",
                "value": result[:500] if result else "Success",
                "inline": False,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id} • Auto-remediated"},
    }


def _build_fix_failed_embed(
    emoji: str,
    color: int,
    issue: Issue,
    fix_attempt_dict: dict[str, Any] | None,
    record_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build embed for failed fix attempt."""
    if not fix_attempt_dict:
        fix_attempt_dict = {}
    if not record_dict:
        record_dict = {}

    action = fix_attempt_dict.get("action_taken", "Unknown action")
    error = fix_attempt_dict.get("error_message", "Unknown error")
    attempt_num = fix_attempt_dict.get("attempt_number", 1)
    remaining = 3 - attempt_num

    return {
        "title": f"{emoji} Fix Attempt Failed",
        "description": f"Attempt #{attempt_num} to fix **{issue.title}** was unsuccessful.",
        "color": color,
        "fields": [
            {
                "name": "Resource",
                "value": f"`{issue.resource_type}/{issue.resource_name}`",
                "inline": True,
            },
            {
                "name": "Attempts Remaining",
                "value": f"{remaining}" if remaining > 0 else "None - escalating",
                "inline": True,
            },
            {
                "name": "Action Attempted",
                "value": action[:300] if action else "Unknown",
                "inline": False,
            },
            {
                "name": "Error",
                "value": f"```\n{error[:400]}\n```" if error else "Unknown error",
                "inline": False,
            },
            {
                "name": "Status",
                "value": "🔄 Retrying..." if remaining > 0 else "🆘 Escalating to human",
                "inline": False,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id}"},
    }


def _build_escalation_embed(
    emoji: str, color: int, issue: Issue, record_dict: dict[str, Any] | None
) -> dict[str, Any]:
    """Build embed for escalation to human."""
    if not record_dict:
        record_dict = {}

    fix_attempts = record_dict.get("fix_attempts", [])

    # Build attempt summary
    attempts_summary = []
    for i, attempt in enumerate(fix_attempts, 1):
        action = attempt.get("action_taken", "Unknown")[:100]
        error = attempt.get("error_message", "Unknown")[:100]
        attempts_summary.append(f"**Attempt {i}:** {action}\n→ Error: {error}")

    attempts_text = "\n\n".join(attempts_summary) if attempts_summary else "No attempts recorded"

    return {
        "title": f"{emoji} HUMAN INTERVENTION REQUIRED",
        "description": (
            f"Automated remediation failed after 3 attempts.\n\n"
            f"**Issue:** {issue.title}\n"
            f"**Description:** {issue.description[:300]}"
        ),
        "color": color,
        "fields": [
            {
                "name": "Resource",
                "value": f"`{issue.resource_type}/{issue.resource_name}`",
                "inline": True,
            },
            {
                "name": "Namespace",
                "value": f"`{issue.namespace}`",
                "inline": True,
            },
            {
                "name": "Severity",
                "value": f"⚠️ {issue.severity.value.upper()}",
                "inline": True,
            },
            {
                "name": "Attempted Fixes",
                "value": attempts_text[:1000],
                "inline": False,
            },
            {
                "name": "Recommended Actions",
                "value": (
                    "1. Review the resource logs and events\n"
                    "2. Check cluster resources and node health\n"
                    "3. Review recent changes or deployments\n"
                    f"4. `kubectl describe {issue.resource_type} {issue.resource_name} -n {issue.namespace}`"
                ),
                "inline": False,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id} • Manual intervention required"},
    }


def _build_generic_embed(emoji: str, color: int, issue: Issue) -> dict[str, Any]:
    """Build a generic embed."""
    return {
        "title": f"{emoji} Remediation Update",
        "description": f"**{issue.title}**",
        "color": color,
        "fields": [
            {
                "name": "Resource",
                "value": f"`{issue.resource_type}/{issue.resource_name}`",
                "inline": True,
            },
            {
                "name": "Namespace",
                "value": f"`{issue.namespace}`",
                "inline": True,
            },
        ],
        "footer": {"text": f"Issue ID: {issue.id}"},
    }
