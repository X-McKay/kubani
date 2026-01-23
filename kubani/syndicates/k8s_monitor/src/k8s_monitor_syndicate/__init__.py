"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

This package provides the deployable K8s Monitor syndicate which
orchestrates event classification, issue remediation, and skill learning.

Usage:
    # As a script
    k8s-monitor-worker

    # Programmatically
    from k8s_monitor_syndicate import K8sMonitorSyndicate

    syndicate = K8sMonitorSyndicate()
    await syndicate.start()
"""

# Re-export from the framework's syndicate module
from syndicates.k8s_monitor import K8sMonitorSyndicate

__all__ = ["K8sMonitorSyndicate"]
__version__ = "0.4.0"
