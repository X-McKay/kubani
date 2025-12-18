"""
K8s-Monitor Swarm Agents.

Multi-agent swarm for Kubernetes cluster monitoring and remediation.
"""

from k8s_monitor.agents.base import create_agent, create_mcp_client, create_model
from k8s_monitor.agents.cluster_remediator import ClusterRemediatorAgent
from k8s_monitor.agents.cluster_scout import ClusterScoutAgent
from k8s_monitor.agents.cluster_triage import ClusterTriageAgent
from k8s_monitor.agents.discord_notifier import DiscordNotifierAgent
from k8s_monitor.agents.pod_diagnostician import PodDiagnosticianAgent
from k8s_monitor.agents.remediation_memory import RemediationMemoryAgent

__all__ = [
    # Agent classes
    "ClusterTriageAgent",
    "ClusterScoutAgent",
    "PodDiagnosticianAgent",
    "ClusterRemediatorAgent",
    "RemediationMemoryAgent",
    "DiscordNotifierAgent",
    # Utilities
    "create_agent",
    "create_model",
    "create_mcp_client",
]
