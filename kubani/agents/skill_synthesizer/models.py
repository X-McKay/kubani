"""Models for the Skill Synthesizer Agent."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class SkillProposalStatus(Enum):
    """Status of a skill proposal."""

    PENDING = "pending"  # Awaiting review
    APPROVED = "approved"  # Approved by team
    REJECTED = "rejected"  # Rejected by team
    DEPLOYED = "deployed"  # Deployed to production
    EXPIRED = "expired"  # Timed out without decision


@dataclass
class ProposedSkill:
    """A skill proposed by the synthesizer."""

    # Identifiers
    skill_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    domain: str = ""  # e.g., "k8s", "news"
    category: str = ""  # e.g., "diagnostic", "remediation"

    # Content
    description: str = ""
    instructions: str = ""  # Markdown skill content
    implementation_notes: str = ""

    # Evidence
    source_patterns: list[str] = field(default_factory=list)
    source_executions: list[str] = field(default_factory=list)
    source_insights: list[str] = field(default_factory=list)

    # Validation
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    estimated_success_rate: float = 0.0
    confidence: float = 0.0

    # Approval workflow
    status: SkillProposalStatus = SkillProposalStatus.PENDING
    approval_message_id: str | None = None
    approval_channel: str | None = None
    approvers: list[str] = field(default_factory=list)
    rejection_reason: str | None = None

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "skill-synthesizer"
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "domain": self.domain,
            "category": self.category,
            "description": self.description,
            "instructions": self.instructions,
            "implementation_notes": self.implementation_notes,
            "source_patterns": self.source_patterns,
            "source_executions": self.source_executions,
            "source_insights": self.source_insights,
            "test_cases": self.test_cases,
            "estimated_success_rate": self.estimated_success_rate,
            "confidence": self.confidence,
            "status": self.status.value,
            "approval_message_id": self.approval_message_id,
            "approval_channel": self.approval_channel,
            "approvers": self.approvers,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProposedSkill":
        """Create from dictionary."""
        return cls(
            skill_id=data.get("skill_id", str(uuid4())),
            name=data.get("name", ""),
            domain=data.get("domain", ""),
            category=data.get("category", ""),
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            implementation_notes=data.get("implementation_notes", ""),
            source_patterns=data.get("source_patterns", []),
            source_executions=data.get("source_executions", []),
            source_insights=data.get("source_insights", []),
            test_cases=data.get("test_cases", []),
            estimated_success_rate=data.get("estimated_success_rate", 0.0),
            confidence=data.get("confidence", 0.0),
            status=SkillProposalStatus(data.get("status", "pending")),
            approval_message_id=data.get("approval_message_id"),
            approval_channel=data.get("approval_channel"),
            approvers=data.get("approvers", []),
            rejection_reason=data.get("rejection_reason"),
            created_by=data.get("created_by", "skill-synthesizer"),
            context=data.get("context", {}),
        )

    def to_skill_markdown(self) -> str:
        """Generate skill markdown content."""
        return f"""---
name: {self.name}
version: "1.0.0"
domain: {self.domain}
category: {self.category}
auto_generated: true
confidence: {self.confidence:.2f}
---

# {self.name}

{self.description}

## Instructions

{self.instructions}

## Implementation Notes

{self.implementation_notes}

## Evidence

This skill was synthesized from {len(self.source_executions)} successful executions
with an estimated success rate of {self.estimated_success_rate:.0%}.

### Source Patterns
{chr(10).join(f"- {p}" for p in self.source_patterns[:5])}

## Test Cases

{chr(10).join(f"- {tc.get('description', 'Test case')}" for tc in self.test_cases[:5])}
"""


@dataclass
class SynthesisResult:
    """Result of a skill synthesis cycle."""

    # Proposals
    proposals: list[ProposedSkill] = field(default_factory=list)

    # Statistics
    patterns_analyzed: int = 0
    insights_analyzed: int = 0
    proposals_created: int = 0
    proposals_posted: int = 0

    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposals": [p.to_dict() for p in self.proposals],
            "patterns_analyzed": self.patterns_analyzed,
            "insights_analyzed": self.insights_analyzed,
            "proposals_created": self.proposals_created,
            "proposals_posted": self.proposals_posted,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }
