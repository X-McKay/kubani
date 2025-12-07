"""Data models for cluster state and configuration."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PodStatus(BaseModel):
    """Kubernetes pod status information."""

    name: str
    namespace: str
    node: str
    status: str
    restarts: int


class ServiceStatus(BaseModel):
    """Kubernetes service status information."""

    name: str
    namespace: str
    pod_count: str  # Format: "ready/total" e.g., "3/3"
    health_status: str  # "Healthy", "Degraded", "Unhealthy", "Unknown"


class NodeStatus(BaseModel):
    """Kubernetes node status information."""

    name: str
    role: str
    status: str  # Ready, NotReady, Unknown
    cpu_usage: float
    memory_usage: float
    tailscale_ip: str
    kubelet_version: str
    last_heartbeat: datetime


class ClusterState(BaseModel):
    """Current cluster state."""

    name: str
    nodes: list[NodeStatus] = Field(default_factory=list)
    pods: list[PodStatus] = Field(default_factory=list)
    api_server: str
    flux_status: str = "unknown"

    @classmethod
    def from_kubernetes_api(cls, api_client, cluster_name: str) -> "ClusterState":
        """Fetch current state from Kubernetes API."""
        from kubernetes.client import Configuration

        # Get API server URL from config
        config = Configuration.get_default_copy()
        api_server = config.host if config else "unknown"

        # Fetch nodes
        nodes_response = api_client.list_node()
        nodes = []
        for node in nodes_response.items:
            # Get node status
            status = "Unknown"
            last_heartbeat = datetime.now()
            for condition in node.status.conditions or []:
                if condition.type == "Ready":
                    status = "Ready" if condition.status == "True" else "NotReady"
                    if condition.last_heartbeat_time:
                        last_heartbeat = condition.last_heartbeat_time

            # Get node role
            role = "worker"
            labels = node.metadata.labels or {}
            if "node-role.kubernetes.io/control-plane" in labels:
                role = "control-plane"
            elif "node-role.kubernetes.io/master" in labels:
                role = "control-plane"
            elif labels.get("node-role") == "control-plane":
                role = "control-plane"

            # Get Tailscale IP from annotations or addresses
            tailscale_ip = ""
            annotations = node.metadata.annotations or {}
            if "tailscale.com/ip" in annotations:
                tailscale_ip = annotations["tailscale.com/ip"]
            else:
                # Try to find from node addresses
                for addr in node.status.addresses or []:
                    if addr.type == "InternalIP" and addr.address.startswith("100."):
                        tailscale_ip = addr.address
                        break

            # Get resource usage (simplified - actual metrics would need metrics-server API)
            cpu_usage = 0.0
            memory_usage = 0.0

            nodes.append(
                NodeStatus(
                    name=node.metadata.name,
                    role=role,
                    status=status,
                    cpu_usage=cpu_usage,
                    memory_usage=memory_usage,
                    tailscale_ip=tailscale_ip or "N/A",
                    kubelet_version=node.status.node_info.kubelet_version,
                    last_heartbeat=last_heartbeat,
                )
            )

        # Fetch pods
        pods_response = api_client.list_pod_for_all_namespaces()
        pods = []
        for pod in pods_response.items:
            # Get restart count
            restarts = 0
            for container_status in pod.status.container_statuses or []:
                restarts += container_status.restart_count

            pods.append(
                PodStatus(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    node=pod.spec.node_name or "unscheduled",
                    status=pod.status.phase,
                    restarts=restarts,
                )
            )

        return cls(
            name=cluster_name,
            nodes=nodes,
            pods=pods,
            api_server=api_server,
            flux_status="unknown",
        )


class ClusterConfig(BaseModel):
    """Cluster configuration."""

    cluster_name: str
    k3s_version: str
    tailscale_network: str
    git_repo_url: str
    git_branch: str = "main"
    flux_namespace: str = "flux-system"

    @field_validator("cluster_name")
    @classmethod
    def validate_cluster_name(cls, v: str) -> str:
        """Validate cluster name is not empty."""
        if not v:
            raise ValueError("cluster_name cannot be empty")
        return v

    @field_validator("k3s_version")
    @classmethod
    def validate_k3s_version(cls, v: str) -> str:
        """Validate k3s_version follows semantic versioning."""
        if not v:
            raise ValueError("k3s_version cannot be empty")
        # Basic semver pattern with optional k3s suffix
        version_pattern = re.compile(r"^v?\d+\.\d+\.\d+(\+k3s\d+)?$")
        if not version_pattern.match(v):
            raise ValueError(
                f"k3s_version '{v}' must follow semantic versioning (e.g., v1.28.5+k3s1)"
            )
        return v

    @field_validator("tailscale_network")
    @classmethod
    def validate_tailscale_network(cls, v: str) -> str:
        """Validate tailscale_network is a valid CIDR."""
        if not v:
            raise ValueError("tailscale_network cannot be empty")
        # Basic CIDR validation
        cidr_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$")
        if not cidr_pattern.match(v):
            raise ValueError(f"tailscale_network '{v}' must be a valid CIDR (e.g., 100.64.0.0/10)")
        return v

    @field_validator("git_repo_url")
    @classmethod
    def validate_git_repo_url(cls, v: str) -> str:
        """Validate git_repo_url is not empty."""
        if not v:
            raise ValueError("git_repo_url cannot be empty")
        return v

    def save(self, path: str) -> None:
        """Save configuration to YAML file."""
        import yaml

        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)

    @classmethod
    def load(cls, path: str) -> "ClusterConfig":
        """Load configuration from YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
