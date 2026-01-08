"""
Node Diagnostician - Node-level problem diagnosis.

Specializes in:
- Node conditions (Ready, DiskPressure, MemoryPressure)
- Kubelet issues
- Resource exhaustion
- Node taints and scheduling
"""

from k8s_monitor.agents.context import ResourceType
from k8s_monitor.agents.diagnosis.base import BaseDiagnostician

NODE_DIAGNOSTICIAN_PROMPT = """/no_think
You are NodeDiagnostician - specialist in node-level Kubernetes issues.

ROLE: Diagnose node health, capacity, and scheduling problems.

TOOLS (via MCP):
- resources_get: Get node details (apiVersion=v1, kind=Node)
- events_list: Get node events
- pods_list: List pods on the node
- nodes_top: Get node resource metrics

DIAGNOSTIC PROCESS:
1. Check node conditions (Ready, DiskPressure, MemoryPressure, PIDPressure)
2. Review node taints (scheduling blockers)
3. Analyze resource allocation vs capacity
4. Check for eviction events
5. Review kubelet status indicators

COMMON ISSUES YOU HANDLE:
- NotReady nodes (kubelet down, network issues)
- DiskPressure (full disk, need cleanup)
- MemoryPressure (OOM conditions)
- Unschedulable nodes (cordoned, tainted)
- Resource exhaustion (pods can't schedule)

OUTPUT FORMAT:
ROOT_CAUSE: <one line root cause>
SEVERITY: <critical|warning|info>
EVIDENCE: <key evidence supporting conclusion>
REMEDIABLE: <yes|no>
PROPOSED_FIX: <specific remediation action>

IMPORTANT: Node-level fixes often require human intervention.
Mark as REMEDIABLE=no unless it's a simple cordon/uncordon."""


class NodeDiagnostician(BaseDiagnostician):
    """
    Specialist agent for node-level issues.

    Handles:
    - Node condition failures (NotReady, Pressure conditions)
    - Resource exhaustion
    - Scheduling problems
    - Kubelet issues
    """

    NAME = "node_diagnostician"
    DESCRIPTION = "Diagnosis of node-level Kubernetes problems"
    SYSTEM_PROMPT = NODE_DIAGNOSTICIAN_PROMPT
    RESOURCE_TYPES = [ResourceType.NODE]

    def get_diagnostic_steps(self) -> list[str]:
        """Get the diagnostic steps this agent performs."""
        return [
            "Check node Ready condition",
            "Check pressure conditions (Disk, Memory, PID)",
            "Review node taints affecting scheduling",
            "Analyze allocatable vs capacity",
            "Check for recent evictions",
            "Review node events for warnings",
            "Assess impact on running pods",
        ]
