"""Data models for node configuration and management."""

import re

from pydantic import BaseModel, Field, IPvAnyAddress, field_validator


class NodeTaint(BaseModel):
    """Kubernetes node taint configuration."""

    key: str
    value: str
    effect: str  # NoSchedule, PreferNoSchedule, NoExecute

    @field_validator("effect")
    @classmethod
    def validate_effect(cls, v: str) -> str:
        """Validate taint effect is one of the allowed values."""
        allowed = ["NoSchedule", "PreferNoSchedule", "NoExecute"]
        if v not in allowed:
            raise ValueError(f"effect must be one of {allowed}, got {v}")
        return v


class Node(BaseModel):
    """Node configuration model."""

    hostname: str
    ansible_host: str
    tailscale_ip: IPvAnyAddress
    role: str  # control-plane or worker
    reserved_cpu: str | None = None
    reserved_memory: str | None = None
    gpu: bool = False
    node_labels: dict[str, str] = Field(default_factory=dict)
    node_taints: list[NodeTaint] = Field(default_factory=list)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        """Validate hostname follows DNS naming conventions."""
        if not v:
            raise ValueError("hostname cannot be empty")
        if len(v) > 253:
            raise ValueError("hostname cannot exceed 253 characters")
        # RFC 1123 hostname validation
        hostname_pattern = re.compile(
            r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$", re.IGNORECASE
        )
        if not hostname_pattern.match(v):
            raise ValueError(
                f"hostname '{v}' must contain only alphanumeric characters, "
                "hyphens, and dots, and cannot start or end with a hyphen"
            )
        return v

    @field_validator("ansible_host")
    @classmethod
    def validate_ansible_host(cls, v: str) -> str:
        """Validate ansible_host is not empty."""
        if not v:
            raise ValueError("ansible_host cannot be empty")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is either control-plane or worker."""
        allowed_roles = ["control-plane", "worker"]
        if v not in allowed_roles:
            raise ValueError(f"role must be one of {allowed_roles}, got '{v}'")
        return v

    def to_inventory_dict(self) -> dict:
        """Convert to Ansible inventory format."""
        result = {
            "ansible_host": self.ansible_host,
            "tailscale_ip": str(self.tailscale_ip),
        }

        if self.reserved_cpu:
            result["reserved_cpu"] = self.reserved_cpu
        if self.reserved_memory:
            result["reserved_memory"] = self.reserved_memory
        if self.gpu:
            result["gpu"] = self.gpu
        if self.node_labels:
            result["node_labels"] = self.node_labels
        if self.node_taints:
            result["node_taints"] = [
                {"key": t.key, "value": t.value, "effect": t.effect} for t in self.node_taints
            ]

        return result

    @classmethod
    def from_inventory_dict(cls, hostname: str, data: dict) -> "Node":
        """Parse from Ansible inventory format."""
        taints = []
        if "node_taints" in data:
            taints = [NodeTaint(**t) for t in data["node_taints"]]

        return cls(
            hostname=hostname,
            ansible_host=data["ansible_host"],
            tailscale_ip=data["tailscale_ip"],
            role=data.get("role", "worker"),
            reserved_cpu=data.get("reserved_cpu"),
            reserved_memory=data.get("reserved_memory"),
            gpu=data.get("gpu", False),
            node_labels=data.get("node_labels", {}),
            node_taints=taints,
        )
