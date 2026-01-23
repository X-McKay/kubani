"""
Healer Agent Tools - Custom tools for the Healer agent.

These tools are provided in addition to MCP tools.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Global context for the current issue being investigated
_current_context: Any = None


def set_context(context: Any) -> None:
    """Set the current issue context for tools."""
    global _current_context
    _current_context = context


def clear_context() -> None:
    """Clear the current issue context."""
    global _current_context
    _current_context = None


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
        from kubani.framework.mcp import get_mcp_client

        client = get_mcp_client()
        result = client.discord.send_message_sync(
            content=content,
            agent_name="healer",
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
