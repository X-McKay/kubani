"""
ClusterRemediatorAgent - Safe remediation actions.

Applies safe, reversible fixes using MCP tools.
"""

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.prompts import CLUSTER_REMEDIATOR_PROMPT


class ClusterRemediatorAgent:
    """
    Safe remediation agent.

    Can only perform safe operations via MCP:
    - Restart pods (delete to trigger recreation)
    - Scale deployments (within limits)

    Cannot delete resources or modify configurations.
    """

    NAME = "cluster_remediator"
    DESCRIPTION = "Apply safe remediation actions (restart, scale)"

    # No local tools - uses MCP tools exclusively
    TOOLS: list = []

    def __init__(self):
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=CLUSTER_REMEDIATOR_PROMPT,
                tools=self.TOOLS,
                enable_mcp=True,  # Remediator uses MCP for K8s operations
                enable_safety=True,  # Extra safety for remediation
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
