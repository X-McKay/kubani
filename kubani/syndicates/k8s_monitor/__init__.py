"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

Orchestrates event classification, issue remediation, and multi-agent investigation
through Temporal workflows. Uses dedicated namespace 'k8s-monitor' for isolation.

Workflows:
    K8sRemediationWorkflow: Deterministic remediation sequence for known issues
    K8sInvestigationSwarm: Emergent multi-agent investigation for complex problems

Usage:
    # Start the worker
    k8s-monitor-worker

    # Or programmatically
    from kubani.syndicates.k8s_monitor.workflows import (
        K8sRemediationWorkflow,
        K8sInvestigationSwarm,
    )
"""

from .workflows import K8sInvestigationSwarm, K8sRemediationWorkflow

__all__ = ["K8sRemediationWorkflow", "K8sInvestigationSwarm"]
