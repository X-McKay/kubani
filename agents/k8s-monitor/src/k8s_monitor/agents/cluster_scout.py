"""
ClusterScoutAgent - Quick cluster-wide health scanning.

Checks nodes, deployments, storage, and resources.
Uses MCP kubernetes-mcp-server for native Kubernetes operations.
"""

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.prompts import CLUSTER_SCOUT_PROMPT


class ClusterScoutAgent:
    """
    Cluster-wide health scanner.

    Performs rapid assessment of:
    - Node health and capacity
    - Deployment replica status
    - Storage (PVC) binding status
    - Resource usage overview

    Uses MCP kubernetes-mcp-server for all Kubernetes operations,
    providing standardized protocol access to the cluster.
    """

    NAME = "cluster_scout"
    DESCRIPTION = "Quick cluster-wide health scanning using MCP"

    def __init__(self):
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=CLUSTER_SCOUT_PROMPT,
                tools=[],  # All tools provided by MCP client
                enable_mcp=True,  # Use kubernetes-mcp-server
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
