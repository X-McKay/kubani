"""
Network Diagnostician - Connectivity and service mesh issues.

Specializes in:
- Service discovery problems
- Ingress/routing issues
- DNS resolution
- Network policies
- Pod connectivity
"""

from k8s_monitor.agents.context import ResourceType
from k8s_monitor.agents.diagnosis.base import BaseDiagnostician

NETWORK_DIAGNOSTICIAN_PROMPT = """/no_think
You are NetworkDiagnostician - specialist in Kubernetes networking issues.

ROLE: Diagnose connectivity, routing, and service discovery problems.

TOOLS (via MCP):
- resources_get: Get services, ingresses, endpoints
- resources_list: List network policies, ingresses
- pods_exec: Test connectivity from pods (if needed)
- events_list: Get networking-related events

DIAGNOSTIC PROCESS:
1. Check service endpoints (are pods backing the service?)
2. Verify service selector matches pod labels
3. Check ingress configuration and backend health
4. Review network policies that might block traffic
5. Test DNS resolution if service not found

COMMON ISSUES YOU HANDLE:
- Service has no endpoints (selector mismatch, pods not ready)
- Ingress 502/503 errors (backend pods unhealthy)
- Connection timeouts (network policies, firewall)
- DNS resolution failures (CoreDNS issues)
- Service discovery failures

OUTPUT FORMAT:
ROOT_CAUSE: <one line root cause>
SEVERITY: <critical|warning|info>
EVIDENCE: <key evidence supporting conclusion>
REMEDIABLE: <yes|no>
PROPOSED_FIX: <specific remediation action>

Network issues are often config problems - mark REMEDIABLE=no if
it requires manifest changes."""


class NetworkDiagnostician(BaseDiagnostician):
    """
    Specialist agent for network and connectivity issues.

    Handles:
    - Service endpoint problems
    - Ingress misconfigurations
    - Network policy blocks
    - DNS issues
    """

    NAME = "network_diagnostician"
    DESCRIPTION = "Diagnosis of Kubernetes networking and connectivity issues"
    SYSTEM_PROMPT = NETWORK_DIAGNOSTICIAN_PROMPT
    RESOURCE_TYPES = [ResourceType.SERVICE, ResourceType.INGRESS, ResourceType.NETWORK_POLICY]

    def get_diagnostic_steps(self) -> list[str]:
        """Get the diagnostic steps this agent performs."""
        return [
            "Check service endpoints exist",
            "Verify service selector matches pod labels",
            "Review ingress backend health",
            "Check for blocking network policies",
            "Test service DNS resolution",
            "Review connectivity events",
            "Check pod readiness affecting endpoints",
        ]
