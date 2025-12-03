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
        # This will be implemented when we add Kubernetes API integration
        raise NotImplementedError("Kubernetes API integration not yet implemented")


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
