"""
Event schema definitions for the event bus.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """
    Typed event categories for cross-agent communication.

    Naming convention: DOMAIN_ACTION (e.g., K8S_ISSUE_DETECTED)
    """

    # K8s domain events
    K8S_ISSUE_DETECTED = "k8s:issue_detected"
    K8S_INVESTIGATION_REQUESTED = "k8s:investigation_requested"
    K8S_REMEDIATION_STARTED = "k8s:remediation_started"
    K8S_REMEDIATION_COMPLETED = "k8s:remediation_completed"
    K8S_REMEDIATION_FAILED = "k8s:remediation_failed"
    K8S_SKILL_EXECUTED = "k8s:skill_executed"

    # News domain events
    NEWS_ARTICLE_INGESTED = "news:article_ingested"
    NEWS_BREAKING_DETECTED = "news:breaking_detected"
    NEWS_DIGEST_PUBLISHED = "news:digest_published"
    NEWS_SOURCE_DISCOVERED = "news:source_discovered"
    NEWS_TREND_DETECTED = "news:trend_detected"

    # System events
    SYSTEM_MCP_SERVER_REQUESTED = "system:mcp_server_requested"
    SYSTEM_APPROVAL_REQUESTED = "system:approval_requested"
    SYSTEM_APPROVAL_RECEIVED = "system:approval_received"
    SYSTEM_SKILL_PROPOSED = "system:skill_proposed"
    SYSTEM_SKILL_APPROVED = "system:skill_approved"

    # Agent lifecycle
    AGENT_STARTED = "agent:started"
    AGENT_STOPPED = "agent:stopped"
    AGENT_ERROR = "agent:error"
    AGENT_SKILL_LEARNED = "agent:skill_learned"
    AGENT_IMAGE_PUSHED = "agent:image_pushed"

    # GitOps events
    GITOPS_DEPLOYMENT_STARTED = "gitops:deployment_started"
    GITOPS_DEPLOYMENT_COMPLETED = "gitops:deployment_completed"
    GITOPS_DEPLOYMENT_FAILED = "gitops:deployment_failed"
    GITOPS_ROLLBACK_STARTED = "gitops:rollback_started"
    GITOPS_ROLLBACK_COMPLETED = "gitops:rollback_completed"

    # Syndicate events (new for kubani restructuring)
    SYNDICATE_STARTED = "syndicate:started"
    SYNDICATE_STOPPED = "syndicate:stopped"
    SYNDICATE_AGENT_HANDOFF = "syndicate:agent_handoff"


class Event(BaseModel):
    """
    An event published to the bus.

    Events are the primary mechanism for cross-agent communication.
    They are immutable records of something that happened.
    """

    id: str = Field(description="Unique event ID (auto-generated if not provided)")
    type: EventType = Field(description="Event type")
    source: str = Field(description="Agent or component that emitted this event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the event occurred"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")
    correlation_id: str | None = Field(
        default=None,
        description="ID linking related events (e.g., issue -> remediation -> result)",
    )

    def to_stream_data(self) -> dict[str, str]:
        """Convert to Redis Stream format (all values must be strings)."""
        import json

        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "payload": json.dumps(self.payload),
            "correlation_id": self.correlation_id or "",
        }

    @classmethod
    def from_stream_data(cls, data: dict[bytes, bytes]) -> "Event":
        """Parse from Redis Stream format."""
        import json

        # Decode bytes to strings
        decoded = {k.decode(): v.decode() for k, v in data.items()}

        return cls(
            id=decoded["id"],
            type=EventType(decoded["type"]),
            source=decoded["source"],
            timestamp=datetime.fromisoformat(decoded["timestamp"]),
            payload=json.loads(decoded["payload"]) if decoded["payload"] else {},
            correlation_id=decoded["correlation_id"] or None,
        )


class MCPServerRequest(BaseModel):
    """Payload for SYSTEM_MCP_SERVER_REQUESTED events."""

    server: str = Field(description="Name of requested MCP server")
    reason: str = Field(description="Why this server is needed")
    requested_by: str = Field(description="Agent requesting the server")
    skill_id: str | None = Field(default=None, description="Skill that requires this server")
    blocking: bool = Field(default=False, description="Whether the requesting operation is blocked")
    priority: str = Field(default="medium", description="low, medium, high")


class ApprovalRequest(BaseModel):
    """Payload for SYSTEM_APPROVAL_REQUESTED events."""

    action: str = Field(description="What action needs approval")
    skill_id: str | None = Field(default=None, description="Skill being executed")
    resource: str = Field(description="Resource being acted upon")
    reason: str = Field(description="Why this action is needed")
    requested_by: str = Field(description="Agent requesting approval")
    timeout_seconds: int = Field(default=300, description="How long to wait for approval")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context for the approver"
    )


class ApprovalResponse(BaseModel):
    """Payload for SYSTEM_APPROVAL_RECEIVED events."""

    request_id: str = Field(description="ID of the approval request")
    approved: bool = Field(description="Whether the action was approved")
    approver: str = Field(description="Who approved/rejected")
    reason: str | None = Field(default=None, description="Reason for decision")


class ImagePushedEvent(BaseModel):
    """Payload for AGENT_IMAGE_PUSHED events."""

    agent_name: str = Field(description="Name of the agent (e.g., k8s-monitor)")
    new_tag: str = Field(description="New image tag (e.g., 0.2.0-abc1234)")
    previous_tag: str | None = Field(default=None, description="Previous image tag for rollback")
    registry: str = Field(default="registry.almckay.io", description="Container registry")
    commit_sha: str | None = Field(default=None, description="Git commit SHA")


class DeploymentEvent(BaseModel):
    """Payload for GITOPS_DEPLOYMENT_* events."""

    agent_name: str = Field(description="Name of the agent being deployed")
    image_tag: str = Field(description="Image tag being deployed")
    namespace: str = Field(default="ai-agents", description="Kubernetes namespace")
    manifest_path: str | None = Field(default=None, description="Path to the deployment manifest")
    commit_sha: str | None = Field(
        default=None, description="Git commit SHA of the manifest change"
    )
    error: str | None = Field(default=None, description="Error message if failed")
    duration_seconds: float | None = Field(default=None, description="Time taken for deployment")
