"""
Temporal activities for issue remediation.

These activities handle investigation, fix attempts, and Discord notifications
for the remediation workflow.

Uses multi-agent swarm for investigation and remediation with enhanced
Discord formatting from core utilities.
"""

import logging
import os
from datetime import UTC, datetime
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
from k8s_monitor.swarm import (
    attempt_fix as swarm_attempt_fix,
)
from k8s_monitor.swarm import (
    investigate_issue as swarm_investigate,
)
from k8s_monitor.swarm import (
    verify_fix as swarm_verify_fix,
)

logger = logging.getLogger(__name__)


@activity.defn
async def investigate_issue_activity(issue_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Investigate an issue to determine root cause and propose a fix.

    Uses the multi-agent swarm's PodDiagnosticianAgent for deep analysis.
    Also checks memory for similar past issues.

    Args:
        issue_dict: Dictionary representation of the Issue

    Returns:
        Dictionary representation of the Investigation
    """
    logger.info(f"Starting investigation for issue: {issue_dict.get('id')}")

    issue = Issue(**issue_dict)

    # Use swarm investigation
    result = swarm_investigate(
        issue_title=issue.title,
        resource_type=issue.resource_type,
        resource_name=issue.resource_name,
        namespace=issue.namespace,
        description=issue.description,
    )

    # Convert to Investigation model format
    investigation = Investigation(
        issue_id=issue.id,
        findings=result.get("findings", ""),
        root_cause=result.get("root_cause", "Unknown"),
        proposed_fix=result.get("proposed_fix", ""),
        fix_command=result.get("fix_command", ""),
        confidence=result.get("confidence", 0.5),
        investigated_at=datetime.now(UTC).isoformat(),
    )

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

    Uses the multi-agent swarm's ClusterRemediatorAgent for safe fixes.

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

    # Use swarm fix attempt
    result = swarm_attempt_fix(
        issue_title=issue.title,
        resource_type=issue.resource_type,
        resource_name=issue.resource_name,
        namespace=issue.namespace,
        proposed_fix=investigation.proposed_fix,
        attempt_number=attempt_number,
    )

    # Convert to FixAttempt model format
    fix_attempt = FixAttempt(
        attempt_number=attempt_number,
        action_taken=result.get("action_taken", "Unknown"),
        command_executed=result.get("command_executed", ""),
        result=result.get("result", ""),
        success=result.get("success", False),
        error_message=result.get("error_message"),
        attempted_at=datetime.now(UTC).isoformat(),
    )

    logger.info(f"Fix attempt {attempt_number} {'succeeded' if fix_attempt.success else 'failed'}")
    return fix_attempt.model_dump()


@activity.defn
async def store_remediation_memory_activity(
    record_dict: dict[str, Any],
    permanent_fix: str | None = None,
) -> dict[str, Any]:
    """
    Store a completed remediation record in memory for future learning.

    Args:
        record_dict: Dictionary representation of the RemediationRecord
        permanent_fix: Optional description of a permanent fix if one was applied

    Returns:
        Dictionary with success status and memory_id if successful
    """
    logger.info("Storing remediation record in memory")

    try:
        from k8s_monitor.memory import store_remediation_memory

        record = RemediationRecord(**record_dict)
        memory_id = store_remediation_memory(record, permanent_fix)

        if memory_id:
            logger.info(f"Successfully stored remediation memory: {memory_id}")
            return {"success": True, "memory_id": memory_id}
        else:
            logger.warning("Failed to store remediation memory (no ID returned)")
            return {"success": False, "error": "No memory ID returned"}

    except Exception as e:
        logger.error(f"Error storing remediation memory: {e}")
        return {"success": False, "error": str(e)}


@activity.defn
async def verify_issue_resolved(issue_dict: dict[str, Any]) -> bool:
    """
    Verify if an issue has been resolved.

    Uses tools to check resource health directly.

    Args:
        issue_dict: Dictionary representation of the Issue

    Returns:
        True if the issue appears to be resolved
    """
    logger.info(f"Verifying resolution for issue: {issue_dict.get('id')}")

    issue = Issue(**issue_dict)
    is_healthy = swarm_verify_fix(issue.resource_type, issue.resource_name, issue.namespace)

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
    Post a remediation-related message to Discord using enhanced formatting.

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

    try:
        # Import formatting utilities from core
        from core_agents.discord_utils import (
            format_escalation,
            format_fix_attempt,
            format_fix_failure,
            format_fix_success,
            format_investigation_results,
            format_issue_detection,
            send_discord_message,
        )

        msg_type = DiscordMessageType(message_type)
        issue = Issue(**issue_dict)
        timestamp = datetime.now(UTC).isoformat()

        # Build embed based on message type using core utilities
        if msg_type == DiscordMessageType.ISSUE_DETECTED:
            embed = format_issue_detection(
                issue_title=issue.title,
                resource_type=issue.resource_type,
                resource_name=issue.resource_name,
                namespace=issue.namespace,
                severity=issue.severity.value,
                description=issue.description,
                timestamp=timestamp,
            )

        elif msg_type == DiscordMessageType.INVESTIGATION_COMPLETE:
            investigation = Investigation(**investigation_dict) if investigation_dict else None
            if investigation:
                # Extract evidence from findings (simple split by lines)
                evidence = [
                    line.strip("- ")
                    for line in investigation.findings.split("\n")
                    if line.strip().startswith("-")
                ][:3]

                # Get memory context (if available)
                similar_count = 0
                last_occurrence = None
                try:
                    from k8s_monitor.memory import search_similar_issues

                    similar_issues = search_similar_issues(issue)
                    similar_count = len(similar_issues)
                    if similar_issues:
                        last_occurrence = similar_issues[0].get("last_occurrence")
                except Exception as e:
                    logger.warning(f"Could not fetch memory context: {e}")

                embed = format_investigation_results(
                    issue_title=issue.title,
                    root_cause=investigation.root_cause,
                    evidence=evidence if evidence else None,
                    similar_issues_count=similar_count,
                    last_occurrence=last_occurrence,
                    proposed_fix=investigation.proposed_fix,
                    confidence=investigation.confidence,
                    timestamp=timestamp,
                )
            else:
                # Fallback if no investigation data
                embed = format_issue_detection(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    severity=issue.severity.value,
                    timestamp=timestamp,
                )

        elif msg_type == DiscordMessageType.FIX_ATTEMPTED:
            fix_attempt = FixAttempt(**fix_attempt_dict) if fix_attempt_dict else None
            if fix_attempt:
                embed = format_fix_attempt(
                    issue_title=issue.title,
                    attempt_number=fix_attempt.attempt_number,
                    max_attempts=3,
                    action=fix_attempt.action_taken,
                    command=fix_attempt.command_executed,
                    timestamp=timestamp,
                )
            else:
                embed = format_issue_detection(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    severity=issue.severity.value,
                    timestamp=timestamp,
                )

        elif msg_type == DiscordMessageType.FIX_SUCCESS:
            fix_attempt = FixAttempt(**fix_attempt_dict) if fix_attempt_dict else None
            if fix_attempt:
                # Get recurrence count from memory
                recurrence_count = 0
                recommendations = []
                try:
                    from k8s_monitor.memory import get_recurrence_count

                    recurrence_count = get_recurrence_count(issue)
                    if recurrence_count >= 3:
                        recommendations = [
                            "Investigate root cause for permanent fix",
                            "Consider updating base deployment manifest",
                        ]
                except Exception as e:
                    logger.warning(f"Could not fetch recurrence count: {e}")

                embed = format_fix_success(
                    issue_title=issue.title,
                    fix_applied=fix_attempt.action_taken,
                    result=fix_attempt.result,
                    recurrence_count=recurrence_count,
                    recommendations=recommendations if recommendations else None,
                    timestamp=timestamp,
                )
            else:
                embed = format_issue_detection(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    severity=issue.severity.value,
                    timestamp=timestamp,
                )

        elif msg_type == DiscordMessageType.FIX_FAILED:
            fix_attempt = FixAttempt(**fix_attempt_dict) if fix_attempt_dict else None
            record = RemediationRecord(**record_dict) if record_dict else None
            if fix_attempt and record:
                next_action = None
                if record.current_attempt < 3:
                    next_action = "Re-investigating with new context..."

                embed = format_fix_failure(
                    issue_title=issue.title,
                    attempt_number=fix_attempt.attempt_number,
                    max_attempts=3,
                    result=fix_attempt.result or fix_attempt.error_message or "Fix failed",
                    next_action=next_action,
                    timestamp=timestamp,
                )
            else:
                embed = format_issue_detection(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    severity=issue.severity.value,
                    timestamp=timestamp,
                )

        elif msg_type == DiscordMessageType.ESCALATION:
            record = RemediationRecord(**record_dict) if record_dict else None
            if record:
                # Build attempts summary
                attempts_summary = []
                for attempt in record.fix_attempts:
                    summary = f"{attempt.action_taken} → {attempt.result or attempt.error_message or 'Failed'}"
                    attempts_summary.append(summary)

                # Get root cause from last investigation
                root_cause = None
                if record.investigations:
                    root_cause = record.investigations[-1].root_cause

                # Action required
                action_required = [
                    "Check application logs",
                    "Verify recent configuration changes",
                    "Consider rollback to known good state",
                ]

                embed = format_escalation(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    attempts=len(record.fix_attempts),
                    attempts_summary=attempts_summary,
                    root_cause=root_cause,
                    action_required=action_required,
                    timestamp=timestamp,
                )
            else:
                embed = format_issue_detection(
                    issue_title=issue.title,
                    resource_type=issue.resource_type,
                    resource_name=issue.resource_name,
                    namespace=issue.namespace,
                    severity=issue.severity.value,
                    timestamp=timestamp,
                )

        else:
            # Fallback for unknown message types
            embed = format_issue_detection(
                issue_title=issue.title,
                resource_type=issue.resource_type,
                resource_name=issue.resource_name,
                namespace=issue.namespace,
                severity=issue.severity.value,
                timestamp=timestamp,
            )

        # Send to Discord using core utility
        await send_discord_message(
            embeds=[embed],
            webhook_url=webhook_url,
            username="Kubani K8s Monitor",
        )

        logger.info(f"Posted {message_type} message to Discord")
        return {"success": True}

    except Exception as e:
        error_msg = f"Error posting to Discord: {e}"
        logger.exception(error_msg)
        return {"success": False, "error": error_msg}
