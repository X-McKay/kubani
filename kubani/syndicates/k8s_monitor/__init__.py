"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

Uses a coordinator agent to assess cluster health and dispatch to specialist
agents for investigation and remediation through Temporal workflows.

Workflows:
    K8sMonitorWorkflow: Runs the coordinator agent for health checks

Usage:
    # Start the worker
    k8s-monitor-worker

    # Or programmatically
    from kubani.syndicates.k8s_monitor.workflows import K8sMonitorWorkflow
"""

from .workflows import K8sMonitorWorkflow

__all__ = ["K8sMonitorWorkflow"]
