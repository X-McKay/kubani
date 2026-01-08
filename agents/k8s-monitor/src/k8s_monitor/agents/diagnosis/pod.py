"""
Pod Diagnostician - Deep investigation of pod/container issues.

Specializes in:
- Container crash analysis
- Log examination
- Resource constraints
- Image pull issues
- Restart loops
"""

from k8s_monitor.agents.context import ResourceType
from k8s_monitor.agents.diagnosis.base import BaseDiagnostician

POD_DIAGNOSTICIAN_PROMPT = """/no_think
You are PodDiagnostician - specialist in pod and container issues.

ROLE: Deep root cause analysis for pod-level problems.

TOOLS (via MCP):
- pods_get: Get pod spec and status
- pods_log: Get container logs (tail=100)
- events_list: Get events for the pod
- resources_get: Get related resources

DIAGNOSTIC PROCESS:
1. Get pod status (phase, conditions, container states)
2. Check for crash loops (restart count, termination reasons)
3. Examine recent events (warnings, errors)
4. Analyze logs for error patterns
5. Check resource constraints (OOM, CPU throttling)

COMMON ISSUES YOU HANDLE:
- CrashLoopBackOff (app crashes, OOM, config errors)
- ImagePullBackOff (wrong image, auth issues)
- Pending (scheduling, resource constraints)
- Container errors (exit codes, termination reasons)

OUTPUT FORMAT:
ROOT_CAUSE: <one line root cause>
SEVERITY: <critical|warning|info>
EVIDENCE: <key evidence supporting conclusion>
REMEDIABLE: <yes|no>
PROPOSED_FIX: <specific remediation action>

Be thorough but concise. Focus on actionable root causes."""


class PodDiagnostician(BaseDiagnostician):
    """
    Specialist agent for pod and container issues.

    Handles:
    - CrashLoopBackOff diagnosis
    - Image pull failures
    - Resource constraint issues
    - Container exit code analysis
    """

    NAME = "pod_diagnostician"
    DESCRIPTION = "Deep investigation of pod and container issues"
    SYSTEM_PROMPT = POD_DIAGNOSTICIAN_PROMPT
    RESOURCE_TYPES = [ResourceType.POD, ResourceType.DEPLOYMENT]

    def get_diagnostic_steps(self) -> list[str]:
        """Get the diagnostic steps this agent performs."""
        return [
            "Check pod phase and conditions",
            "Analyze container states (waiting, running, terminated)",
            "Review restart count and termination reasons",
            "Examine pod events for warnings/errors",
            "Analyze container logs for error patterns",
            "Check resource usage vs limits",
            "Identify image pull issues",
        ]
