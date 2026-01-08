"""
Storage Diagnostician - Storage and volume issues.

Specializes in:
- PVC binding problems
- Volume mount failures
- Storage capacity issues
- CSI driver problems
"""

from k8s_monitor.agents.context import ResourceType
from k8s_monitor.agents.diagnosis.base import BaseDiagnostician

STORAGE_DIAGNOSTICIAN_PROMPT = """/no_think
You are StorageDiagnostician - specialist in Kubernetes storage issues.

ROLE: Diagnose PVC, volume, and storage-related problems.

TOOLS (via MCP):
- resources_get: Get PVCs, PVs, StorageClasses
- resources_list: List storage resources
- events_list: Get storage-related events
- pods_get: Check pod volume mounts

DIAGNOSTIC PROCESS:
1. Check PVC status (Bound, Pending, Lost)
2. Verify StorageClass exists and is default
3. Check for PV availability (if static provisioning)
4. Review CSI driver status
5. Check for capacity constraints

COMMON ISSUES YOU HANDLE:
- PVC Pending (no matching PV, storage class issue)
- Volume mount failures (permissions, path issues)
- StorageClass not found
- Capacity exhausted
- CSI driver errors

OUTPUT FORMAT:
ROOT_CAUSE: <one line root cause>
SEVERITY: <critical|warning|info>
EVIDENCE: <key evidence supporting conclusion>
REMEDIABLE: <yes|no>
PROPOSED_FIX: <specific remediation action>

Storage issues usually need config changes. Mark REMEDIABLE=yes only
for simple cases like waiting for provisioning."""


class StorageDiagnostician(BaseDiagnostician):
    """
    Specialist agent for storage and volume issues.

    Handles:
    - PVC binding failures
    - Volume mount problems
    - Storage capacity issues
    - CSI driver errors
    """

    NAME = "storage_diagnostician"
    DESCRIPTION = "Diagnosis of Kubernetes storage and volume issues"
    SYSTEM_PROMPT = STORAGE_DIAGNOSTICIAN_PROMPT
    RESOURCE_TYPES = [ResourceType.PVC]

    def get_diagnostic_steps(self) -> list[str]:
        """Get the diagnostic steps this agent performs."""
        return [
            "Check PVC status and phase",
            "Verify StorageClass configuration",
            "Check for available PVs (static provisioning)",
            "Review volume provisioner events",
            "Check storage capacity",
            "Review pod volume mount errors",
            "Assess CSI driver health",
        ]
