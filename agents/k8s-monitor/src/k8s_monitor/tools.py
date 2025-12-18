"""
Tools for the k8s-monitor Strands agent.

Provides Kubernetes inspection tools, memory operations, and Discord notifications
using the @tool decorator for Strands agent compatibility.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from kubernetes import client, config
from strands import tool

logger = logging.getLogger(__name__)


def _load_k8s_config() -> None:
    """Load Kubernetes configuration (in-cluster or local)."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _format_cpu(cpu_str: str) -> str:
    """Format CPU value to human-readable string (e.g., '5.5 cores')."""
    if not cpu_str or cpu_str == "unknown":
        return "unknown"
    try:
        cores = float(cpu_str[:-1]) / 1000 if cpu_str.endswith("m") else float(cpu_str)
        # Format nicely - show decimals only if needed
        if cores == int(cores):
            return f"{int(cores)} cores"
        return f"{cores:.1f} cores"
    except ValueError:
        return cpu_str


def _format_memory(mem_str: str) -> str:
    """Format memory value to human-readable string (e.g., '10.5 Gi')."""
    if not mem_str or mem_str == "unknown":
        return "unknown"
    try:
        # Parse to bytes first
        units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
        bytes_val = 0
        for unit, multiplier in units.items():
            if mem_str.endswith(unit):
                bytes_val = int(float(mem_str[: -len(unit)]) * multiplier)
                break
        else:
            bytes_val = int(mem_str)

        # Convert to best unit
        if bytes_val >= 1024**4:
            return f"{bytes_val / (1024**4):.1f} Ti"
        elif bytes_val >= 1024**3:
            return f"{bytes_val / (1024**3):.1f} Gi"
        elif bytes_val >= 1024**2:
            return f"{bytes_val / (1024**2):.1f} Mi"
        elif bytes_val >= 1024:
            return f"{bytes_val / 1024:.1f} Ki"
        return f"{bytes_val} B"
    except ValueError:
        return mem_str


@tool
def get_node_status() -> dict[str, Any]:
    """
    Get the status of all nodes in the cluster.

    Returns a dictionary with node names as keys and their status,
    conditions, capacity, and resource usage.
    """
    _load_k8s_config()
    v1 = client.CoreV1Api()

    nodes = v1.list_node()
    result = {}

    for node in nodes.items:
        conditions = {c.type: c.status for c in node.status.conditions if c.status == "True"}

        # Get allocatable resources
        allocatable = node.status.allocatable or {}

        result[node.metadata.name] = {
            "ready": "Ready" in conditions,
            "conditions": list(conditions.keys()),
            "cpu_allocatable": _format_cpu(allocatable.get("cpu", "unknown")),
            "memory_allocatable": _format_memory(allocatable.get("memory", "unknown")),
            "pods_allocatable": allocatable.get("pods", "unknown"),
            "roles": [
                label.split("/")[-1]
                for label in (node.metadata.labels or {})
                if "node-role.kubernetes.io" in label
            ],
        }

    return result


@tool
def get_pod_status_summary() -> dict[str, Any]:
    """
    Get a summary of pod statuses across all namespaces.

    Returns counts of pods in each phase (Running, Pending, Failed, etc.)
    grouped by namespace.
    """
    _load_k8s_config()
    v1 = client.CoreV1Api()

    pods = v1.list_pod_for_all_namespaces()

    # Count by namespace and phase
    summary: dict[str, dict[str, int]] = {}
    problem_pods: list[dict[str, str]] = []

    for pod in pods.items:
        ns = pod.metadata.namespace
        phase = pod.status.phase

        if ns not in summary:
            summary[ns] = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}

        summary[ns][phase] = summary[ns].get(phase, 0) + 1

        # Track problem pods
        if phase in ("Pending", "Failed", "Unknown"):
            problem_pods.append(
                {
                    "name": pod.metadata.name,
                    "namespace": ns,
                    "phase": phase,
                    "reason": getattr(pod.status, "reason", None) or "Unknown",
                }
            )

    return {
        "by_namespace": summary,
        "problem_pods": problem_pods[:10],  # Limit to 10 for brevity
        "total_problem_pods": len(problem_pods),
    }


