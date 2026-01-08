"""
K8s-Monitor Swarm Agents.

Multi-agent swarm for Kubernetes cluster monitoring and remediation.

Agent Hierarchy:
- Tier 1: K8sCoordinatorAgent (entry point, orchestration)
- Tier 2: TriageAgent (assessment, routing)
- Tier 3: Diagnosticians (Pod, Node, Network, Storage)
- Tier 4: ClusterRemediatorAgent (safe fixes)
- Support: RemediationMemoryAgent (learning), DiscordNotifierAgent (notifications)
"""

from k8s_monitor.agents.base import (
    K8sAgentFactory,
    create_agent,
    create_mcp_client,
    create_model,
    get_k8s_factory,
)
from k8s_monitor.agents.cluster_remediator import ClusterRemediatorAgent
from k8s_monitor.agents.cluster_scout import ClusterScoutAgent
from k8s_monitor.agents.cluster_triage import ClusterTriageAgent
from k8s_monitor.agents.context import (
    Finding,
    HandoffContext,
    RequestType,
    ResourceType,
    Severity,
    Urgency,
)
from k8s_monitor.agents.coordinator import K8sCoordinatorAgent, create_coordinator
from k8s_monitor.agents.diagnosis import (
    BaseDiagnostician,
    NetworkDiagnostician,
    NodeDiagnostician,
    PodDiagnostician,
    StorageDiagnostician,
)
from k8s_monitor.agents.discord_notifier import DiscordNotifierAgent
from k8s_monitor.agents.pod_diagnostician import PodDiagnosticianAgent
from k8s_monitor.agents.remediation_memory import RemediationMemoryAgent
from k8s_monitor.agents.triage import TriageAgent
from k8s_monitor.agents.world_model import (
    EventType,
    QueryType,
    ResourceKind,
    ResourceNode,
    StateEvent,
    WorldModelAgent,
    WorldModelQuery,
    WorldModelResponse,
)

__all__ = [
    # Tier 1 - Coordinator
    "K8sCoordinatorAgent",
    "create_coordinator",
    # Tier 2 - Triage
    "TriageAgent",
    "ClusterTriageAgent",  # Legacy
    # Tier 3 - Diagnosticians
    "BaseDiagnostician",
    "PodDiagnostician",
    "NodeDiagnostician",
    "NetworkDiagnostician",
    "StorageDiagnostician",
    "PodDiagnosticianAgent",  # Legacy
    # Tier 4 - Remediation
    "ClusterRemediatorAgent",
    # Support Agents
    "ClusterScoutAgent",
    "RemediationMemoryAgent",
    "DiscordNotifierAgent",
    # Context
    "HandoffContext",
    "Finding",
    "RequestType",
    "ResourceType",
    "Severity",
    "Urgency",
    # Factory
    "K8sAgentFactory",
    "get_k8s_factory",
    # Utilities
    "create_agent",
    "create_model",
    "create_mcp_client",
    # WorldModel
    "WorldModelAgent",
    "WorldModelQuery",
    "WorldModelResponse",
    "StateEvent",
    "ResourceNode",
    "ResourceKind",
    "EventType",
    "QueryType",
]
