"""
PodDiagnosticianAgent - Deep investigation of pod/container issues.

Uses MCP tools for detailed analysis of logs, events, and resources.
"""

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.prompts import POD_DIAGNOSTICIAN_PROMPT


class PodDiagnosticianAgent:
    """
    Deep pod/container investigation agent.

    Uses MCP kubernetes-mcp-server tools for:
    - Pod logs analysis
    - Pod specification inspection
    - Event investigation
    - Resource configuration review
    """

    NAME = "pod_diagnostician"
    DESCRIPTION = "Deep investigation of pod and container issues"

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
                system_prompt=POD_DIAGNOSTICIAN_PROMPT,
                tools=self.TOOLS,
                enable_mcp=True,  # Diagnostician uses MCP for K8s operations
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
