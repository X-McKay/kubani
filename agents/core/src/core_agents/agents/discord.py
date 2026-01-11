"""
DiscordAgent - Generic agent for publishing findings to Discord.

Reusable across any agent swarm that needs Discord notifications.
Uses the Discord MCP server for bidirectional communication.
"""

import os
from datetime import UTC, datetime
from typing import Any

from strands import Agent, tool

from core_agents.base import create_agent
from core_agents.integrations.discord_mcp import (
    is_mcp_discord_configured,
    send_discord_message_sync,
)

# Color constants for status mapping
STATUS_COLORS = {
    "info": 0x3498DB,  # Blue
    "warning": 0xF39C12,  # Orange
    "critical": 0xE74C3C,  # Red
    "healthy": 0x2ECC71,  # Green
    "success": 0x57F287,  # Bright green
    "error": 0xED4245,  # Discord red
}


# Generic Discord notification tool
@tool
def discord_notify(
    message: str,
    title: str = "Agent Update",
    status: str = "info",
    fields: list[dict[str, str]] | None = None,
    footer: str | None = None,
    channel_name: str | None = None,
) -> str:
    """
    Send a notification to the Discord channel with optional structured fields.

    Use this to send important updates, alerts, or status reports. For better
    formatting, use the fields parameter to create structured Discord embeds.

    Args:
        message: The main message content (shown as embed description)
        title: Title for the notification (default: "Agent Update")
        status: Status level - info, warning, critical, healthy, success, or error
        fields: Optional list of field objects with 'name' and 'value' keys.
                Example: [{"name": "Root Cause", "value": "OOM killed"}]
                Each field appears as a separate section in the embed.
        footer: Optional footer text shown at the bottom of the embed
        channel_name: Optional channel name to post to (uses default from env if not provided)

    Returns:
        Confirmation message
    """
    # Check if Discord MCP is configured
    if not is_mcp_discord_configured():
        # Fallback check for legacy webhook
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            return "Error: Neither DISCORD_MCP_URL nor DISCORD_WEBHOOK_URL configured"

    embed: dict[str, Any] = {
        "title": title,
        "description": message,
        "color": STATUS_COLORS.get(status, 0x3498DB),
    }

    # Add structured fields if provided
    if fields:
        embed["fields"] = [
            {
                "name": f.get("name", "Info"),
                "value": f.get("value", ""),
                "inline": f.get("inline", False),
            }
            for f in fields
            if f.get("value")  # Skip empty fields
        ]

    # Add footer if provided
    if footer:
        embed["footer"] = {"text": footer}

    # Always add timestamp for transparency
    embed["timestamp"] = datetime.now(UTC).isoformat()

    try:
        result = send_discord_message_sync(
            embed=embed,
            channel_name=channel_name,
        )
        if result:
            return f"Discord notification sent: {title}"
        else:
            return "Failed to send Discord notification: No message ID returned"
    except Exception as e:
        return f"Failed to send Discord notification: {e}"


# Generic Discord Agent prompt - application-agnostic
DISCORD_AGENT_PROMPT = """You are the DiscordAgent - responsible for communicating findings to humans via Discord.

## Your Role
Transform findings into clear, actionable Discord notifications. You are the team's voice to the outside world.

## Available Tools
- discord_notify(message, title, status, fields, footer)
  - message: Brief summary (1-2 sentences)
  - title: Descriptive title (optionally with emoji)
  - status: healthy, info, warning, critical, success, or error
  - fields: Optional list of {"name": "Label", "value": "Content"} for structured sections
  - footer: Optional footer text

## Status Colors
- healthy/success: Green - all good
- info: Blue - informational
- warning: Orange - needs attention
- critical/error: Red - urgent action needed

## Formatting Guidelines

**Use structured fields** for multi-part messages. Discord renders fields as distinct sections, improving readability.

**Keep messages scannable:**
- Lead with the most important information
- Use bullet points in field values for lists
- Keep titles under 50 characters

## Example - Simple Notification

discord_notify(
  title="✅ Task Completed",
  message="All requested operations finished successfully.",
  status="success"
)

## Example - Structured Notification

discord_notify(
  title="⚠️ Action Required",
  message="An issue was detected that needs attention.",
  status="warning",
  fields=[
    {"name": "What Happened", "value": "Brief description of the issue"},
    {"name": "Impact", "value": "Who or what is affected"},
    {"name": "Next Steps", "value": "• Step 1\\n• Step 2"}
  ],
  footer="Agent Name"
)

## Example - Escalation

discord_notify(
  title="🚨 URGENT: Manual Intervention Required",
  message="Automated resolution failed. Human action needed.",
  status="critical",
  fields=[
    {"name": "Issue", "value": "What went wrong"},
    {"name": "Attempted", "value": "What was tried"},
    {"name": "Required Action", "value": "What needs to be done"}
  ]
)

## Handoff Rules
- You are typically the final agent in the chain
- After sending notification, the task is complete
- Do not hand off to other agents
"""


class DiscordAgent:
    """
    Generic Discord notification agent.

    Formats and publishes findings to Discord:
    - Status reports
    - Investigation results
    - Escalation alerts

    Can be used in any agent swarm that needs Discord notifications.
    """

    NAME = "discord"
    DESCRIPTION = "Publish summaries and alerts to Discord"

    def __init__(
        self,
        system_prompt: str | None = None,
        additional_tools: list | None = None,
        hooks_factory: Any = None,
    ):
        """
        Initialize the Discord agent.

        Args:
            system_prompt: Custom system prompt (uses default if not provided)
            additional_tools: Extra tools beyond discord_notify
            hooks_factory: Factory function to create hooks
        """
        self._agent: Agent | None = None
        self._system_prompt = system_prompt or DISCORD_AGENT_PROMPT
        self._additional_tools = additional_tools or []
        self._hooks_factory = hooks_factory

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            tools = [discord_notify] + self._additional_tools
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=self._system_prompt,
                tools=tools,
                hooks_factory=self._hooks_factory,
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
