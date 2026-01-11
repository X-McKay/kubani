"""
Tools for k8s-monitor Strands agent.

NOTE: Kubernetes operations are handled via MCP tools from kubernetes-mcp-server.
This file only contains supplementary tools (Discord notifications).
"""

import logging

from strands import tool

from core_agents.integrations.discord_mcp import (
    is_mcp_discord_configured,
    send_discord_message_sync,
)

logger = logging.getLogger(__name__)


@tool
def discord_notify(
    message: str,
    title: str = "K8s Monitor Update",
    status: str = "info",
) -> str:
    """
    Send a notification to the Discord channel.

    Use this to send important updates, alerts, or status reports.

    Args:
        message: The message content to send
        title: Optional title for the notification (default: "K8s Monitor Update")
        status: Status level - info, warning, critical, or healthy

    Returns:
        Confirmation message
    """
    color_map = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
        "healthy": 0x2ECC71,  # Green
    }

    if not is_mcp_discord_configured():
        logger.warning("Discord MCP not configured, skipping notification")
        return "Discord notification skipped - MCP not configured"

    embed = {
        "title": title,
        "description": message,
        "color": color_map.get(status, 0x3498DB),
    }

    try:
        message_id = send_discord_message_sync(
            embed=embed,
            agent_name="k8s-monitor",
        )
        if message_id:
            return f"Successfully sent Discord notification: {title}"
        else:
            return "Failed to send Discord notification: No message ID returned"
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return f"Failed to send Discord notification: {e}"


# All tools - just the Discord notifier
# K8s operations are via MCP tools, not @tool decorated functions
ALL_TOOLS = [discord_notify]
