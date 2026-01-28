"""
Event schema definitions for the event bus.

Framework events are defined here as an enum for type safety.
Domain-specific events (syndicates, agents) should be defined locally
as string constants following the convention: "{domain}:{action}".

Example syndicate-local events:
    # In kubani/syndicates/my_syndicate/events.py
    TASK_COMPLETED = "my_syndicate:task_completed"
    ERROR_DETECTED = "my_syndicate:error_detected"
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """
    Framework-level event types for cross-cutting concerns.

    For domain-specific events, syndicates should define their own
    string constants locally. The event bus accepts both EventType
    enum values and plain strings.

    Naming convention: DOMAIN_ACTION (e.g., AGENT_STARTED)
    """

    # System events - framework-wide concerns
    SYSTEM_MCP_SERVER_REQUESTED = "system:mcp_server_requested"
    SYSTEM_APPROVAL_REQUESTED = "system:approval_requested"
    SYSTEM_APPROVAL_RECEIVED = "system:approval_received"

    # Agent lifecycle - universal agent events
    AGENT_STARTED = "agent:started"
    AGENT_STOPPED = "agent:stopped"
    AGENT_ERROR = "agent:error"
    AGENT_EXECUTION_COMPLETE = "agent:execution_complete"

    # Syndicate lifecycle - universal syndicate events
    SYNDICATE_STARTED = "syndicate:started"
    SYNDICATE_STOPPED = "syndicate:stopped"
    SYNDICATE_AGENT_HANDOFF = "syndicate:agent_handoff"

    # GitOps events - deployment infrastructure
    GITOPS_DEPLOYMENT_STARTED = "gitops:deployment_started"
    GITOPS_DEPLOYMENT_COMPLETED = "gitops:deployment_completed"
    GITOPS_DEPLOYMENT_FAILED = "gitops:deployment_failed"
    GITOPS_ROLLBACK_STARTED = "gitops:rollback_started"
    GITOPS_ROLLBACK_COMPLETED = "gitops:rollback_completed"


# Type alias for event types - accepts both enum and string
EventTypeValue = EventType | str


class Event(BaseModel):
    """
    An event published to the bus.

    Events are the primary mechanism for cross-agent communication.
    They are immutable records of something that happened.

    The type field accepts both EventType enum values (for framework events)
    and plain strings (for syndicate-local events).
    """

    id: str = Field(description="Unique event ID (auto-generated if not provided)")
    type: EventType | str = Field(description="Event type (EventType enum or string)")
    source: str = Field(description="Agent or component that emitted this event")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the event occurred"
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")
    correlation_id: str | None = Field(
        default=None,
        description="ID linking related events (e.g., issue -> remediation -> result)",
    )

    @property
    def type_value(self) -> str:
        """Get the string value of the event type."""
        if isinstance(self.type, EventType):
            return self.type.value
        return self.type

    def to_stream_data(self) -> dict[str, str]:
        """Convert to Redis Stream format (all values must be strings)."""
        import json

        return {
            "id": self.id,
            "type": self.type_value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "payload": json.dumps(self.payload),
            "correlation_id": self.correlation_id or "",
        }

    @classmethod
    def from_stream_data(cls, data: dict[bytes, bytes], message_id: str | None = None) -> "Event":
        """Parse from Redis Stream format.

        Args:
            data: Raw Redis stream message data (bytes keys/values)
            message_id: Optional Redis message ID to use as event ID if not in data
        """
        import json
        import uuid

        # Decode bytes to strings
        decoded = {k.decode(): v.decode() for k, v in data.items()}

        # Use explicit id, message_id, or generate one
        event_id = decoded.get("id") or message_id or str(uuid.uuid4())

        # Handle missing required fields gracefully
        if "type" not in decoded:
            raise ValueError(f"Event missing 'type' field: {decoded}")
        if "source" not in decoded:
            raise ValueError(f"Event missing 'source' field: {decoded}")

        # Try to parse as EventType enum, fall back to string
        event_type_str = decoded["type"]
        try:
            event_type: EventType | str = EventType(event_type_str)
        except ValueError:
            # Not a framework event type, use as plain string
            event_type = event_type_str

        return cls(
            id=event_id,
            type=event_type,
            source=decoded["source"],
            timestamp=datetime.fromisoformat(decoded["timestamp"])
            if "timestamp" in decoded
            else datetime.utcnow(),
            payload=json.loads(decoded["payload"]) if decoded.get("payload") else {},
            correlation_id=decoded.get("correlation_id") or None,
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
