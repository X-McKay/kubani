"""
Kubernetes inspection tools for the monitoring agent.

These tools provide the Strands agent with the ability to inspect
various aspects of the Kubernetes cluster.
"""

from datetime import UTC, datetime
from typing import Any

from kubernetes import client, config
from strands import tool


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


# Export all tools for use with Strands agent
ALL_TOOLS = [
    get_node_status,
    get_pod_status_summary,
    get_recent_events,
    get_deployment_status,
    get_resource_usage,
    get_pvc_status,
]
