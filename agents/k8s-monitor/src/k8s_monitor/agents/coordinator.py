"""
K8s Coordinator Agent - Top-level orchestrator for cluster monitoring.

The coordinator is the entry point for all k8s-monitor operations.
It routes requests to appropriate specialist agents and aggregates results.
"""

import logging
from typing import Any

from strands import Agent
from strands.multiagent import Swarm

from k8s_monitor.agents.base import create_agent
from k8s_monitor.agents.cluster_remediator import ClusterRemediatorAgent
from k8s_monitor.agents.cluster_scout import ClusterScoutAgent
from k8s_monitor.agents.context import (
    HandoffContext,
    ResourceType,
    Severity,
)
from k8s_monitor.agents.diagnosis import (
    NetworkDiagnostician,
    NodeDiagnostician,
    PodDiagnostician,
    StorageDiagnostician,
)
from k8s_monitor.agents.discord_notifier import DiscordNotifierAgent
from k8s_monitor.agents.remediation_memory import RemediationMemoryAgent
from k8s_monitor.agents.triage import TriageAgent

logger = logging.getLogger(__name__)


COORDINATOR_PROMPT = """/no_think
You are K8sCoordinatorAgent - the orchestrator for Kubernetes cluster monitoring.

ROLE: Route requests to specialists and ensure complete handling.

PROCESS:
1. Analyze request type (health check, specific issue, status)
2. Route to appropriate agent
3. Ensure findings are reported to Discord

ROUTING:
- Health check request → cluster_scout
- Specific pod/deployment issue → triage_agent
- Node problem → triage_agent
- Status request → cluster_scout

Your job is coordination, not investigation. Gather just enough
info to route correctly, then hand off.

HANDOFFS:
- cluster_scout: Cluster-wide scans
- triage_agent: Issue investigation
- discord_notifier: Final notification (after investigation complete)

Be decisive and route quickly."""


class K8sCoordinatorAgent:
    """
    Top-level coordinator for k8s-monitor hierarchy.

    Responsibilities:
    - Receive incoming requests
    - Route to appropriate tier-2 agent
    - Ensure complete handling (investigation → notification)
    """

    NAME = "k8s_coordinator"
    DESCRIPTION = "Orchestrates K8s monitoring workflow"

    def __init__(self):
        self._agent: Agent | None = None
        self._swarm: Swarm | None = None

        # Initialize sub-agents
        self._triage = TriageAgent()
        self._scout = ClusterScoutAgent()
        self._discord = DiscordNotifierAgent()
        self._remediator = ClusterRemediatorAgent()
        self._memory = RemediationMemoryAgent()

        # Diagnosticians
        self._pod_diag = PodDiagnostician()
        self._node_diag = NodeDiagnostician()
        self._network_diag = NetworkDiagnostician()
        self._storage_diag = StorageDiagnostician()

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the coordinator agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=COORDINATOR_PROMPT,
                tools=[],  # Coordinator doesn't use tools directly
                enable_mcp=False,
            )
        return self._agent

    @property
    def swarm(self) -> Swarm:
        """Create a swarm with all agents for complex operations."""
        if self._swarm is None:
            self._swarm = Swarm(
                [
                    self.agent,
                    self._triage.agent,
                    self._scout.agent,
                    self._pod_diag.agent,
                    self._node_diag.agent,
                    self._network_diag.agent,
                    self._storage_diag.agent,
                    self._remediator.agent,
                    self._memory.agent,
                    self._discord.agent,
                ],
                entry_point=self.agent,
                max_handoffs=12,
                max_iterations=25,
                execution_timeout=300.0,
                node_timeout=120.0,
            )
        return self._swarm

    def health_check(self, prompt: str = "") -> dict[str, Any]:
        """
        Run a cluster health check.

        Args:
            prompt: Optional additional context

        Returns:
            Health check results
        """
        context = HandoffContext.for_health_check(prompt)
        logger.info(f"[{self.NAME}] Starting health check {context.request_id}")

        # Run through swarm for full orchestration
        result = self.swarm(
            f"Perform a comprehensive cluster health check. "
            f"Report findings to Discord. Context: {context.get_summary()}"
        )

        return self._parse_result(result, context)

    def investigate_issue(
        self,
        prompt: str,
        resource_type: ResourceType | None = None,
        resource_name: str | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """
        Investigate a specific issue.

        Args:
            prompt: Description of the issue
            resource_type: Type of Kubernetes resource
            resource_name: Name of the resource
            namespace: Kubernetes namespace

        Returns:
            Investigation results
        """
        context = HandoffContext.for_issue(
            prompt=prompt,
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
        )
        logger.info(f"[{self.NAME}] Starting investigation {context.request_id}")

        # Run through swarm
        result = self.swarm(
            f"Investigate this issue and report findings to Discord.\n\n"
            f"Issue: {prompt}\n"
            f"Resource: {resource_type.value if resource_type else 'Unknown'}"
            f"/{resource_name or 'unknown'}\n"
            f"Namespace: {namespace or 'default'}\n"
            f"Context: {context.get_summary()}"
        )

        return self._parse_result(result, context)

    def diagnose(self, context: HandoffContext) -> HandoffContext:
        """
        Run diagnosis through the appropriate diagnostician.

        Args:
            context: Handoff context with issue details

        Returns:
            Enriched context with diagnosis findings
        """
        # Select diagnostician based on resource type
        diagnostician = self._select_diagnostician(context.resource_type)

        if diagnostician:
            logger.info(f"[{self.NAME}] Routing to {diagnostician.NAME}")
            return diagnostician.diagnose(context)
        else:
            # Fall back to triage for unknown resource types
            logger.info(f"[{self.NAME}] No specific diagnostician, using triage")
            context.add_finding(
                agent=self.NAME,
                description="No specific diagnostician for this resource type",
                severity=Severity.INFO,
            )
            return context

    def _select_diagnostician(self, resource_type: ResourceType | None):
        """Select the appropriate diagnostician for the resource type."""
        if not resource_type:
            return None

        diagnosticians = [
            self._pod_diag,
            self._node_diag,
            self._network_diag,
            self._storage_diag,
        ]

        for diag in diagnosticians:
            if diag.can_handle(resource_type):
                return diag

        return None

    def _parse_result(self, result: Any, context: HandoffContext) -> dict[str, Any]:
        """Parse swarm result into structured format."""
        from k8s_monitor.swarm import parse_swarm_result

        parsed = parse_swarm_result(result, "investigation")
        parsed["context"] = context.to_dict()
        return parsed

    def __call__(self, prompt: str) -> str:
        """Direct invocation for simple queries."""
        return str(self.agent(prompt))


def create_coordinator() -> K8sCoordinatorAgent:
    """Create a new coordinator instance."""
    return K8sCoordinatorAgent()
