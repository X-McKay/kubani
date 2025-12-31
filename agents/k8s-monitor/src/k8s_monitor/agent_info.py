"""
Agent information for k8s-monitor.

Defines capabilities and metadata for self-registration with the agent registry.
"""

import os

from core_agents.communication import AgentCapability, AgentInfo

# Agent version from environment or default
AGENT_VERSION = os.environ.get("AGENT_VERSION", "0.2.12")

# K8s-monitor agent capabilities
AGENT_INFO = AgentInfo(
    id="k8s-monitor",
    name="Kubernetes Monitor",
    description="Monitors Kubernetes cluster health and performs automated remediation",
    endpoint=os.environ.get("AGENT_ENDPOINT", "k8s-monitor.ai-agents.svc.cluster.local"),
    version=AGENT_VERSION,
    capabilities=[
        AgentCapability(
            name="cluster-health",
            description="Check overall cluster health including nodes, pods, and services",
            input_schema={},
            output_schema={"status": "string", "issues": "array"},
            tags=["kubernetes", "monitoring", "health"],
        ),
        AgentCapability(
            name="pod-diagnosis",
            description="Diagnose issues with a specific pod",
            input_schema={"namespace": "string", "pod": "string"},
            output_schema={"diagnosis": "string", "evidence": "array"},
            tags=["kubernetes", "diagnosis", "pod"],
        ),
        AgentCapability(
            name="remediation",
            description="Attempt automated remediation of a detected issue",
            input_schema={"issue_id": "string"},
            output_schema={"success": "boolean", "action": "string"},
            tags=["kubernetes", "remediation", "automation"],
        ),
    ],
    metadata={
        "task_queue": "k8s-monitor",
        "requires_mcp": ["kubernetes-mcp-server"],
    },
)
