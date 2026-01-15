"""
Cluster Monitor Agent - Self-contained Kubernetes monitoring.

This agent provides intelligent Kubernetes cluster monitoring with:
- Sentinel: Watches K8s events and publishes issues to event bus
- Event correlation to detect systemic issues
- Stateful investigations with progressive updates
- Memory-driven learning from past incidents
- Automated remediation with transparency
"""

from cluster_monitor.correlator import EventCorrelator
from cluster_monitor.orchestrator import InvestigationOrchestrator
from cluster_monitor.sentinel import SentinelService

__version__ = "0.2.1"

__all__ = [
    "SentinelService",
    "EventCorrelator",
    "InvestigationOrchestrator",
]
