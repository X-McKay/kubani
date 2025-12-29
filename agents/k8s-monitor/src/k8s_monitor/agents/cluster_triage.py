"""
ClusterTriageAgent - Entry point for all K8s monitoring tasks.

Routes requests to appropriate specialist agents after quick assessment.
Uses MCP for Kubernetes operations, plus memory tools for context.
"""

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.prompts import CLUSTER_TRIAGE_PROMPT
from k8s_monitor.tools import (
    search_memories,
)


class ClusterTriageAgent:
    """
    Entry point agent for cluster monitoring.

    Performs quick assessment and routes to specialists:
    - cluster_scout: For cluster-wide health scans
    - pod_diagnostician: For specific pod issues
    - remediation_memory: For recalling past issues

    Uses MCP kubernetes-mcp-server for K8s operations (pods, events),
    plus memory tools for historical context.
    """

    NAME = "cluster_triage"
    DESCRIPTION = "Entry point for K8s monitoring - quick assessment and routing"

    # Keep memory tools - MCP provides K8s operations
    TOOLS = [
        search_memories,
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
                system_prompt=CLUSTER_TRIAGE_PROMPT,
                tools=self.TOOLS,
                enable_mcp=True,  # Use MCP for K8s operations
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
