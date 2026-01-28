"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

This package provides the deployable K8s Monitor syndicate which
orchestrates event classification, issue remediation, and multi-agent investigation.

Usage:
    # As a script
    k8s-monitor-worker

    # Programmatically
    from k8s_monitor_syndicate import K8sRemediationWorkflow, K8sInvestigationSwarm
"""

# Re-export workflows from the framework's syndicate module
from kubani.syndicates.k8s_monitor import K8sInvestigationSwarm, K8sRemediationWorkflow

__all__ = ["K8sRemediationWorkflow", "K8sInvestigationSwarm"]
__version__ = "0.4.0"
