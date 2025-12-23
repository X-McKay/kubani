"""
DiscordNotifierAgent - K8s-specific Discord notification agent.

Wraps core_agents.DiscordAgent with k8s-specific prompt customization.
"""

from strands import Agent

from core_agents import DiscordAgent
from k8s_monitor.hooks import create_default_hooks
from k8s_monitor.prompts import DISCORD_NOTIFIER_PROMPT


def _create_hooks() -> list:
    """Create hooks for the Discord agent."""
    return create_default_hooks(
        enable_safety=False,  # No K8s operations
        enable_observability=True,
        enable_discord=False,
    )


class DiscordNotifierAgent:
    """
    K8s-specific Discord notification agent.

    Uses the core DiscordAgent with k8s-specific prompt customization.
    Formats and publishes findings to Discord:
    - Cluster health check summaries
    - Investigation results
    - Escalation alerts
    """

    NAME = "discord_notifier"
    DESCRIPTION = "Publish summaries and alerts to Discord"

    def __init__(self):
        self._agent: Agent | None = None
        # Use core DiscordAgent with k8s-specific prompt
        self._discord_agent = DiscordAgent(
            system_prompt=DISCORD_NOTIFIER_PROMPT,
            hooks_factory=_create_hooks,
        )

    @property
    def agent(self) -> Agent:
        """Get the underlying Strands agent."""
        return self._discord_agent.agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return self._discord_agent(prompt)
