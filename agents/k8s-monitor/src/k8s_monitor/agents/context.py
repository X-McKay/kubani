"""
Handoff context for agent hierarchy.

Provides structured context passing between agents in the k8s-monitor hierarchy.
Each agent enriches the context with its findings before handing off.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"  # Immediate action required
    WARNING = "warning"  # Should be addressed soon
    INFO = "info"  # Informational, no action needed


class Urgency(str, Enum):
    """Response urgency levels."""

    IMMEDIATE = "immediate"  # Address now
    SOON = "soon"  # Address within hours
    SCHEDULED = "scheduled"  # Can be planned


class RequestType(str, Enum):
    """Types of requests handled by the hierarchy."""

    HEALTH_CHECK = "health_check"
    ISSUE_INVESTIGATION = "issue_investigation"
    REMEDIATION = "remediation"
    STATUS_REPORT = "status_report"


class ResourceType(str, Enum):
    """Kubernetes resource types for issue classification."""

    POD = "Pod"
    DEPLOYMENT = "Deployment"
    NODE = "Node"
    SERVICE = "Service"
    INGRESS = "Ingress"
    PVC = "PersistentVolumeClaim"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"  # pragma: allowlist secret
    NETWORK_POLICY = "NetworkPolicy"
    UNKNOWN = "Unknown"


@dataclass
class Finding:
    """A single finding from an agent's investigation."""

    agent: str
    timestamp: datetime
    description: str
    evidence: dict[str, Any] | None = None
    severity: Severity | None = None


@dataclass
class RemediationAttempt:
    """Record of a remediation attempt."""

    action: str
    timestamp: datetime
    success: bool
    outcome: str
    agent: str


@dataclass
class HandoffContext:
    """
    Context passed between agents in the k8s-monitor hierarchy.

    Each agent enriches the context with its findings before handing off
    to the next agent. The context accumulates information throughout
    the investigation and remediation process.
    """

    # Request identification
    request_id: str = field(default_factory=lambda: str(uuid4())[:8])
    request_type: RequestType = RequestType.HEALTH_CHECK
    original_prompt: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Resource identification (if investigating specific resource)
    resource_type: ResourceType | None = None
    resource_name: str | None = None
    namespace: str | None = None

    # Assessment results
    severity: Severity | None = None
    urgency: Urgency | None = None

    # Accumulated findings from all agents
    findings: list[Finding] = field(default_factory=list)

    # Raw evidence (logs, events, etc.)
    evidence: dict[str, Any] = field(default_factory=dict)

    # Remediation
    proposed_fix: str | None = None
    remediation_attempts: list[RemediationAttempt] = field(default_factory=list)
    fix_applied: bool = False
    fix_outcome: str | None = None

    # Memory/learning
    similar_issues: list[str] = field(default_factory=list)
    recurrence_count: int = 0
    recommended_permanent_fix: str | None = None

    # Agent chain tracking
    agent_chain: list[str] = field(default_factory=list)

    def add_finding(
        self,
        agent: str,
        description: str,
        evidence: dict[str, Any] | None = None,
        severity: Severity | None = None,
    ) -> None:
        """Add a finding from an agent."""
        self.findings.append(
            Finding(
                agent=agent,
                timestamp=datetime.now(UTC),
                description=description,
                evidence=evidence,
                severity=severity,
            )
        )
        if agent not in self.agent_chain:
            self.agent_chain.append(agent)

    def add_evidence(self, key: str, value: Any) -> None:
        """Add evidence to the context."""
        self.evidence[key] = value

    def record_remediation(
        self,
        agent: str,
        action: str,
        success: bool,
        outcome: str,
    ) -> None:
        """Record a remediation attempt."""
        self.remediation_attempts.append(
            RemediationAttempt(
                action=action,
                timestamp=datetime.now(UTC),
                success=success,
                outcome=outcome,
                agent=agent,
            )
        )
        if success:
            self.fix_applied = True
            self.fix_outcome = outcome

    def get_summary(self) -> str:
        """Get a text summary of the context for handoffs."""
        parts = []

        # Request info
        parts.append(f"Request: {self.request_type.value} ({self.request_id})")

        # Resource
        if self.resource_name:
            parts.append(
                f"Resource: {self.resource_type.value if self.resource_type else 'Unknown'}"
                f"/{self.resource_name} in {self.namespace or 'default'}"
            )

        # Severity
        if self.severity:
            parts.append(f"Severity: {self.severity.value}")

        # Findings summary
        if self.findings:
            parts.append(f"Findings ({len(self.findings)}):")
            for f in self.findings[-3:]:  # Last 3 findings
                parts.append(f"  - [{f.agent}] {f.description[:100]}")

        # Remediation
        if self.remediation_attempts:
            last = self.remediation_attempts[-1]
            status = "success" if last.success else "failed"
            parts.append(f"Last remediation: {last.action} ({status})")

        # Memory
        if self.recurrence_count > 0:
            parts.append(f"Recurrence: {self.recurrence_count} times")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "request_type": self.request_type.value,
            "original_prompt": self.original_prompt,
            "resource_type": self.resource_type.value if self.resource_type else None,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
            "severity": self.severity.value if self.severity else None,
            "urgency": self.urgency.value if self.urgency else None,
            "findings_count": len(self.findings),
            "fix_applied": self.fix_applied,
            "fix_outcome": self.fix_outcome,
            "agent_chain": self.agent_chain,
            "recurrence_count": self.recurrence_count,
        }

    @classmethod
    def for_health_check(cls, prompt: str = "") -> "HandoffContext":
        """Create a context for a health check request."""
        return cls(
            request_type=RequestType.HEALTH_CHECK,
            original_prompt=prompt or "Perform cluster health check",
        )

    @classmethod
    def for_issue(
        cls,
        prompt: str,
        resource_type: ResourceType | None = None,
        resource_name: str | None = None,
        namespace: str | None = None,
    ) -> "HandoffContext":
        """Create a context for investigating a specific issue."""
        return cls(
            request_type=RequestType.ISSUE_INVESTIGATION,
            original_prompt=prompt,
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
        )
