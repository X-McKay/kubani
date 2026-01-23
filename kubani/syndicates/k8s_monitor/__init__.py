"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

Orchestrates event classification, issue remediation, and skill learning.

Usage:
    from syndicates.k8s_monitor import K8sMonitorSyndicate

    syndicate = K8sMonitorSyndicate()
    await syndicate.start()
"""

from syndicates.k8s_monitor.syndicate import K8sMonitorSyndicate

__all__ = ["K8sMonitorSyndicate"]
