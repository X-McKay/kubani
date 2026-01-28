"""K8s Monitor Workflows - Temporal workflows for cluster monitoring.

This module provides two workflow patterns:
- K8sRemediationWorkflow: Deterministic remediation sequence (Workflow pattern)
- K8sInvestigationSwarm: Emergent investigation behavior (Swarm pattern)

Usage:
    from kubani.syndicates.k8s_monitor.workflows import (
        K8sRemediationWorkflow,
        K8sInvestigationSwarm,
    )
"""

from .investigation import K8sInvestigationSwarm
from .remediation import K8sRemediationWorkflow

__all__ = [
    "K8sRemediationWorkflow",
    "K8sInvestigationSwarm",
]