@tool
def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    """
    Get recent cluster events, focusing on warnings and errors.

    Args:
        limit: Maximum number of events to return.

    Returns a list of recent events with type, reason, message, and involved object.
    """
    _load_k8s_config()
    v1 = client.CoreV1Api()

    events = v1.list_event_for_all_namespaces(limit=100)

    # Sort by last timestamp, most recent first
    sorted_events = sorted(
        events.items,
        key=lambda e: e.last_timestamp or e.event_time or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    # Filter and format
    result = []
    for event in sorted_events[:limit]:
        # Prioritize warnings
        if event.type == "Normal" and len(result) >= limit // 2:
            continue

        result.append(
            {
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "namespace": event.metadata.namespace,
                "involved_object": f"{event.involved_object.kind}/{event.involved_object.name}",
                "count": event.count,
                "last_seen": str(event.last_timestamp or event.event_time),
            }
        )

    return result


@tool
def get_deployment_status() -> dict[str, Any]:
    """
    Get the status of all deployments in the cluster.

    Returns deployment health including replica counts and any
    deployments that are not fully available.
    """
    _load_k8s_config()
    apps_v1 = client.AppsV1Api()

    deployments = apps_v1.list_deployment_for_all_namespaces()

    healthy = []
    unhealthy = []

    for deploy in deployments.items:
        name = deploy.metadata.name
        namespace = deploy.metadata.namespace
        desired = deploy.spec.replicas or 0
        ready = deploy.status.ready_replicas or 0
        available = deploy.status.available_replicas or 0

        info = {
            "name": name,
            "namespace": namespace,
            "desired": desired,
            "ready": ready,
            "available": available,
        }

        if ready == desired and available == desired:
            healthy.append(info)
        else:
            unhealthy.append(info)

    return {
        "healthy_count": len(healthy),
        "unhealthy_count": len(unhealthy),
        "unhealthy_deployments": unhealthy,
    }


@tool
def get_resource_usage() -> dict[str, Any]:
    """
    Get cluster resource usage summary.

    Returns CPU and memory requests/limits across the cluster.
    Note: This shows requested resources, not actual usage (requires metrics-server).
    """
    _load_k8s_config()
    v1 = client.CoreV1Api()

    pods = v1.list_pod_for_all_namespaces()

    total_cpu_requests = 0.0
    total_memory_requests = 0
    total_cpu_limits = 0.0
    total_memory_limits = 0

    def parse_cpu(cpu_str: str) -> float:
        """Parse CPU string to cores."""
        if not cpu_str:
            return 0.0
        if cpu_str.endswith("m"):
            return float(cpu_str[:-1]) / 1000
        return float(cpu_str)

    def parse_memory(mem_str: str) -> int:
        """Parse memory string to bytes."""
        if not mem_str:
            return 0
        units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
        for unit, multiplier in units.items():
            if mem_str.endswith(unit):
                return int(float(mem_str[: -len(unit)]) * multiplier)
        return int(mem_str)

    for pod in pods.items:
        if pod.status.phase != "Running":
            continue

        for container in pod.spec.containers:
            resources = container.resources
            if resources:
                requests = resources.requests or {}
                limits = resources.limits or {}

                total_cpu_requests += parse_cpu(requests.get("cpu", "0"))
                total_memory_requests += parse_memory(requests.get("memory", "0"))
                total_cpu_limits += parse_cpu(limits.get("cpu", "0"))
                total_memory_limits += parse_memory(limits.get("memory", "0"))

    return {
        "cpu_requests_cores": round(total_cpu_requests, 2),
        "memory_requests_gb": round(total_memory_requests / (1024**3), 2),
        "cpu_limits_cores": round(total_cpu_limits, 2),
        "memory_limits_gb": round(total_memory_limits / (1024**3), 2),
    }


@tool
def get_pvc_status() -> dict[str, Any]:
    """
    Get the status of Persistent Volume Claims.

    Returns PVC binding status and any unbound or lost PVCs.
    """
    _load_k8s_config()
    v1 = client.CoreV1Api()

    pvcs = v1.list_persistent_volume_claim_for_all_namespaces()

    bound = []
    problem = []

    for pvc in pvcs.items:
        info = {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,
            "capacity": pvc.status.capacity.get("storage") if pvc.status.capacity else "unknown",
        }

        if pvc.status.phase == "Bound":
            bound.append(info)
        else:
            problem.append(info)

    return {
        "bound_count": len(bound),
        "problem_count": len(problem),
        "problem_pvcs": problem,
    }


# =============================================================================
# Memory Tools - wrap existing memory.py functions for Strands
# =============================================================================


@tool
def search_memories(
    title: str,
    resource_type: str,
    namespace: str,
    description: str = "",
    limit: int = 5,
) -> str:
    """
    Search for similar past issues and their resolutions in memory.

    Use this before investigating any issue to learn from past experiences.
    Returns relevant memories with remediation history.

    Args:
        title: Issue title or summary
        resource_type: Kubernetes resource type (Pod, Deployment, Service, etc.)
        namespace: Kubernetes namespace
        description: Optional detailed description of the issue
        limit: Maximum number of results to return (default: 5)

    Returns:
        Formatted string with past remediation experiences
    """
    from k8s_monitor.memory import get_remediation_context
    from k8s_monitor.models import HealthStatus, Issue

    issue = Issue(
        id="search-query",
        title=title,
        description=description,
        severity=HealthStatus.WARNING,
        resource_type=resource_type,
        resource_name="unknown",
        namespace=namespace,
        detected_at="",
    )

    return get_remediation_context(issue)


@tool
def store_memory(
    issue_title: str,
    resource_type: str,
    resource_name: str,
    namespace: str,
    root_cause: str,
    fix_action: str,
    was_successful: bool,
    issue_description: str = "",
    severity: str = "warning",
    permanent_fix: str = "",
) -> str:
    """
    Store a completed remediation record in memory for future learning.

    Call this after successfully investigating or fixing an issue.

    Args:
        issue_title: Title/summary of the issue
        resource_type: Kubernetes resource type (Pod, Deployment, etc.)
        resource_name: Name of the affected resource
        namespace: Kubernetes namespace
        root_cause: Identified root cause of the issue
        fix_action: Action taken to fix the issue
        was_successful: Whether the fix was successful
        issue_description: Detailed description of the issue
        severity: Issue severity (warning or critical)
        permanent_fix: Optional permanent fix recommendation

    Returns:
        Confirmation message with memory ID
    """
    from k8s_monitor.memory import store_remediation_memory
    from k8s_monitor.models import (
        FixAttempt,
        HealthStatus,
        Investigation,
        Issue,
        RemediationRecord,
        RemediationStatus,
    )

    issue = Issue(
        id=f"store-{resource_type}-{resource_name}"[:12],
        title=issue_title,
        description=issue_description,
        severity=HealthStatus(severity),
        resource_type=resource_type,
        resource_name=resource_name,
        namespace=namespace,
        detected_at="",
    )

    record = RemediationRecord(
        issue=issue,
        status=RemediationStatus.SUCCESS if was_successful else RemediationStatus.FAILED,
        started_at="",
        investigations=[
            Investigation(
                findings=issue_description,
                root_cause=root_cause,
                suggested_actions=[fix_action],
            )
        ],
        fix_attempts=[
            FixAttempt(
                action_taken=fix_action,
                success=was_successful,
                result="Stored via Strands agent",
            )
        ],
        final_outcome="Resolved" if was_successful else "Failed",
    )

    perm_fix = permanent_fix if permanent_fix else None
    memory_id = store_remediation_memory(record, perm_fix)

    if memory_id:
        return f"Successfully stored remediation memory with ID: {memory_id}"
    return "Failed to store memory - check logs for details"


@tool
def check_permanent_fix(
    title: str,
    resource_type: str,
    namespace: str,
) -> str:
    """
    Check if a permanent fix exists for this type of issue.

    Args:
        title: Issue title/summary
        resource_type: Kubernetes resource type
        namespace: Kubernetes namespace

    Returns:
        Description of permanent fix if one exists, or message indicating none found
    """
    from k8s_monitor.memory import check_for_permanent_fix as check_fix
    from k8s_monitor.models import HealthStatus, Issue

    issue = Issue(
        id="perm-fix-check",
        title=title,
        description="",
        severity=HealthStatus.WARNING,
        resource_type=resource_type,
        resource_name="unknown",
        namespace=namespace,
        detected_at="",
    )

    fix = check_fix(issue)
    if fix:
        return f"Permanent fix found: {fix}"
    return "No permanent fix found for this issue type."


@tool
def get_issue_recurrence_count(
    title: str,
    resource_type: str,
    namespace: str,
) -> str:
    """
    Count how many times this type of issue has occurred before.

    Useful for identifying recurring problems that may need permanent fixes.

    Args:
        title: Issue title/summary
        resource_type: Kubernetes resource type
        namespace: Kubernetes namespace

    Returns:
        Message indicating recurrence count
    """
    from k8s_monitor.memory import get_recurrence_count
    from k8s_monitor.models import HealthStatus, Issue

    issue = Issue(
        id="recurrence-check",
        title=title,
        description="",
        severity=HealthStatus.WARNING,
        resource_type=resource_type,
        resource_name="unknown",
        namespace=namespace,
        detected_at="",
    )

    count = get_recurrence_count(issue)
    if count > 3:
        return f"This issue type has occurred {count} times before. Consider recommending a permanent fix."
    elif count > 0:
        return f"This issue type has occurred {count} times before."
    return "This is the first occurrence of this issue type."


# =============================================================================
# Notification Tools
# =============================================================================


@tool
def discord_notify(
    message: str,
    title: str = "K8s Monitor Update",
    status: str = "info",
) -> str:
    """
    Send a notification to the Discord channel.

    Use this to send important updates, alerts, or status reports.

    Args:
        message: The message content to send
        title: Optional title for the notification (default: "K8s Monitor Update")
        status: Status level - info, warning, critical, or healthy

    Returns:
        Confirmation message
    """
    from core_agents import DiscordEmbed, send_discord_message_sync

    color_map = {
        "info": 0x3498DB,  # Blue
        "warning": 0xF39C12,  # Orange
        "critical": 0xE74C3C,  # Red
        "healthy": 0x2ECC71,  # Green
    }

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set, skipping notification")
        return "Discord notification skipped - webhook URL not configured"

    embed = DiscordEmbed(
        title=title,
        description=message,
        color=color_map.get(status, 0x3498DB),
    )

    try:
        send_discord_message_sync(embeds=[embed], webhook_url=webhook_url)
        return f"Successfully sent Discord notification: {title}"
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return f"Failed to send Discord notification: {e}"


# =============================================================================
# Export all tools for use with Strands agent
# =============================================================================

# Kubernetes inspection tools
K8S_TOOLS = [
    get_node_status,
    get_pod_status_summary,
    get_recent_events,
    get_deployment_status,
    get_resource_usage,
    get_pvc_status,
]

# Memory tools
MEMORY_TOOLS = [
    search_memories,
    store_memory,
    check_permanent_fix,
    get_issue_recurrence_count,
]

# Notification tools
NOTIFICATION_TOOLS = [
    discord_notify,
]

# All tools combined
ALL_TOOLS = K8S_TOOLS + MEMORY_TOOLS + NOTIFICATION_TOOLS
