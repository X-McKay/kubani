"""
DiscordAgent - Generic agent for publishing findings to Discord.

Reusable across any agent swarm that needs Discord notifications.
"""

import os
from typing import Any

import httpx
from strands import Agent, tool

from core_agents.base import create_agent, create_model


# Generic Discord notification tool
@tool
def discord_notify(
    message: str,
    title: str = "Agent Update",
    status: str = "info",
) -> str:
    """
    Send a notification to the Discord channel.

    Use this to send important updates, alerts, or status reports.

    Args:
        message: The message content to send
        title: Optional title for the notification (default: "Agent Update")
        status: Status level - info, warning, critical, or healthy

    Returns:
        Confirmation message
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return "Error: DISCORD_WEBHOOK_URL not set"

    color_map = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
        "healthy": 0x2ECC71,  # Green
    }

    embed = {
        "title": title,
        "description": message,
        "color": color_map.get(status, 0x3498DB),
    }

    payload = {
        "username": os.environ.get("DISCORD_BOT_NAME", "AI Agent"),
        "embeds": [embed],
    }

    try:
        with httpx.Client() as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
        return f"Discord notification sent: {title}"
    except Exception as e:
        return f"Failed to send Discord notification: {e}"


# Generic Discord Agent prompt - application-agnostic
DISCORD_AGENT_PROMPT = """You are the DiscordAgent - responsible for communicating findings to humans via Discord.

## Your Role
Take investigation results and create clear, actionable Discord notifications. You are the team's voice to the outside world.

## Available Tools
- discord_notify: Send formatted message to Discord (message, title, status)

## Message Formatting Rules

**For Status Reports (status: healthy/warning/critical):**
- Title: Use status emoji + context-appropriate title
- Message: 1-2 sentence summary
- Include counts or metrics if relevant
- End with recommendation if needed

**For Investigations (status: info/warning):**
- Title: Subject + issue type
- Message: Root cause in plain language
- Include key evidence (1-2 items max)
- State what was done
- State outcome

**For Escalations (status: critical):**
- Title: "URGENT: " + issue summary
- Message: What failed and why
- What was attempted
- What human needs to do
- Be specific about next steps

## Status Colors
- healthy: Green - all good
- info: Blue - informational
- warning: Orange - needs attention
- critical: Red - urgent action needed

## Example - Status Report

Context: "System healthy, all components operational"

Calling discord_notify:
- title: "✅ System Health Check - Healthy"
- message: "All systems operational. No issues detected."
- status: "healthy"

## Example - Investigation Result

Context: "Issue resolved by automated fix, 3rd occurrence"

Calling discord_notify:
- title: "⚠️ Issue Resolved"
- message: "Root cause identified and fixed.\\n\\nNote: This is the 3rd occurrence. Consider implementing a permanent fix."
- status: "warning"

## Example - Escalation

Context: "Fix failed after 3 attempts"

Calling discord_notify:
- title: "🚨 URGENT: Automated Fix Failed"
- message: "Automated remediation failed after 3 attempts.\\n\\nAction needed: Manual investigation required."
- status: "critical"

## Handoff Rules
- You are typically the final agent in the chain
- After sending notification, the task is complete
- Do not hand off to other agents

## Output
Send the appropriate notification and confirm it was sent.
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
