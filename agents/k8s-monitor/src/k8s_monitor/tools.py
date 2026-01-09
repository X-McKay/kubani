"""
Tools for k8s-monitor Strands agent.

NOTE: Kubernetes operations are handled via MCP tools from kubernetes-mcp-server.
This file only contains supplementary tools (Discord notifications).
"""

import logging
import os

from strands import tool

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
    from core_agents import DiscordEmbed, send_discord_message_sync

    color_map = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
        "healthy": 0x2ECC71,  # Green
    }

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set, skipping notification")
        return "Discord notification skipped - webhook URL not configured"

    embed = DiscordEmbed(
        title=title,
        description=message,
        color=color_map.get(status, 0x3498DB),
    )

    try:
        send_discord_message_sync(embeds=[embed], webhook_url=webhook_url)
        return f"Successfully sent Discord notification: {title}"
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return f"Failed to send Discord notification: {e}"


# All tools - just the Discord notifier
# K8s operations are via MCP tools, not @tool decorated functions
ALL_TOOLS = [discord_notify]
