"""
RemediationMemoryAgent - K8s-specific memory and learning agent.

Wraps core_agents.MemoryAgent with k8s-specific memory tools.
"""

from strands import Agent

from core_agents import MemoryAgent
from k8s_monitor.hooks import create_default_hooks
from k8s_monitor.prompts import REMEDIATION_MEMORY_PROMPT
from k8s_monitor.tools import (
    check_permanent_fix,
    get_issue_recurrence_count,
    search_memories,
    store_memory,
)


def _create_hooks() -> list:
    """Create hooks for the Memory agent."""
    return create_default_hooks(
        enable_safety=True,
        enable_observability=True,
        enable_discord=False,
    )


class RemediationMemoryAgent:
    """
    K8s-specific learning and memory agent.

    Uses the core MemoryAgent with k8s-specific tools and prompt.
    Manages institutional knowledge about:
    - Past issues and their resolutions
    - Recurring patterns
    - Permanent fix recommendations
    """

    NAME = "remediation_memory"
    DESCRIPTION = "Store and recall learnings from past issues"

    # K8s-specific memory tools
    TOOLS = [
        search_memories,
        store_memory,
        check_permanent_fix,
        get_issue_recurrence_count,
    ]

    def __init__(self):
        self._agent: Agent | None = None
        # Use core MemoryAgent with k8s-specific tools and prompt
        self._memory_agent = MemoryAgent(
            tools=self.TOOLS,
            system_prompt=REMEDIATION_MEMORY_PROMPT,
            name=self.NAME,
            description=self.DESCRIPTION,
            hooks_factory=_create_hooks,
        )

    @property
    def agent(self) -> Agent:
        """Get the underlying Strands agent."""
        return self._memory_agent.agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return self._memory_agent(prompt)
