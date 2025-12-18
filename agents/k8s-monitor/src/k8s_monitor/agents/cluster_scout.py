"""
ClusterScoutAgent - Quick cluster-wide health scanning.

Checks nodes, deployments, storage, and resources.
"""

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.prompts import CLUSTER_SCOUT_PROMPT
from k8s_monitor.tools import (
    get_deployment_status,
    get_node_status,
    get_pvc_status,
    get_resource_usage,
)


class ClusterScoutAgent:
    """
    Cluster-wide health scanner.

    Performs rapid assessment of:
    - Node health and capacity
    - Deployment replica status
    - Storage (PVC) binding status
    - Resource usage overview
    """

    NAME = "cluster_scout"
    DESCRIPTION = "Quick cluster-wide health scanning"

    TOOLS = [
        get_node_status,
        get_deployment_status,
        get_pvc_status,
        get_resource_usage,
    ]

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
                tools=self.TOOLS,
                enable_mcp=False,  # Scout uses simple tools only
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
